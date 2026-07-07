"""Security Lab forensic analyzer: Received-chain parsing, public-IP detection,
link + attachment extraction, and the assembled report. DNS is stubbed so the
test never touches the network."""
from email.message import EmailMessage

from app.api import security
from app.models import Message


def test_is_public_ip():
    assert security._is_public_ip("8.8.8.8") is True
    assert security._is_public_ip("192.168.1.10") is False
    assert security._is_public_ip("10.0.0.5") is False
    assert security._is_public_ip("172.16.4.4") is False
    assert security._is_public_ip("127.0.0.1") is False


def test_parse_received_chain_and_origin():
    # Received headers are prepended (newest first); the analyzer walks them in
    # reverse to reconstruct the delivery path oldest-first and pick the origin.
    headers = [
        "from relay.provider.com (relay.provider.com [10.0.0.9]) by mx.me.com; Mon, 1 Jan 2024 10:00:02 +0000",
        "from evil.example ([203.0.113.7]) by relay.provider.com; Mon, 1 Jan 2024 10:00:01 +0000",
    ]
    hops, origin = security._parse_received(headers)
    assert len(hops) == 2
    assert hops[0]["ip"] == "203.0.113.7"     # oldest first
    assert origin == "203.0.113.7"            # first public hop


def test_auth_alignment():
    import email as _email
    raw = ("From: LinkedIn <no-reply@evil.example>\r\n"
           "Return-Path: <bounce@sendgrid.net>\r\n"
           "DKIM-Signature: v=1; a=rsa-sha256; d=mailer.evil.example; s=sel1; h=from\r\n"
           "Subject: hi\r\n\r\nbody\r\n").encode()
    a = security._auth_alignment(_email.message_from_bytes(raw), "evil.example")
    assert a["dkim_domain"] == "mailer.evil.example"
    assert a["dkim_selector"] == "sel1"
    assert a["dkim_aligned"] is True                            # mailer.evil.example ~ evil.example
    assert a["return_path_domain"] == "sendgrid.net"
    assert a["return_path_aligned"] is False                    # bounce domain differs → SPF not aligned


def test_attachment_flags_double_extension_and_magic():
    # PE bytes (MZ) named .pdf.exe → double-extension + executable + content mismatch.
    flags = security._attachment_flags("invoice.pdf.exe", b"MZ\x90\x00rest")
    joined = " ".join(flags).lower()
    assert "double extension" in joined
    assert "executable" in joined
    # A benign txt with no scary signature yields no flags.
    assert security._attachment_flags("notes.txt", b"just text") == []


def test_clock_skew_backdated():
    hops = [{"from": "x", "by": "y", "ip": "203.0.113.7", "ts": "Mon, 1 Jan 2024 15:00:00 +0000"}]
    sk = security._clock_skew("Mon, 1 Jan 2024 10:00:00 +0000", hops)
    assert sk["skew_seconds"] == 5 * 3600
    assert sk["backdated"] is True


def _raw_message() -> bytes:
    msg = EmailMessage()
    msg["From"] = "LinkedIn <no-reply@evil.example>"
    msg["Subject"] = "Verify your account"
    msg["Message-ID"] = "<abc@evil.example>"
    msg["Reply-To"] = "collect@other-domain.tld"
    msg["Received"] = "from evil.example ([203.0.113.7]) by mx.me.com; Mon, 1 Jan 2024 10:00:01 +0000"
    msg.set_content("hello")
    msg.add_alternative('<a href="http://phish.example/login">click</a>', subtype="html")
    msg.add_attachment(b"MZ\x90\x00malware", maintype="application", subtype="octet-stream",
                       filename="invoice.exe")
    return msg.as_bytes()


def test_analyze_report(monkeypatch):
    # Stub every network helper so the analyzer stays offline in tests.
    monkeypatch.setattr(security, "_dns_intel", lambda d: {"mx": [], "a": [], "spf": "", "dmarc": "", "error": ""})
    monkeypatch.setattr(security, "_domain_age", lambda d: {"created": "", "age_days": None})
    monkeypatch.setattr(security, "_ip_intel", lambda ip: {"ip": ip, "ptr": "", "asn": "", "org": "", "country": "", "city": "", "dnsbl": []})
    row = Message(id=1, account_id=1, folder_id=1, uid=1,
                  from_addr="no-reply@evil.example", from_name="LinkedIn",
                  subject="Verify your account")
    rep = security._analyze(_raw_message(), row)

    assert rep["from"]["domain"] == "evil.example"
    assert rep["reply_to_mismatch"] is True                     # Reply-To on another domain
    assert rep["originating_ip"] == "203.0.113.7"
    assert any(l["domain"] == "phish.example" for l in rep["links"])
    att = rep["attachments"][0]
    assert att["filename"] == "invoice.exe"
    assert len(att["sha256"]) == 64 and len(att["md5"]) == 32 and len(att["sha1"]) == 40
    assert any("executable" in f.lower() for f in att["flags"])  # danger flag fired
    # Brand-impersonation heuristic fires (LinkedIn name, non-LinkedIn domain).
    assert any("impersonation" in w.lower() for w in rep["heuristics"])
    assert any(h["name"] == "Message-ID" for h in rep["headers"])
    assert "origin_intel" in rep and "timeline" in rep and "auth_alignment" in rep
