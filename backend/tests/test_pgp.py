"""OpenPGP verify / decrypt / sign+encrypt round-trip tests."""

import warnings

warnings.filterwarnings("ignore")

import pytest  # noqa: E402

pgpy = pytest.importorskip("pgpy")
from pgpy.constants import (  # noqa: E402
    CompressionAlgorithm, HashAlgorithm, KeyFlags, PubKeyAlgorithm, SymmetricKeyAlgorithm,
)

from app.sync import pgp  # noqa: E402


def _make_key(email="alice@example.com"):
    key = pgpy.PGPKey.new(PubKeyAlgorithm.RSAEncryptOrSign, 2048)
    uid = pgpy.PGPUID.new("Alice", email=email)
    key.add_uid(uid, usage={KeyFlags.Sign, KeyFlags.EncryptCommunications},
                hashes=[HashAlgorithm.SHA256], ciphers=[SymmetricKeyAlgorithm.AES256],
                compression=[CompressionAlgorithm.ZLIB])
    return key


def test_detect():
    assert pgp.detect("multipart/encrypted; protocol=\"application/pgp-encrypted\"", "") == "encrypted"
    assert pgp.detect("text/plain", "-----BEGIN PGP MESSAGE-----\n...") == "encrypted"
    assert pgp.detect("text/plain", "-----BEGIN PGP SIGNED MESSAGE-----") == "signed"
    assert pgp.detect("text/plain", "just a normal email") == ""


def test_verify_clearsigned():
    key = _make_key()
    msg = pgpy.PGPMessage.new("Contract agreed.", cleartext=True)
    msg |= key.sign(msg)
    settings = {"pgpPublicKeys": [str(key.pubkey)]}
    res = pgp.analyze("text/plain", str(msg), settings)
    assert res["type"] == "signed"
    assert res["verified"] is True
    assert "alice@example.com" in res["signer"]


def test_decrypt_inline():
    key = _make_key()
    enc = key.pubkey.encrypt(pgpy.PGPMessage.new("the secret password is hunter2"))
    settings = {"pgpPrivateKey": str(key)}
    res = pgp.analyze("text/plain", str(enc), settings)
    assert res["type"] == "encrypted"
    assert "hunter2" in (res["decrypted"] or "")


def test_sign_and_encrypt_roundtrip():
    key = _make_key()
    settings = {"pgpPrivateKey": str(key)}
    armored = pgp.sign_and_encrypt("hello pgp world", settings,
                                   recipients_armored=[str(key.pubkey)],
                                   do_sign=True, do_encrypt=True)
    assert armored and "BEGIN PGP MESSAGE" in armored
    # decrypt it back
    dec = key.decrypt(pgpy.PGPMessage.from_blob(armored))
    body = dec.message
    assert "hello pgp world" in (body.decode() if isinstance(body, bytes) else str(body))
