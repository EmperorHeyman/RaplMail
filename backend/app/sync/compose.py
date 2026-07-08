"""Outgoing MIME construction.

Builds a correctly-nested message so that HTML, a plain-text fallback, inline
signature/body images (referenced via ``cid:``), and file attachments all render
properly in recipients' clients. Inline images use Content-ID + inline
disposition - this is the fix for the "signature image won't show up" problem.

Structure produced (only the needed layers are created):

    multipart/mixed
      └─ multipart/related
           ├─ multipart/alternative
           │     ├─ text/plain
           │     └─ text/html
           └─ image/*  (inline, Content-ID)   × N
      └─ application/*  (attachment)            × N
"""

from __future__ import annotations

import re
from email.message import EmailMessage
from email.policy import SMTP as SMTP_POLICY
from email.utils import formatdate, make_msgid

from app.providers.base import OutgoingMessage


def _html_to_text(html: str) -> str:
    """Very small HTML->text fallback for the text/plain alternative."""
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"</p>", "\n\n", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def build_mime(msg: OutgoingMessage) -> EmailMessage:
    # SMTP policy => linesep='\r\n'. Without it, quoted-printable soft line breaks
    # serialize as bare '=\n', which strict QP decoders mis-parse - dropping the
    # byte after each soft break and mangling UTF-8 diacritics/markup (e.g.
    # "Lukáš" -> "Luká…=A1", "Republic" -> "=epublic", "<span>" -> "<=pan>").
    root = EmailMessage(policy=SMTP_POLICY)
    root["From"] = msg.from_addr
    root["To"] = ", ".join(msg.to)
    if msg.cc:
        root["Cc"] = ", ".join(msg.cc)
    root["Subject"] = msg.subject
    root["Date"] = formatdate(localtime=True)
    root["Message-ID"] = make_msgid()
    if msg.in_reply_to:
        root["In-Reply-To"] = msg.in_reply_to
    if msg.references:
        root["References"] = " ".join(msg.references)

    text_body = msg.text or _html_to_text(msg.html)
    cal = getattr(msg, "calendar_ics", "") or ""

    if not msg.html and not msg.inline_images and not msg.attachments and not cal:
        # Plain text only.
        root.set_content(text_body or "")
        return root

    # alternative: text + html (+ calendar)
    root.set_content(text_body or "")
    html_part = None
    if msg.html:
        root.add_alternative(msg.html, subtype="html")
        # Capture the html part NOW - the calendar part added below becomes the
        # new last payload element, so [-1] would grab the wrong part.
        html_part = root.get_payload()[-1]
    if cal:
        # An iMIP text/calendar alternative with METHOD - Gmail/Outlook render an
        # RSVP box and drop the event onto the recipient's calendar.
        method = (getattr(msg, "calendar_method", "") or "REQUEST").upper()
        root.add_alternative(cal, subtype="calendar", charset="utf-8")
        cal_part = root.get_payload()[-1]
        cal_part.set_param("method", method)
        cal_part.set_param("component", "VEVENT")
        del cal_part["Content-Disposition"]
    if html_part is not None and msg.inline_images:
        # Attach inline images onto the html part so they live in a related group.
        for img in msg.inline_images:
            cid = img["cid"].strip("<>")
            maintype, _, subtype = img.get("content_type", "image/png").partition("/")
            html_part.add_related(
                img["data"], maintype=maintype or "image", subtype=subtype or "png",
                cid=f"<{cid}>", filename=img.get("filename"),
            )

    for att in msg.attachments:
        maintype, _, subtype = att.get("content_type", "application/octet-stream").partition("/")
        root.add_attachment(
            att["data"], maintype=maintype or "application", subtype=subtype or "octet-stream",
            filename=att.get("filename", "attachment"),
        )
    if getattr(msg, "smime_sign", False) or getattr(msg, "smime_encrypt", False):
        return _apply_smime(root, msg)
    return root


def _apply_smime(root: EmailMessage, msg: OutgoingMessage) -> EmailMessage:
    """Sign and/or encrypt the assembled body as S/MIME, moving the addressing
    headers onto the resulting multipart/signed or application/pkcs7-mime outer.
    The body entity (Content-Type + parts, without From/To/Subject) is what's
    signed/encrypted - the standard S/MIME structure."""
    import email as _email

    from app.sync import smime as _sm
    addr_headers = {}
    for h in ("From", "To", "Cc", "Subject", "Date", "Message-ID", "In-Reply-To", "References"):
        if root[h] is not None:
            addr_headers[h] = root[h]
            del root[h]
    body_bytes = root.as_bytes()
    if msg.smime_sign and msg.smime_cert and msg.smime_key:
        body_bytes = _sm.sign(body_bytes, msg.smime_cert, msg.smime_key)
    if msg.smime_encrypt and msg.smime_recip_certs:
        body_bytes = _sm.encrypt(body_bytes, msg.smime_recip_certs)
    outer = _email.message_from_bytes(body_bytes, policy=SMTP_POLICY)
    for h, v in addr_headers.items():
        del outer[h]
        outer[h] = v
    return outer


def inject_signature(body_html: str, signature_html: str,
                     inline_images: list[dict] | None = None) -> tuple[str, list[dict]]:
    """Append a signature to the compose body and return (html, inline_images).

    ``inline_images`` from the stored signature carry base64 data; we decode them
    into the byte form ``build_mime`` expects.
    """
    import base64

    combined = f'{body_html}<br><br><div class="raplmail-signature">{signature_html}</div>'
    images: list[dict] = []
    for img in inline_images or []:
        images.append({
            "cid": img["cid"],
            "filename": img.get("filename", "sig.png"),
            "content_type": img.get("content_type", "image/png"),
            "data": base64.b64decode(img["data_b64"]),
        })
    return combined, images


_DATA_IMG_RE = re.compile(
    r'(<img\b[^>]*\bsrc=["\'])data:([^;"\']+);base64,([^"\']+)(["\'][^>]*>)', re.IGNORECASE
)


def extract_data_images(html: str) -> tuple[str, list[dict]]:
    """Convert inline data:base64 <img> srcs in a body to CID attachments.

    Recipients' clients routinely strip data: URIs, so a signature/image pasted
    into the body must be sent as a proper inline (Content-ID) attachment.
    """
    import base64
    images: list[dict] = []
    counter = {"i": 0}

    def repl(m: re.Match) -> str:
        ctype = m.group(2)
        try:
            data = base64.b64decode(m.group(3))
        except Exception:
            return m.group(0)
        cid = f"bodyimg{counter['i']}@raplmail"
        counter["i"] += 1
        images.append({"cid": cid, "filename": f"image{counter['i']}",
                       "content_type": ctype, "data": data})
        return f"{m.group(1)}cid:{cid}{m.group(4)}"

    return _DATA_IMG_RE.sub(repl, html or ""), images
