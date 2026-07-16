"""S/MIME trust-chain verification: verify_chain walks a signer cert's issuer
links to a trusted root in the CA store. A leaf issued by a CA that is in the
store verifies; a self-signed cert that is not in the store does not.
"""
import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.sync import smime


def _name(cn):
    return x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])


def _mk_cert(subject_cn, issuer_cn, issuer_key, subject_key, ca=False):
    now = datetime.datetime.now(datetime.timezone.utc)
    builder = (x509.CertificateBuilder()
               .subject_name(_name(subject_cn))
               .issuer_name(_name(issuer_cn))
               .public_key(subject_key.public_key())
               .serial_number(x509.random_serial_number())
               .not_valid_before(now - datetime.timedelta(days=1))
               .not_valid_after(now + datetime.timedelta(days=365)))
    if ca:
        builder = builder.add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
    return builder.sign(issuer_key, hashes.SHA256())


def test_chain_verifies_to_injected_root(monkeypatch):
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_cert = _mk_cert("Test Root CA", "Test Root CA", ca_key, ca_key, ca=True)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_cert = _mk_cert("alice@example.com", "Test Root CA", ca_key, leaf_key)

    # Trust our own CA (stand-in for a certifi root).
    monkeypatch.setattr(smime, "_trust_roots", [ca_cert])
    assert smime.verify_chain(leaf_cert, []) is True
    # Chain also resolves when the CA is supplied as an intermediate.
    monkeypatch.setattr(smime, "_trust_roots", [ca_cert])
    assert smime.verify_chain(leaf_cert, [ca_cert]) is True


def test_untrusted_self_signed_does_not_verify(monkeypatch):
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_cert = _mk_cert("Test Root CA", "Test Root CA", ca_key, ca_key, ca=True)
    stray_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    stray = _mk_cert("mallory@example.com", "mallory@example.com", stray_key, stray_key)

    monkeypatch.setattr(smime, "_trust_roots", [ca_cert])   # store does NOT contain the stray
    assert smime.verify_chain(stray, []) is False


def test_no_trust_store_returns_false(monkeypatch):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    cert = _mk_cert("x@example.com", "x@example.com", key, key)
    monkeypatch.setattr(smime, "_trust_roots", [])
    assert smime.verify_chain(cert, []) is False
