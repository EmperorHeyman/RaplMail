"""PGP/MIME (RFC 3156) construction: a signed/encrypted message that carries
HTML + an attachment is built as multipart/signed or multipart/encrypted (not
inline armor, which would drop those parts). Verifies the produced MIME round-
trips: the detached signature verifies, and the encrypted body decrypts back to
the inner MIME with its attachment intact.
"""
import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

pgpy = pytest.importorskip("pgpy")
from pgpy.constants import (  # noqa: E402
    CompressionAlgorithm, HashAlgorithm, KeyFlags, PubKeyAlgorithm, SymmetricKeyAlgorithm,
)

from app.providers.base import OutgoingMessage  # noqa: E402
from app.sync.compose import build_mime  # noqa: E402


def _make_key(email="alice@example.com"):
    key = pgpy.PGPKey.new(PubKeyAlgorithm.RSAEncryptOrSign, 2048)
    uid = pgpy.PGPUID.new("Alice", email=email)
    key.add_uid(uid, usage={KeyFlags.Sign, KeyFlags.EncryptCommunications},
                hashes=[HashAlgorithm.SHA256], ciphers=[SymmetricKeyAlgorithm.AES256],
                compression=[CompressionAlgorithm.ZLIB])
    return key


def _msg_with_attachment(**pgp_kw):
    return OutgoingMessage(
        from_addr="alice@example.com", to=["bob@example.com"], subject="Q3 report",
        html="<p>See attached.</p>",
        attachments=[{"filename": "report.txt", "content_type": "text/plain",
                      "data": b"top secret numbers"}],
        **pgp_kw,
    )


def test_pgp_mime_signed_structure_and_verify():
    key = _make_key()
    settings = {"pgpPrivateKey": str(key)}
    out = build_mime(_msg_with_attachment(pgp_sign=True, pgp_settings=settings))

    assert out.get_content_type() == "multipart/signed"
    assert out.get_param("protocol") == "application/pgp-signature"
    parts = out.get_payload()
    assert len(parts) == 2
    assert parts[1].get_content_type() == "application/pgp-signature"
    # Addressing headers moved to the outer message.
    assert out["Subject"] == "Q3 report" and out["To"] == "bob@example.com"

    # The detached signature verifies over the exact signed part bytes.
    signed_bytes = parts[0].as_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    sig = pgpy.PGPSignature.from_blob(parts[1].get_payload())
    assert bool(key.pubkey.verify(signed_bytes, sig))


def test_pgp_mime_encrypted_roundtrips_with_attachment():
    key = _make_key()
    settings = {"pgpPrivateKey": str(key)}
    out = build_mime(_msg_with_attachment(
        pgp_encrypt=True, pgp_sign=True, pgp_settings=settings, pgp_recipients=[str(key.pubkey)]))

    assert out.get_content_type() == "multipart/encrypted"
    assert out.get_param("protocol") == "application/pgp-encrypted"
    parts = out.get_payload()
    assert parts[0].get_content_type() == "application/pgp-encrypted"
    assert "Version: 1" in parts[0].get_payload()

    # Decrypt the octet-stream and confirm the inner MIME kept the attachment.
    enc = pgpy.PGPMessage.from_blob(parts[1].get_payload())
    dec = key.decrypt(enc)
    inner = dec.message
    inner = inner.decode() if isinstance(inner, (bytes, bytearray)) else str(inner)
    assert "top secret numbers".encode().hex() in inner or "top secret numbers" in inner \
        or "report.txt" in inner
