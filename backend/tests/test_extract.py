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


def _minimal_pdf(text: str) -> bytes:
    """Assemble a tiny single-page uncompressed PDF with a valid xref table."""
    stream = f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R"
        b" /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, body)
    xref_pos = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1, xref_pos)
    return bytes(out)


def test_pdf_text():
    pdf = _minimal_pdf("Invoice 9982 payable")
    out = extract_attachment_text("invoice.pdf", "application/pdf", pdf)
    assert "Invoice 9982" in out


def test_corrupt_pdf_returns_empty():
    assert extract_attachment_text("scan.pdf", "application/pdf", b"%PDF-1.4 ...") == ""


def test_unsupported_returns_empty():
    assert extract_attachment_text("photo.jpg", "image/jpeg", b"\xff\xd8\xff") == ""


def test_html_tags_stripped():
    out = extract_attachment_text("page.html", "text/html", b"<h1>Hello</h1><p>World</p>")
    assert "Hello" in out and "<h1>" not in out
