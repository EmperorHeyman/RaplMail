"""IMAP + SMTP provider implemented with imapclient and smtplib.

Authenticates with either a password (generic IMAP) or an XOAUTH2 access token
(Gmail / Microsoft 365). Blocking by design; the sync engine calls it from a
worker thread. Access tokens are refreshed by the engine *before* a provider is
constructed, so this class stays stateless with respect to token lifetime.
"""

from __future__ import annotations

import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime
from email.header import decode_header, make_header

from imapclient import IMAPClient, SocketTimeout


def decode_mime_words(value) -> str:
    """Decode RFC 2047 encoded-words (e.g. =?utf-8?q?...?=) into plain text."""
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value

from app.providers.base import FolderInfo, HeaderInfo, OutgoingMessage
from app.providers.oauth import xoauth2_string
from app.sync.compose import build_mime

# IMAP special-use flag -> our FolderRole string.
_SPECIAL_USE = {
    b"\\Sent": "sent",
    b"\\Drafts": "drafts",
    b"\\Trash": "trash",
    b"\\Junk": "junk",
    b"\\Archive": "archive",
}


@dataclass
class Auth:
    mechanism: str          # "plain" | "xoauth2"
    user: str
    secret: str             # password or access token


def _addr_to_str(addr) -> tuple[str, str]:
    """imapclient envelope Address -> (email, display name)."""
    if addr is None:
        return "", ""
    mailbox = (addr.mailbox or b"").decode("utf-8", "replace")
    host = (addr.host or b"").decode("utf-8", "replace")
    name = decode_mime_words(addr.name)
    email_str = f"{mailbox}@{host}" if mailbox and host else mailbox or host
    return email_str, name


def _fix_folder_mojibake(name: str) -> str:
    """Repair folder display names.

    Some servers (notably Office 365) return UTF-8 folder names, but imapclient
    decodes them as modified UTF-7, which for plain UTF-8 bytes degrades to a
    latin-1 read - e.g. "Svátky" -> "SvÃ¡tky". Reverse it when it round-trips
    cleanly back to valid UTF-8.
    """
    try:
        repaired = name.encode("latin-1").decode("utf-8")
        if repaired != name and "�" not in repaired:
            return repaired
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    return name


