"""Link unfurl: fetch a URL's OpenGraph metadata for a preview card.

Off by default (privacy) — the frontend only calls this when the user enables
"Rich link previews". Fetch is best-effort with a short timeout and size cap.
"""

from __future__ import annotations

import re
import ssl
import urllib.request
from urllib.parse import urljoin

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import verify_token

router = APIRouter(prefix="/unfurl", tags=["unfurl"], dependencies=[Depends(verify_token)])

_INSECURE = ssl._create_unverified_context()


def _meta(html: str, prop: str) -> str:
    # <meta property="og:title" content="…"> or name="…"
    for attr in ("property", "name"):
        m = re.search(
            rf'<meta[^>]+{attr}=["\']{re.escape(prop)}["\'][^>]*\bcontent=["\']([^"\']*)["\']',
            html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
        m = re.search(
            rf'<meta[^>]+content=["\']([^"\']*)["\'][^>]*{attr}=["\']{re.escape(prop)}["\']',
            html, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return ""


class Unfurl(BaseModel):
    url: str
    title: str = ""
    description: str = ""
    image: str = ""
    site: str = ""


@router.get("", response_model=Unfurl)
def unfurl(url: str) -> Unfurl:
    if not re.match(r"^https?://", url, re.IGNORECASE):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "bad url")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "RaplMail/0.1 (+link-preview)"})
        with urllib.request.urlopen(req, timeout=6, context=_INSECURE) as r:  # noqa: S310 (localhost app)
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "html" not in ctype and "text" not in ctype:
                return Unfurl(url=url)
            html = r.read(400_000).decode("utf-8", "replace")
    except Exception:
        return Unfurl(url=url)

    title = _meta(html, "og:title") or _meta(html, "twitter:title")
    if not title:
        tm = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        title = re.sub(r"\s+", " ", tm.group(1)).strip() if tm else ""
    desc = _meta(html, "og:description") or _meta(html, "twitter:description") or _meta(html, "description")
    image = _meta(html, "og:image") or _meta(html, "twitter:image")
    if image:
        image = urljoin(url, image)
    site = _meta(html, "og:site_name")
    return Unfurl(url=url, title=title[:200], description=desc[:300], image=image, site=site[:80])
