"""Security Lab: a read-only forensic report for a single message.

Aimed at IT admins / power users triaging a suspicious mail: the full raw
headers, the parsed Received hop chain and originating IP, sender-domain DNS
intelligence (MX / A / SPF / DMARC), SPF/DKIM/DMARC verdicts, every link and its
domain, attachment SHA-256 hashes (for a VirusTotal hash lookup), and our own
heuristic findings. All passive - no active scanning of third-party hosts. The UI
turns the returned facts (domains, IPs, URLs, hashes) into one-click deep links to
external tools (VirusTotal, urlscan, MXToolbox, AbuseIPDB, whois).
"""

from __future__ import annotations

import email
import hashlib
import io
import json
import re
import socket
import ssl
import urllib.error
import urllib.request
import zipfile
from datetime import datetime, timezone
from email.message import Message as EmailMessage
from email.utils import parsedate_to_datetime

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from sqlmodel import Session

from app.api.deps import verify_token
from app.core.db import get_session
from app.models import Account, Folder, Message
from app.sync.authcheck import _reg_domain, check_auth, spoof_warnings

router = APIRouter(prefix="/security", tags=["security"], dependencies=[Depends(verify_token)])

# Header names worth surfacing verbatim in the Lab (order preserved). Received is
# handled separately as a parsed hop chain.
_LAB_HEADERS = [
    "From", "Reply-To", "Return-Path", "Sender", "To", "Cc", "Date", "Subject",
    "Message-ID", "In-Reply-To", "References", "Authentication-Results",
    "ARC-Authentication-Results", "Received-SPF", "DKIM-Signature",
    "List-Unsubscribe", "Precedence", "X-Mailer", "User-Agent", "X-Originating-IP",
    "Content-Type",
]

_IPV4_RE = re.compile(r"(?:\d{1,3}\.){3}\d{1,3}")
# IPv6 only when bracketed, so a timestamp like "10:00:01" is never mistaken for one.
_IPV6_RE = re.compile(r"\[([0-9a-fA-F:]{2,}:[0-9a-fA-F:]{2,})\]")
_HREF_RE = re.compile(r'href=["\'](https?://[^"\'\s>]+)["\']', re.IGNORECASE)


def _extract_ip(text: str) -> str:
    m = _IPV4_RE.search(text)
    if m:
        return m.group(0)
    m = _IPV6_RE.search(text)
    return m.group(1) if m else ""


def _is_public_ip(ip: str) -> bool:
    """Coarse RFC1918 / loopback / link-local filter so 'originating IP' is the
    first genuinely external hop, not the mailbox provider's internal relays."""
    if ":" in ip:                       # IPv6 - treat non-local as public
        return not ip.lower().startswith(("::1", "fe80", "fc", "fd"))
    parts = ip.split(".")
    if len(parts) != 4 or not all(p.isdigit() for p in parts):
        return False
    a, b = int(parts[0]), int(parts[1])
    if a in (10, 127) or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31):
        return False
    if a == 169 and b == 254:
        return False
    return True


def _parse_received(headers: list[str]) -> tuple[list[dict], str]:
    """Parse the Received: chain into hops (oldest first) and pick the originating
    public IP (the earliest external hop)."""
    hops: list[dict] = []
    origin = ""
    # Received headers are prepended, so the LAST one is the oldest (origin).
    for raw in reversed(headers or []):
        one = re.sub(r"\s+", " ", raw).strip()
        frm = re.search(r"\bfrom\s+([^\s;]+)", one, re.I)
        by = re.search(r"\bby\s+([^\s;]+)", one, re.I)
        ts = one.split(";")[-1].strip() if ";" in one else ""
        ip = _extract_ip(one)
        hop = {"from": frm.group(1) if frm else "", "by": by.group(1) if by else "",
               "ip": ip, "ts": ts[:60]}
        hops.append(hop)
        if not origin and ip and _is_public_ip(ip):
            origin = ip
    return hops, origin


