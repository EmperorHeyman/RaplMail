"""Smoke test: inline-CID signature image produces a correct MIME structure.

This is the core fix for the 'signature image never shows up' problem - verify
the image is embedded with a Content-ID that the HTML references via cid:.
"""

import base64

from app.providers.base import OutgoingMessage
from app.sync.compose import build_mime, inject_signature

# 1x1 PNG
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def test_inline_signature_image_embeds_with_content_id():
    sig_imgs = [{
        "cid": "logo1", "filename": "logo.png", "content_type": "image/png",
        "data_b64": base64.b64encode(_PNG).decode(),
    }]
    html, inline = inject_signature(
        "<p>Hi there!</p>", '<p>Iva<br><img src="cid:logo1"></p>', sig_imgs
    )
    msg = OutgoingMessage(from_addr="me@x.com", to=["you@y.com"], subject="Test",
                          html=html, inline_images=inline)
    mime = build_mime(msg)

    assert "cid:logo1" in html
    content_ids = [p.get("Content-ID") for p in mime.walk()]
    assert "<logo1>" in content_ids, content_ids
    # multipart/alternative (text + html) must be present
    types = [p.get_content_type() for p in mime.walk()]
    assert "text/plain" in types and "text/html" in types, types
    assert "image/png" in types, types


def test_plain_text_only_message():
    msg = OutgoingMessage(from_addr="a@b.com", to=["c@d.com"], subject="Hi", text="hello")
    mime = build_mime(msg)
    assert mime.get_content_type() == "text/plain"