class ImapSmtpProvider:
    def __init__(self, auth: Auth, imap_host: str, imap_port: int,
                 smtp_host: str, smtp_port: int):
        self._auth = auth
        self._imap_host = imap_host
        self._imap_port = imap_port
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._client: IMAPClient | None = None

    # --- connection ---------------------------------------------------------
    def _imap(self) -> IMAPClient:
        if self._client is None:
            # Bound connect + read so a stalled server (seen on M365) fails fast
            # instead of hanging the sync for minutes on the OS TCP timeout. Read
            # timeout stays well above the 60s IDLE poll so IDLE isn't cut short.
            client = IMAPClient(self._imap_host, port=self._imap_port, use_uid=True, ssl=True,
                                timeout=SocketTimeout(connect=20, read=120))
            if self._auth.mechanism == "xoauth2":
                client.oauth2_login(self._auth.user, self._auth.secret)
            else:
                client.login(self._auth.user, self._auth.secret)
            self._client = client
        return self._client

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.logout()
            except Exception:
                pass
            self._client = None

    # --- reads --------------------------------------------------------------
    def list_folders(self) -> list[FolderInfo]:
        out: list[FolderInfo] = []
        for flags, _delim, name in self._imap().list_folders():
            # Skip container-only folders that can't be selected (e.g. Gmail's
            # "[Gmail]" parent is \Noselect) - trying to fetch them errors with
            # "[NONEXISTENT] Unknown Mailbox".
            if any(f in (b"\\Noselect", b"\\NonExistent") for f in flags):
                continue
            role = "other"
            if name.upper() == "INBOX":
                role = "inbox"
            else:
                for flag in flags:
                    if flag in _SPECIAL_USE:
                        role = _SPECIAL_USE[flag]
                        break
            display = _fix_folder_mojibake(name.split("/")[-1])
            out.append(FolderInfo(name=display, path=name, role=role))
        return out

    def fetch_uids(self, folder_path: str) -> list[int]:
        self._imap().select_folder(folder_path, readonly=True)
        return list(self._imap().search(["ALL"]))

    def folder_uidvalidity(self, folder_path: str) -> int | None:
        """The mailbox's current UIDVALIDITY. If it changes, every stored UID for
        the folder is stale and must be purged + re-synced."""
        try:
            resp = self._imap().select_folder(folder_path, readonly=True)
            v = resp.get(b"UIDVALIDITY")
            return int(v) if v is not None else None
        except Exception:
            return None

    def search_uids(self, folder_path: str, min_uid: int = 1,
                    max_uid: int | None = None) -> list[int]:
        """Every UID in a range, oldest -> newest. One SEARCH; the caller decides
        how to window it. Kept separate from fetch_headers so a caller that must
        page a whole range contiguously (catching up after the app was closed)
        can see how much is actually there instead of silently taking a slice."""
        client = self._imap()
        client.select_folder(folder_path, readonly=True)
        hi = "*" if max_uid is None else str(max_uid)
        uids = client.search(["UID", f"{min_uid}:{hi}"])
        # `min_uid:*` always returns at least the last message even when it's
        # below min_uid, so filter to the real range.
        return sorted(u for u in uids
                      if u >= min_uid and (max_uid is None or u <= max_uid))

    def fetch_headers(self, folder_path: str, min_uid: int = 1,
                      max_uid: int | None = None, limit: int | None = None) -> list[HeaderInfo]:
        uids = self.search_uids(folder_path, min_uid=min_uid, max_uid=max_uid)
        if limit:
            # Newest `limit` UIDs in the range - for backfill that's the window
            # just below the current cursor, so paging walks steadily older.
            uids = uids[-limit:]
        return self.fetch_headers_for(folder_path, uids)

    def fetch_headers_for(self, folder_path: str, uids: list[int]) -> list[HeaderInfo]:
        """Headers for an explicit UID list (one FETCH)."""
        if not uids:
            return []
        client = self._imap()
        client.select_folder(folder_path, readonly=True)
        data = client.fetch(uids, ["ENVELOPE", "FLAGS", "RFC822.SIZE", "BODYSTRUCTURE",
                                   "INTERNALDATE"])
        out: list[HeaderInfo] = []
        for uid, info in data.items():
            env = info.get(b"ENVELOPE")
            if env is None:
                continue
            from_addr, from_name = _addr_to_str(env.from_[0] if env.from_ else None)
            to_addrs = [_addr_to_str(a)[0] for a in (env.to or [])]
            cc_addrs = [_addr_to_str(a)[0] for a in (env.cc or [])]
            subject = decode_mime_words(env.subject)
            msg_id = (env.message_id or b"").decode("utf-8", "replace") if isinstance(env.message_id, bytes) else (env.message_id or "")
            irt = getattr(env, "in_reply_to", None)
            irt = irt.decode("utf-8", "replace") if isinstance(irt, bytes) else (irt or "")
            when = env.date if isinstance(env.date, datetime) else None
            if when is None:
                # No Date header, or one imapclient couldn't parse (it returns
                # None instead of raising). Fall back to the server's
                # INTERNALDATE - otherwise the row is stored with date=NULL and
                # sorts to the very bottom of every date-ordered list, i.e. the
                # message is invisible in the UI. This is what hid sent copies.
                idate = info.get(b"INTERNALDATE")
                when = idate if isinstance(idate, datetime) else None
            flags = [f.decode() if isinstance(f, bytes) else str(f) for f in info.get(b"FLAGS", ())]
            out.append(HeaderInfo(
                uid=uid, message_id=msg_id, subject=subject,
                from_addr=from_addr, from_name=from_name,
                to_addrs=to_addrs, cc_addrs=cc_addrs, date=when, flags=flags,
                size=info.get(b"RFC822.SIZE", 0),
                has_attachments=_bodystructure_has_attachment(info.get(b"BODYSTRUCTURE")),
                in_reply_to=irt.strip(),
            ))
        return out

    def fetch_flags(self, folder_path: str, uids: list[int]) -> dict[int, list[str]]:
        """Just the FLAGS for known UIDs - used to resync read/done state that
        changed on another device, without re-downloading whole messages."""
        return {uid: flags for uid, (flags, _d) in
                self.fetch_flags_dates(folder_path, uids).items()}

    def fetch_flags_dates(self, folder_path: str,
                          uids: list[int]) -> dict[int, tuple[list[str], datetime | None]]:
        """FLAGS + INTERNALDATE for known UIDs, in one round trip. The date rides
        along so the sync can heal rows stored with no date (an absent or
        unparseable Date header) without a second fetch."""
        if not uids:
            return {}
        client = self._imap()
        client.select_folder(folder_path, readonly=True)
        data = client.fetch(uids, ["FLAGS", "INTERNALDATE"])
        out: dict[int, tuple[list[str], datetime | None]] = {}
        for uid, info in data.items():
            flags = [f.decode() if isinstance(f, bytes) else str(f) for f in info.get(b"FLAGS", ())]
            idate = info.get(b"INTERNALDATE")
            out[uid] = (flags, idate if isinstance(idate, datetime) else None)
        return out

    def fetch_raw(self, folder_path: str, uid: int) -> bytes:
        client = self._imap()
        client.select_folder(folder_path, readonly=True)
        data = client.fetch([uid], ["RFC822"])
        return _raw_from_fetch(data.get(uid, {}))

    # --- writes -------------------------------------------------------------
    def set_flags(self, folder_path: str, uid: int, flags: list[str], add: bool = True) -> None:
        client = self._imap()
        client.select_folder(folder_path)
        if add:
            client.add_flags([uid], flags)
        else:
            client.remove_flags([uid], flags)

    def move(self, folder_path: str, uid: int, dest_path: str) -> None:
        client = self._imap()
        client.select_folder(folder_path)
        # MOVE if supported, else copy + delete + expunge.
        if client.has_capability("MOVE"):
            client.move([uid], dest_path)
        else:
            client.copy([uid], dest_path)
            client.add_flags([uid], [b"\\Deleted"])
            client.expunge()

    def delete(self, folder_path: str, uid: int) -> None:
        client = self._imap()
        client.select_folder(folder_path)
        client.add_flags([uid], [b"\\Deleted"])
        client.expunge()

    def create_folder(self, name: str) -> None:
        self._imap().create_folder(name)

    def ensure_folder(self, name: str) -> None:
        """Create a folder only if it doesn't already exist (idempotent)."""
        c = self._imap()
        if not c.folder_exists(name):
            c.create_folder(name)

    def list_uids(self, folder_path: str) -> list[int]:
        """All UIDs in a folder, oldest→newest (used to scan the device-sync folder)."""
        c = self._imap()
        c.select_folder(folder_path, readonly=True)
        return sorted(c.search(["ALL"]))

    def delete_folder(self, path: str) -> None:
        self._imap().delete_folder(path)

    # --- send ---------------------------------------------------------------
    def send(self, message: OutgoingMessage) -> bytes:
        """Send via SMTP and return the raw MIME bytes (for saving to Sent)."""
        mime = build_mime(message)
        raw = mime.as_bytes()
        recipients = [*message.to, *message.cc, *message.bcc]
        context = ssl.create_default_context()
        # A 30s timeout so a stalled SMTP server fails fast with a clear error
        # instead of hanging the send (which previously looked like "stuck for
        # minutes" before the queue retried it).
        if self._smtp_port == 465:
            server = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, context=context, timeout=30)
        else:
            server = smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        try:
            if self._auth.mechanism == "xoauth2":
                server.ehlo()
                server.auth("XOAUTH2", lambda: f"user={self._auth.user}\x01auth=Bearer {self._auth.secret}\x01\x01")
            else:
                server.login(self._auth.user, self._auth.secret)
            # Envelope sender must be a bare address even if From is "Name <addr>".
            from email.utils import parseaddr
            envelope_from = parseaddr(message.from_addr)[1] or message.from_addr
            server.sendmail(envelope_from, recipients, raw)
        finally:
            server.quit()
        return raw

    def append_to_folder(self, folder_path: str, raw: bytes, seen: bool = True,
                          draft: bool = False) -> None:
        """Save a message into an IMAP folder (Sent copy, or a Draft)."""
        flags = []
        if seen:
            flags.append(b"\\Seen")
        if draft:
            flags.append(b"\\Draft")
        self._imap().append(folder_path, raw, flags=flags)