def _links(html: str) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    unshortened = 0
    for m in _HREF_RE.finditer(html or ""):
        url = m.group(1)
        host = re.sub(r"^https?://", "", url).split("/")[0].split("?")[0].lower()
        key = url[:200]
        if key in seen:
            continue
        seen.add(key)
        # Punycode / non-ASCII (homograph) host - a classic lookalike carrier.
        puny = host.startswith("xn--") or "xn--" in host or any(ord(c) > 127 for c in host)
        final = ""
        if _reg_domain(host) in _SHORTENERS and unshortened < 6:
            final = _unshorten(url)
            unshortened += 1
        out.append({"url": url[:400], "domain": host, "reg_domain": _reg_domain(host),
                    "punycode": puny, "final_url": final[:400]})
        if len(out) >= 100:
            break
    return out


# Extensions that execute code / are common malware carriers, and the
# macro-capable Office formats. A double extension (invoice.pdf.exe) or one of
# these on an "invoice"/"receipt" is a classic lure.
_DANGEROUS_EXT = {"exe", "scr", "com", "pif", "bat", "cmd", "js", "jse", "vbs", "vbe",
                  "wsf", "wsh", "hta", "jar", "msi", "msp", "cpl", "ps1", "lnk", "reg",
                  "iso", "img", "vhd", "apk", "dll", "sys"}
_MACRO_EXT = {"docm", "xlsm", "pptm", "dotm", "xlm", "xlsb"}
_ARCHIVE_EXT = {"zip", "jar", "apk", "docx", "xlsx", "pptx", "odt"}  # zip-container formats
# Magic-byte signatures → the real family, to catch a claimed type that lies.
_MAGIC = [
    (b"MZ", "exe/dll (PE)"),
    (b"%PDF", "pdf"),
    (b"PK\x03\x04", "zip"),
    (b"\x7fELF", "elf"),
    (b"Rar!", "rar"),
    (b"\x1f\x8b", "gzip"),
    (b"\xd0\xcf\x11\xe0", "ole (legacy office)"),
    (b"\xff\xd8\xff", "jpeg"),
    (b"\x89PNG", "png"),
    (b"GIF8", "gif"),
    (b"7z\xbc\xaf", "7z"),
]


def _ext(name: str) -> str:
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def _magic_family(payload: bytes) -> str:
    for sig, fam in _MAGIC:
        if payload.startswith(sig):
            return fam
    return ""


def _attachment_flags(fname: str, payload: bytes) -> list[str]:
    flags: list[str] = []
    lower = (fname or "").lower()
    ext = _ext(lower)
    parts = lower.split(".")
    # Double extension where the visible-looking one is a benign doc and the real
    # one executes (invoice.pdf.exe).
    if len(parts) >= 3 and parts[-1] in _DANGEROUS_EXT and parts[-2] in {
            "pdf", "doc", "docx", "xls", "xlsx", "jpg", "jpeg", "png", "txt", "zip"}:
        flags.append(f"double extension .{parts[-2]}.{parts[-1]}")
    if ext in _DANGEROUS_EXT:
        flags.append(f"executable/script (.{ext})")
    if ext in _MACRO_EXT:
        flags.append(f"macro-enabled Office (.{ext})")
    # Real content vs claimed extension.
    fam = _magic_family(payload)
    if fam:
        if fam.startswith("exe") and ext not in {"exe", "dll", "scr", "sys"}:
            flags.append(f"content is {fam} but named .{ext or '?'}")
        elif "office" in fam and ext in {"pdf", "txt", "jpg", "png"}:
            flags.append(f"content is {fam} but named .{ext}")
    return flags


def _archive_names(payload: bytes) -> list[str]:
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            return [n for n in zf.namelist()][:60]
    except Exception:
        return []


