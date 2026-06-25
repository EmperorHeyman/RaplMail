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

from imapclient import IMAPClient


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
    latin-1 read — e.g. "Svátky" -> "SvÃ¡tky". Reverse it when it round-trips
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
            client = IMAPClient(self._imap_host, port=self._imap_port, use_uid=True, ssl=True)
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

    def fetch_headers(self, folder_path: str, min_uid: int = 1,
                      limit: int | None = None) -> list[HeaderInfo]:
        client = self._imap()
        client.select_folder(folder_path, readonly=True)
        uids = client.search(["UID", f"{min_uid}:*"])
        # search with min_uid:* always returns at least the last message; filter.
        uids = [u for u in uids if u >= min_uid]
        if limit:
            uids = sorted(uids)[-limit:]
        if not uids:
            return []
        data = client.fetch(uids, ["ENVELOPE", "FLAGS", "RFC822.SIZE", "BODYSTRUCTURE"])
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
            when = env.date if isinstance(env.date, datetime) else None
            flags = [f.decode() if isinstance(f, bytes) else str(f) for f in info.get(b"FLAGS", ())]
            out.append(HeaderInfo(
                uid=uid, message_id=msg_id, subject=subject,
                from_addr=from_addr, from_name=from_name,
                to_addrs=to_addrs, cc_addrs=cc_addrs, date=when, flags=flags,
                size=info.get(b"RFC822.SIZE", 0),
                has_attachments=_bodystructure_has_attachment(info.get(b"BODYSTRUCTURE")),
            ))
        return out

    def fetch_raw(self, folder_path: str, uid: int) -> bytes:
        client = self._imap()
        client.select_folder(folder_path, readonly=True)
        data = client.fetch([uid], ["RFC822"])
        return data.get(uid, {}).get(b"RFC822", b"")

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

    def delete_folder(self, path: str) -> None:
        self._imap().delete_folder(path)

    # --- send ---------------------------------------------------------------
    def send(self, message: OutgoingMessage) -> bytes:
        """Send via SMTP and return the raw MIME bytes (for saving to Sent)."""
        mime = build_mime(message)
        raw = mime.as_bytes()
        recipients = [*message.to, *message.cc, *message.bcc]
        context = ssl.create_default_context()
        if self._smtp_port == 465:
            server = smtplib.SMTP_SSL(self._smtp_host, self._smtp_port, context=context)
        else:
            server = smtplib.SMTP(self._smtp_host, self._smtp_port)
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
        try:
            if self._auth.mechanism == "xoauth2":
                server.ehlo()
                server.auth("XOAUTH2", lambda: f"user={self._auth.user}\x01auth=Bearer {self._auth.secret}\x01\x01")
            else:
                server.login(self._auth.user, self._auth.secret)
            server.sendmail(message.from_addr, recipients, raw)
        finally:
            server.quit()
        return raw

    def append_to_folder(self, folder_path: str, raw: bytes, seen: bool = True) -> None:
        """Save a (sent) message into an IMAP folder so it shows up there."""
        flags = [b"\\Seen"] if seen else []
        self._imap().append(folder_path, raw, flags=flags)


def _bodystructure_has_attachment(bs) -> bool:
    """Heuristic: a multipart/mixed structure usually means attachments."""
    if bs is None:
        return False
    try:
        text = repr(bs).lower()
        return "attachment" in text or "mixed" in text
    except Exception:
        return False