# RFC 3501 defines RFC822 as equivalent to BODY[], and a server is free to
# answer an RFC822 fetch by naming the item either way (Exchange and Zimbra do).
# imapclient keys the result dict by whatever atom the server echoed, so reading
# only b"RFC822" silently yielded b"" on those servers - the message then looked
# empty and, worse, got cached that way. Accept every spelling.
_RAW_KEYS = (b"RFC822", b"BODY[]", b"BODY[NULL]")
# Response items that are never the message itself, so the last-resort scan
# below can't mistake one for the body.
_NOT_RAW = {b"SEQ", b"UID", b"FLAGS", b"INTERNALDATE", b"RFC822.SIZE",
            b"ENVELOPE", b"BODY", b"BODYSTRUCTURE", b"MODSEQ"}


def _raw_from_fetch(info: dict) -> bytes:
    """The raw message bytes out of one imapclient FETCH result."""
    for key in _RAW_KEYS:
        val = info.get(key)
        if isinstance(val, bytes) and val:
            return val
    # Some server spelled it differently again: take the one large bytes value
    # that isn't a known metadata item.
    for key, val in info.items():
        if key not in _NOT_RAW and isinstance(val, bytes) and len(val) > 2:
            return val
    return b""


def _bodystructure_has_attachment(bs) -> bool:
    """Heuristic: a multipart/mixed structure usually means attachments."""
    if bs is None:
        return False
    try:
        text = repr(bs).lower()
        return "attachment" in text or "mixed" in text
    except Exception:
        return False