def _attachments(msg: EmailMessage) -> list[dict]:
    out: list[dict] = []
    for part in msg.walk():
        if part.is_multipart():
            continue
        disp = (part.get("Content-Disposition") or "").lower()
        fname = part.get_filename()
        if "attachment" not in disp and not fname:
            continue
        try:
            payload = part.get_payload(decode=True) or b""
        except Exception:
            payload = b""
        name = fname or "(unnamed)"
        flags = _attachment_flags(name, payload) if payload else []
        # Peek inside zip-family archives (list entries; flag risky ones inside).
        contents: list[str] = []
        if _ext(name) in _ARCHIVE_EXT and payload.startswith(b"PK"):
            contents = _archive_names(payload)
            if any(_ext(n) in _DANGEROUS_EXT for n in contents):
                flags.append("archive contains an executable/script")
        out.append({
            "filename": name,
            "content_type": part.get_content_type(),
            "size": len(payload),
            "md5": hashlib.md5(payload).hexdigest() if payload else "",       # noqa: S324 - file id for VT, not security
            "sha1": hashlib.sha1(payload).hexdigest() if payload else "",     # noqa: S324
            "sha256": hashlib.sha256(payload).hexdigest() if payload else "",
            "magic": _magic_family(payload),
            "flags": flags,
            "contents": contents,
        })
        if len(out) >= 40:
            break
    return out


def _dns_intel(domain: str) -> dict:
    """Best-effort DNS lookups for the sender domain (short timeouts, all guarded).
    Returns whatever resolves; missing records simply come back empty."""
    out: dict = {"mx": [], "a": [], "spf": "", "dmarc": "", "error": ""}
    if not domain:
        return out
    try:
        import dns.resolver
    except Exception:
        out["error"] = "dnspython unavailable"
        return out
    resolver = dns.resolver.Resolver()
    resolver.timeout = 2.0
    resolver.lifetime = 4.0

    def q(name, rtype):
        try:
            return list(resolver.resolve(name, rtype))
        except Exception:
            return []

    out["mx"] = sorted(f"{r.preference} {str(r.exchange).rstrip('.')}" for r in q(domain, "MX"))[:10]
    out["a"] = [str(r) for r in q(domain, "A")][:10]
    for r in q(domain, "TXT"):
        txt = "".join(s.decode() if isinstance(s, bytes) else str(s) for s in r.strings) \
            if hasattr(r, "strings") else str(r).strip('"')
        if txt.lower().startswith("v=spf1"):
            out["spf"] = txt[:400]
            break
    for r in q(f"_dmarc.{domain}", "TXT"):
        txt = "".join(s.decode() if isinstance(s, bytes) else str(s) for s in r.strings) \
            if hasattr(r, "strings") else str(r).strip('"')
        if txt.lower().startswith("v=dmarc1"):
            out["dmarc"] = txt[:400]
            break
    return out


