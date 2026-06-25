"""Sender avatars: fetch a domain's favicon once, cache it on disk, serve it.

Spark-style avatars show the sender's brand mark. Rather than hardcode logos we
fetch the domain's favicon on first request and cache the bytes under the data
dir, so subsequent loads are instant and offline. We try the domain's own
favicon first (no third party sees the lookup); only if that fails do we fall
back to Google's public favicon service.

The endpoint is intentionally unauthenticated: it returns nothing but public
logos and `<img>` tags can't send our auth header anyway. It's localhost-only.
"""

from __future__ import annotations

import hashlib
import re
import ssl
import time
import urllib.request
from urllib.parse import urljoin

from fastapi import APIRouter, Response

from app.core.config import get_settings

router = APIRouter(prefix="/avatars", tags=["avatars"])

_DOMAIN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,}$")
_NEG_TTL = 86400  # re-try a missing favicon after a day


def _cache_dir():
    d = get_settings().data_dir / "avatars"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sniff(b: bytes) -> str:
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if b[:3] == b"GIF":
        return "image/gif"
    if b[:2] == b"\xff\xd8":
        return "image/jpeg"
    if b[:6] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00") or b[:4] == b"\x00\x00\x01\x00":
        return "image/x-icon"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "image/webp"
    head = b[:300].lstrip().lower()
    if head.startswith(b"<svg") or b"<svg" in head:
        return "image/svg+xml"
    return "image/x-icon"


# Favicons are public logos, so for the sender's own site we tolerate a bad/
# self-signed TLS cert (common on internal corporate domains like a123systems.cz)
# rather than show no icon. Third-party services keep normal verification.
_INSECURE = ssl._create_unverified_context()


def _get(url: str, *, insecure: bool = False, want_html: bool = False) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RaplMail/0.1"})
        ctx = _INSECURE if insecure else None
        with urllib.request.urlopen(req, timeout=6, context=ctx) as r:  # noqa: S310 (localhost desktop app)
            if r.status != 200:
                return None
            data = r.read(300_000 if want_html else 200_000)
            if want_html:
                return data
            return data if data and len(data) > 70 else None
    except Exception:
        return None


def _homepage_icon_url(domain: str, insecure: bool) -> str | None:
    """Fetch the domain's homepage and resolve a declared <link rel=icon> href."""
    html = _get(f"https://{domain}/", insecure=insecure, want_html=True)
    if not html:
        return None
    text = html.decode("utf-8", "replace")
    best = None
    for tag in re.findall(r"(?i)<link\b[^>]*>", text):
        if not re.search(r'(?i)rel=["\'][^"\']*icon[^"\']*["\']', tag):
            continue
        href = re.search(r'(?i)href=["\']([^"\']+)["\']', tag)
        if href:
            best = urljoin(f"https://{domain}/", href.group(1))
            if "apple-touch" in tag.lower():  # prefer the higher-res apple icon
                return best
    return best


def _fetch_favicon(domain: str) -> bytes | None:
    # The domain's own site first — verified, then insecure (self-signed corp certs).
    for insecure in (False, True):
        data = _get(f"https://{domain}/favicon.ico", insecure=insecure)
        if data:
            return data
        icon_url = _homepage_icon_url(domain, insecure)
        if icon_url:
            data = _get(icon_url, insecure=insecure)
            if data:
                return data
    # Public favicon services (valid certs) as a last resort.
    for url in (
        f"https://icons.duckduckgo.com/ip3/{domain}.ico",
        f"https://www.google.com/s2/favicons?sz=64&domain={domain}",
    ):
        data = _get(url)
        if data:
            return data
    return None


@router.get("/{domain}")
def avatar(domain: str) -> Response:
    domain = (domain or "").lower().strip()
    if not _DOMAIN_RE.match(domain):
        return Response(status_code=404)

    key = hashlib.sha1(domain.encode()).hexdigest()
    cache_dir = _cache_dir()
    hit = cache_dir / key
    miss = cache_dir / f"{key}.miss"

    if hit.exists():
        data = hit.read_bytes()
        return Response(data, media_type=_sniff(data),
                        headers={"Cache-Control": "public, max-age=604800"})

    if miss.exists() and (time.time() - miss.stat().st_mtime) < _NEG_TTL:
        return Response(status_code=404)

    data = _fetch_favicon(domain)
    if data:
        try:
            hit.write_bytes(data)
        except Exception:
            pass
        return Response(data, media_type=_sniff(data),
                        headers={"Cache-Control": "public, max-age=604800"})

    try:
        miss.write_bytes(b"")
    except Exception:
        pass
    return Response(status_code=404)
