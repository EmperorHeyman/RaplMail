"""Attachment text-extraction unit tests (full-text-search-in-attachments)."""

import io
import zipfile

from app.sync.extract import extract_attachment_text


def test_plain_text():
    out = extract_attachment_text("notes.txt", "text/plain", b"Invoice 4471 due Friday")
    assert "Invoice 4471" in out


def test_docx_ooxml():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml",
                   "<w:document><w:body><w:p><w:r><w:t>Quarterly</w:t></w:r>"
                   "<w:r><w:t>Report</w:t></w:r></w:p></w:body></w:document>")
    out = extract_attachment_text("q.docx", "", buf.getvalue())
    assert "Quarterly" in out and "Report" in out


def test_unsupported_returns_empty():
    assert extract_attachment_text("scan.pdf", "application/pdf", b"%PDF-1.4 ...") == ""
    assert extract_attachment_text("photo.jpg", "image/jpeg", b"\xff\xd8\xff") == ""


def test_html_tags_stripped():
    out = extract_attachment_text("page.html", "text/html", b"<h1>Hello</h1><p>World</p>")
    assert "Hello" in out and "<h1>" not in out