def _http_json(url: str, timeout: float = 3.0) -> dict | None:
    """GET a small JSON body with a tight timeout (keyless public APIs). None on
    any failure - every caller treats missing intel as simply 'unknown'."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RaplMail-Lab",
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout, context=ssl.create_default_context()) as r:
            return json.loads(r.read(200_000).decode("utf-8", "replace"))
    except Exception:
        return None


def _domain_age(domain: str) -> dict:
    """Registration date + age in days via RDAP (rdap.org, keyless). A very young
    domain is the single strongest phishing signal."""
    out = {"created": "", "age_days": None}
    if not domain or "." not in domain:
        return out
    data = _http_json(f"https://rdap.org/domain/{domain}")
    if not data:
        return out
    for ev in data.get("events", []) or []:
        if (ev.get("eventAction") or "").lower() == "registration":
            out["created"] = ev.get("eventDate", "")[:10]
            try:
                created = datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00"))
                out["age_days"] = (datetime.now(timezone.utc) - created).days
            except Exception:
                pass
            break
    return out


# A handful of well-known DNS blocklists (reverse the IP, query the zone; any
# answer = listed). Kept short so the lookup stays fast.
_DNSBL_ZONES = [("zen.spamhaus.org", "Spamhaus"), ("bl.spamcop.net", "SpamCop"),
                ("b.barracudacentral.org", "Barracuda"), ("dnsbl.sorbs.net", "SORBS")]


def _dnsbl(ip: str) -> list[str]:
    if not ip or ":" in ip or ip.count(".") != 3:
        return []                                   # IPv4 only
    try:
        import dns.resolver
    except Exception:
        return []
    resolver = dns.resolver.Resolver()
    resolver.timeout = 1.5
    resolver.lifetime = 2.5
    rev = ".".join(reversed(ip.split(".")))
    listed: list[str] = []
    for zone, name in _DNSBL_ZONES:
        try:
            resolver.resolve(f"{rev}.{zone}", "A")
            listed.append(name)
        except Exception:
            pass                                    # NXDOMAIN = not listed
    return listed


def _ip_intel(ip: str) -> dict:
    """Reverse DNS (PTR), ASN/geo (ipwho.is, keyless HTTPS), and DNSBL listing for
    the originating IP."""
    out = {"ip": ip, "ptr": "", "asn": "", "org": "", "country": "", "city": "", "dnsbl": []}
    if not ip:
        return out
    try:
        out["ptr"] = socket.getfqdn(ip) if socket.gethostbyaddr(ip) else ""
    except Exception:
        try:
            out["ptr"] = socket.gethostbyaddr(ip)[0]
        except Exception:
            out["ptr"] = ""
    geo = _http_json(f"https://ipwho.is/{ip}")
    if geo and geo.get("success", True):
        conn = geo.get("connection") or {}
        asn = conn.get("asn")
        out["asn"] = f"AS{asn}" if asn else ""
        out["org"] = conn.get("org") or conn.get("isp") or ""
        out["country"] = geo.get("country") or ""
        out["city"] = geo.get("city") or ""
    out["dnsbl"] = _dnsbl(ip)
    return out


def _auth_alignment(parsed: EmailMessage, from_dom: str) -> dict:
    """DMARC-style alignment: does the DKIM signing domain (d=), the SPF /
    Return-Path domain each share the From's registered domain? Failed alignment
    with an overall 'pass' is how display-name spoofs sneak through."""
    fr = _reg_domain(from_dom)
    out = {"from_domain": fr, "dkim_domain": "", "dkim_selector": "", "dkim_aligned": None,
           "return_path_domain": "", "return_path_aligned": None}
    dkim = parsed.get("DKIM-Signature") or ""
    dm = re.search(r"[;\s]d=([^;\s]+)", dkim)
    sm = re.search(r"[;\s]s=([^;\s]+)", dkim)
    if dm:
        out["dkim_domain"] = dm.group(1).strip()
        out["dkim_selector"] = sm.group(1).strip() if sm else ""
        out["dkim_aligned"] = _reg_domain(out["dkim_domain"]) == fr if fr else None
    rp = parsed.get("Return-Path") or ""
    rpm = re.search(r"@([^>\s]+)", rp)
    if rpm:
        out["return_path_domain"] = rpm.group(1).lower().rstrip(">")
        out["return_path_aligned"] = _reg_domain(out["return_path_domain"]) == fr if fr else None
    return out


def _clock_skew(date_hdr: str, hops: list[dict]) -> dict:
    """Compare the author's Date: header with the newest Received timestamp. A
    large gap means the mail was backdated or the sender's clock is way off."""
    out = {"date": (date_hdr or "").strip(), "received": "", "skew_seconds": None, "backdated": False}
    if not date_hdr:
        return out
    try:
        d = parsedate_to_datetime(date_hdr)
    except Exception:
        return out
    # hops are oldest-first, so the last one is the newest relay stamp.
    for h in reversed(hops or []):
        if h.get("ts"):
            try:
                r = parsedate_to_datetime(h["ts"])
                out["received"] = h["ts"]
                skew = int((r - d).total_seconds())
                out["skew_seconds"] = skew
                out["backdated"] = abs(skew) > 3600     # >1h off
                break
            except Exception:
                continue
    return out


