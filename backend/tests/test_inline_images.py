"""Inline (cid:) image handling in the reader body.

Regression for the "images don't load in a mail / show as phantom attachments"
bug: Outlook-style pasted inline images carry a Content-ID but no filename, so
mailparser synthesizes filename == Content-ID. The reader must (a) rewrite the
`cid:` refs to data: URIs and (b) NOT list them as downloadable attachments.
"""

import base64

import mailparser

from app.api.messages import (
    _attachment_meta,
    _embed_inline_images,
    _has_blank_inline_img,
    _sniff_image_mime,
)

# 1x1 transparent PNG.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def _build_raw(cid: str, *, with_filename: bool = False, disposition: str | None = None,
               maintype: str = "image", subtype: str = "png") -> bytes:
    """A multipart/related mail whose HTML references an inline image by cid."""
    from email.message import EmailMessage

    m = EmailMessage()
    m["From"] = "Yaobin Liu <yaobin.liu@example.com>"
    m["To"] = "me@example.com"
    m["Subject"] = "Weekly Report"
    m.set_content("plain fallback")
    m.add_alternative(
        f'<html><body><p>Hello</p><img src="cid:{cid}"></body></html>', subtype="html"
    )
    # Attach the image as an inline related part, mimicking Outlook (Content-ID,
    # usually no filename). maintype/subtype can be overridden to mimic clients
    # that mislabel inline images as application/octet-stream.
    kw = {"maintype": maintype, "subtype": subtype, "cid": f"<{cid}>"}
    if with_filename:
        kw["filename"] = "image001.png"
    if disposition:
        kw["disposition"] = disposition
    m.get_payload()[1].add_related(_PNG, **kw)
    return m.as_bytes()


def test_inline_cid_image_becomes_data_uri():
    cid = "CBE34110@347A236D.E46C4B6A"
    parsed = mailparser.parse_from_bytes(_build_raw(cid))
    out = _embed_inline_images(
        "\n".join(parsed.text_html) if parsed.text_html else "", parsed
    )
    assert "cid:" not in out.lower(), "cid ref should be rewritten"
    assert "data:image/png;base64," in out


def test_inline_cid_image_not_listed_as_attachment():
    # mailparser sets filename == content-id here (no real filename) -> must be
    # recognized as inline body art and excluded from the attachment strip.
    parsed = mailparser.parse_from_bytes(_build_raw("34A68FC1@0B166E11.E46C4B6A0"))
    atts = _attachment_meta(parsed)
    assert atts == [], f"inline image leaked into attachments: {atts}"


def test_real_named_attachment_still_listed():
    # A part with a genuine filename is a real attachment and must stay listed.
    parsed = mailparser.parse_from_bytes(
        _build_raw("IMG9@x", with_filename=True, disposition="attachment")
    )
    atts = _attachment_meta(parsed)
    assert any(a["filename"] == "image001.png" for a in atts)


def test_octet_stream_inline_image_is_embedded_and_hidden():
    # Foxmail/Coremail-style: inline image labelled application/octet-stream with
    # a Content-ID and no filename. Must still be embedded AND kept off the strip.
    cid = "CBE34110@347A236D.E46C4B6A"
    raw = _build_raw(cid, maintype="application", subtype="octet-stream")
    parsed = mailparser.parse_from_bytes(raw)
    out = _embed_inline_images(
        "\n".join(parsed.text_html) if parsed.text_html else "", parsed
    )
    assert "data:image/png;base64," in out and "cid:" not in out.lower()
    assert _attachment_meta(parsed) == []


def test_sniff_image_mime():
    assert _sniff_image_mime(_PNG) == "image/png"
    assert _sniff_image_mime(b"\xff\xd8\xff\xe0blah") == "image/jpeg"
    assert _sniff_image_mime(b"GIF89a....") == "image/gif"
    assert _sniff_image_mime(b"not an image") is None


def test_has_blank_inline_img():
    assert _has_blank_inline_img('<p>hi</p><img alt="x">') is True
    assert _has_blank_inline_img('<img src="">') is True
    assert _has_blank_inline_img('<img src="https://x/y.png">') is False
    assert _has_blank_inline_img("<p>no images here</p>") is False
