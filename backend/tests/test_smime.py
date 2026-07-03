"""S/MIME crypto round-trips: PKCS#12 load, detached sign + inspect, encrypt +
decrypt, and analyze() on an enveloped-data message."""

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import Encoding, pkcs12
from cryptography.x509.oid import NameOID

from app.sync import smime


def _make_identity(email_addr="alice@example.com"):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.datetime.now(datetime.timezone.utc)
    name = x509.Name([
        x509.NameAttribute(NameOID.COMMON_NAME, "Test User"),
        x509.NameAttribute(NameOID.EMAIL_ADDRESS, email_addr),
    ])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(days=1))
        .not_valid_after(now + datetime.timedelta(days=365))
        .add_extension(x509.SubjectAlternativeName([x509.RFC822Name(email_addr)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(Encoding.PEM).decode()
    key_pem = key.private_bytes(Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    return {"cert": cert_pem, "key": key_pem}, key, cert


def test_pkcs12_roundtrip():
    _ident, key, cert = _make_identity()
    p12 = pkcs12.serialize_key_and_certificates(b"id", key, cert, None, serialization.NoEncryption())
    loaded = smime.load_pkcs12(p12, "")
    assert "BEGIN CERTIFICATE" in loaded["cert"]
    assert "PRIVATE KEY" in loaded["key"]
    assert loaded["email"] == "alice@example.com"


def test_sign_and_inspect():
    ident, _k, _c = _make_identity("bob@corp.com")
    body = b"Content-Type: text/plain\r\n\r\nHello S/MIME"
    signed = smime.sign(body, ident["cert"], ident["key"])
    info = smime.analyze(signed)
    assert info and info["type"] == "signed"
    assert info["signer"] == "bob@corp.com"
    assert info["verified"] is True


def test_encrypt_decrypt():
    ident, _k, _c = _make_identity()
    body = b"Content-Type: text/html\r\n\r\n<p>secret payload</p>"
    enc_der = smime.encrypt(body, [ident["cert"]], encoding=Encoding.DER)
    dec = smime.decrypt(enc_der, ident["cert"], ident["key"])
    assert b"secret payload" in dec


def test_analyze_encrypted():
    ident, _k, _c = _make_identity()
    body = b"Content-Type: text/html\r\n\r\n<p>top secret memo</p>"
    smime_msg = smime.encrypt(body, [ident["cert"]], encoding=Encoding.SMIME)
    info = smime.analyze(smime_msg, identity=ident)
    assert info and info["type"] == "encrypted"
    assert "top secret memo" in (info.get("decrypted") or "")