# Known URL shorteners - only these are followed to reveal the true destination
# (following every link would be slow and noisy).
_SHORTENERS = {"bit.ly", "t.co", "tinyurl.com", "goo.gl", "ow.ly", "is.gd", "buff.ly",
               "rebrand.ly", "cutt.ly", "lnkd.in", "rb.gy", "shorturl.at", "t.ly"}


def _unshorten(url: str) -> str:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RaplMail-Lab"}, method="HEAD")
        with urllib.request.urlopen(req, timeout=3.0, context=ssl.create_default_context()) as r:
            final = r.geturl()
        return final if final and final != url else ""
    except urllib.error.HTTPError as e:               # host rejected HEAD but may still expose the redirect target
        try:
            final = e.geturl()
            return final if final and final != url else ""
        except Exception:
            return ""
    except Exception:
        return ""


def _analyze(raw: bytes, msg_row: Message) -> dict:
    parsed = email.message_from_bytes(raw)
    from_addr = msg_row.from_addr or ""
    from_dom = from_addr.split("@")[-1].lower() if "@" in from_addr else ""

    # HTML body (for link extraction) - prefer the parsed MIME's text/html part.
    html = ""
    for part in parsed.walk():
        if part.get_content_type() == "text/html" and not part.is_multipart():
            try:
                html = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
            except Exception:
                html = ""
            if html:
                break

    hops, origin = _parse_received(parsed.get_all("Received") or [])
    headers = [{"name": h, "value": re.sub(r"\s+", " ", str(v)).strip()[:600]}
               for h in _LAB_HEADERS for v in (parsed.get_all(h) or [])]

    reply_to = (parsed.get("Reply-To") or "").strip()
    reply_dom = _reg_domain(re.search(r"[\w.+-]+@([\w.-]+)", reply_to).group(1)) if re.search(r"[\w.+-]+@([\w.-]+)", reply_to) else ""

    return {
        "message_id": msg_row.id,
        "subject": msg_row.subject or "",
        "from": {"name": msg_row.from_name or "", "addr": from_addr,
                 "domain": from_dom, "reg_domain": _reg_domain(from_dom)},
        "reply_to": reply_to,
        "reply_to_mismatch": bool(reply_dom and from_dom and reply_dom != _reg_domain(from_dom)),
        "return_path": (parsed.get("Return-Path") or "").strip(),
        "rfc_message_id": (parsed.get("Message-ID") or "").strip(),
        "date": (parsed.get("Date") or "").strip(),
        "auth": check_auth(raw, from_addr),
        "auth_alignment": _auth_alignment(parsed, from_dom),
        "heuristics": spoof_warnings(from_addr, msg_row.from_name or "", html),
        "headers": headers,
        "hops": hops,
        "originating_ip": origin,
        "dns": _dns_intel(from_dom),
        "domain_age": _domain_age(_reg_domain(from_dom)),
        "origin_intel": _ip_intel(origin) if origin else {},
        "timeline": _clock_skew(parsed.get("Date") or "", hops),
        "links": _links(html),
        "attachments": _attachments(parsed),
    }


@router.get("/analyze/{message_id}")
async def analyze_message(message_id: int, session: Session = Depends(get_session)) -> dict:
    """Full forensic report for one message (Security → Lab)."""
    m = session.get(Message, message_id)
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "message not found")
    account = session.get(Account, m.account_id)
    folder = session.get(Folder, m.folder_id)
    if account is None or folder is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "account/folder gone")
    from app.providers.pool import pool
    try:
        raw = await run_in_threadpool(pool.fetch_raw, account, folder.path, m.uid)
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"couldn't fetch the raw message: {exc}") from exc
    return await run_in_threadpool(_analyze, raw, m)
