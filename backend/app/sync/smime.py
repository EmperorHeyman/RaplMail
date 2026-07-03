"""S/MIME (X.509 / PKCS#7) — sign, encrypt, decrypt, and inspect signed mail.

Complements the OpenPGP support for enterprise environments that mandate S/MIME
(law firms, corporate, government). Uses the stdlib ``email`` module +
``cryptography``'s pkcs7/pkcs12 — no extra dependency. Your identity (cert + key,
imported from a .p12/.pfx) and recipients' certificates are managed in
Settings → Encryption.

Note on verification: ``cryptography`` exposes decrypt but not a one-call PKCS#7
signature verify, so ``analyze`` reports the *signer* (from the embedded cert)
and whether that cert is currently within its validity window, rather than a full
trust-chain check. Signed content is still surfaced; the badge is honest about
what was checked.
"""

from __future__ import annotations

import email
from datetime import datetime, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.serialization import pkcs7, pkcs12
from cryptography.x509.oid import NameOID

_PKCS7_MIME = ("application/pkcs7-mime", "application/x-pkcs7-mime")
_PKCS7_SIG = ("application/pkcs7-signature", "application/x-pkcs7-signature")


# --- certificate helpers ---------------------------------------------------

def _cert_email(cert: x509.Certificate) -> str:
    try:
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        emails = san.get_values_for_type(x509.RFC822Name)
        if emails:
            return emails[0]
    except Exception:
        pass
    try:
        attrs = cert.subject.get_attributes_for_oid(NameOID.EMAIL_ADDRESS)
        if attrs:
            return attrs[0].value
    except Exception:
        pass
    return ""


def _cert_cn(cert: x509.Certificate) -> str:
    try:
        return cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
    except Exception:
        return ""


def _cert_valid_now(cert: x509.Certificate) -> bool:
    try:
        now = datetime.now(timezone.utc)
        return cert.not_valid_before_utc <= now <= cert.not_valid_after_utc
    except Exception:
        return False


def load_pkcs12(data: bytes, password: str = "") -> dict:
    """Unpack a .p12/.pfx into PEM strings. Returns
    {cert, key, chain, email, subject}. Raises ValueError on a bad file/password."""
    pw = password.encode() if password else None
    try:
        key, cert, chain = pkcs12.load_key_and_certificates(data, pw)
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Couldn't read the PKCS#12 file (wrong password?): {e}")
    if cert is None or key is None:
        raise ValueError("PKCS#12 file has no certificate + private-key pair")
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    key_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption()).decode()
    chain_pem = "".join(c.public_bytes(serialization.Encoding.PEM).decode() for c in (chain or []))
    return {"cert": cert_pem, "key": key_pem, "chain": chain_pem,
            "email": _cert_email(cert), "subject": _cert_cn(cert)}


def cert_info(cert_pem: str) -> dict:
    """Summarize a PEM certificate for the UI (email, subject, validity)."""
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    return {"email": _cert_email(cert), "subject": _cert_cn(cert), "valid": _cert_valid_now(cert)}


# --- sign / encrypt (outgoing) ---------------------------------------------

def sign(mime_bytes: bytes, cert_pem: str, key_pem: str,
         encoding=serialization.Encoding.SMIME) -> bytes:
    """Detached S/MIME signature over already-serialized MIME bytes → a full
    multipart/signed message (SMIME encoding), ready to hand to SMTP."""
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    builder = (pkcs7.PKCS7SignatureBuilder()
               .set_data(mime_bytes)
               .add_signer(cert, key, hashes.SHA256()))
    return builder.sign(encoding, [pkcs7.PKCS7Options.DetachedSignature])


def encrypt(mime_bytes: bytes, recipient_cert_pems: list[str],
            encoding=serialization.Encoding.SMIME) -> bytes:
    """Encrypt MIME bytes to one or more recipient certs → application/pkcs7-mime
    enveloped-data (SMIME encoding)."""
    if not recipient_cert_pems:
        raise ValueError("No recipient certificate to encrypt to")
    builder = pkcs7.PKCS7EnvelopeBuilder().set_data(mime_bytes)
    for pem in recipient_cert_pems:
        builder = builder.add_recipient(x509.load_pem_x509_certificate(pem.encode()))
    return builder.encrypt(encoding, [])


def decrypt(der_bytes: bytes, cert_pem: str, key_pem: str) -> bytes:
    """Decrypt PKCS#7 enveloped-data (DER) with our identity → the inner MIME."""
    cert = x509.load_pem_x509_certificate(cert_pem.encode())
    key = serialization.load_pem_private_key(key_pem.encode(), password=None)
    return pkcs7.pkcs7_decrypt_der(der_bytes, cert, key, [])


# --- inspect (incoming) ----------------------------------------------------

def _certs_from_pkcs7(blob: bytes) -> list[x509.Certificate]:
    for loader in (pkcs7.load_der_pkcs7_certificates, pkcs7.load_pem_pkcs7_certificates):
        try:
            certs = loader(blob)
            if certs:
                return list(certs)
        except Exception:
            continue
    return []


def _signer_line(certs: list[x509.Certificate]) -> str:
    if not certs:
        return ""
    c = certs[0]
    email_addr, cn = _cert_email(c), _cert_cn(c)
    return email_addr or cn or "unknown signer"


def _inner_text(inner_mime: bytes) -> str:
    """Pull a text/html (or text/plain) body out of a decrypted inner MIME."""
    try:
        msg = email.message_from_bytes(inner_mime)
    except Exception:
        return ""
    html = text = ""
    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "text/html" and not html:
            html = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
        elif ct == "text/plain" and not text:
            text = (part.get_payload(decode=True) or b"").decode(part.get_content_charset() or "utf-8", "replace")
    return html or text


def analyze(raw_mime: bytes, identity: dict | None = None) -> dict | None:
    """Inspect raw MIME for S/MIME. Returns None if not S/MIME, else a dict:
    {type: 'signed'|'encrypted', verified: bool, signer: str, decrypted: str|None}."""
    try:
        msg = email.message_from_bytes(raw_mime)
    except Exception:
        return None
    ctype = (msg.get_content_type() or "").lower()

    if ctype in _PKCS7_MIME:
        smime_type = (msg.get_param("smime-type") or "").lower()
        payload = msg.get_payload(decode=True) or b""
        if smime_type == "signed-data" or not smime_type:
            certs = _certs_from_pkcs7(payload)
            if certs:
                return {"type": "signed", "verified": _cert_valid_now(certs[0]),
                        "signer": _signer_line(certs), "decrypted": None}
        # enveloped-data (or anything else pkcs7-mime) → try to decrypt
        result = {"type": "encrypted", "verified": False, "signer": "", "decrypted": None}
        if identity and identity.get("cert") and identity.get("key"):
            try:
                inner = decrypt(payload, identity["cert"], identity["key"])
                result["decrypted"] = _inner_text(inner)
            except Exception:
                pass
        return result

    if ctype == "multipart/signed":
        for part in msg.walk():
            if part.get_content_type().lower() in _PKCS7_SIG:
                certs = _certs_from_pkcs7(part.get_payload(decode=True) or b"")
                return {"type": "signed", "verified": _cert_valid_now(certs[0]) if certs else False,
                        "signer": _signer_line(certs), "decrypted": None}
    return None
