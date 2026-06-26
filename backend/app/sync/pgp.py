"""OpenPGP support: detect / verify / decrypt incoming mail and sign+encrypt
outgoing mail, using the user's keys from the local settings blob.

Keys never leave the machine. Uses pgpy (pure-python OpenPGP). Handles inline
PGP (ASCII-armored body) and PGP/MIME (multipart/signed, multipart/encrypted).
Everything is best-effort: any failure degrades to "not verified" rather than
breaking the message view.
"""

from __future__ import annotations

import warnings

warnings.filterwarnings("ignore")  # pgpy emits noisy crypto deprecation warnings

try:
    import pgpy  # noqa: E402
    _AVAILABLE = True
except Exception:  # pragma: no cover - pgpy optional
    _AVAILABLE = False


def available() -> bool:
    return _AVAILABLE


def _load_pub(armored: str):
    try:
        k, _ = pgpy.PGPKey.from_blob(armored)
        return k
    except Exception:
        return None


def load_keystore(settings: dict) -> tuple[object | None, list, str]:
    """(private_key | None, [public_keys], passphrase) from the settings blob."""
    if not _AVAILABLE:
        return None, [], ""
    priv = None
    pw = str(settings.get("pgpPassphrase") or "")
    if settings.get("pgpPrivateKey"):
        priv = _load_pub(settings["pgpPrivateKey"])
    pubs = []
    for blob in settings.get("pgpPublicKeys") or []:
        k = _load_pub(blob)
        if k is not None:
            pubs.append(k)
    # The private key's own public half is a valid verification key too.
    if priv is not None:
        pubs.append(priv.pubkey if priv.is_public is False else priv)
    return priv, pubs, pw


def detect(content_type: str, text_body: str) -> str:
    """Cheap classification: 'encrypted' | 'signed' | ''."""
    ct = (content_type or "").lower()
    if "multipart/encrypted" in ct or "application/pgp-encrypted" in ct:
        return "encrypted"
    if "multipart/signed" in ct and "pgp" in ct:
        return "signed"
    t = text_body or ""
    if "-----BEGIN PGP MESSAGE-----" in t:
        return "encrypted"
    if "-----BEGIN PGP SIGNED MESSAGE-----" in t:
        return "signed"
    return ""


def _verify_clearsigned(text: str, pubs: list) -> tuple[bool, str]:
    try:
        msg = pgpy.PGPMessage.from_blob(text)
    except Exception:
        return False, ""
    for k in pubs:
        try:
            if k.verify(msg):
                uid = next(iter(k.userids), None)
                return True, (uid.email if uid else str(k.fingerprint)[-8:])
        except Exception:
            continue
    return False, ""


def analyze(content_type: str, text_body: str, settings: dict) -> dict:
    """Inspect a message: returns {type, verified, signer, decrypted}.
    `decrypted` is set (plain text) when we could decrypt an encrypted body."""
    kind = detect(content_type, text_body)
    if not kind or not _AVAILABLE:
        return {"type": kind, "verified": None, "signer": "", "decrypted": None}

    priv, pubs, pw = load_keystore(settings)
    out = {"type": kind, "verified": None, "signer": "", "decrypted": None}

    if kind == "signed":
        ok, signer = _verify_clearsigned(text_body, pubs)
        out["verified"], out["signer"] = ok, signer
        return out

    # encrypted (inline)
    if "-----BEGIN PGP MESSAGE-----" in (text_body or "") and priv is not None:
        try:
            enc = pgpy.PGPMessage.from_blob(text_body)
            with (priv.unlock(pw) if priv.is_protected else _NullCtx(priv)) as k:
                dec = k.decrypt(enc)
            body = dec.message
            out["decrypted"] = body.decode() if isinstance(body, bytes) else str(body)
            # Decrypted payload may itself be signed.
            if getattr(dec, "is_signed", False):
                for k2 in pubs:
                    try:
                        if k2.verify(dec):
                            out["verified"] = True
                            uid = next(iter(k2.userids), None)
                            out["signer"] = uid.email if uid else ""
                            break
                    except Exception:
                        continue
        except Exception:
            pass
    return out


class _NullCtx:
    """Lets `with` work uniformly for unprotected keys."""
    def __init__(self, k):
        self.k = k

    def __enter__(self):
        return self.k

    def __exit__(self, *a):
        return False


def pubkeys_for(emails: list[str], settings: dict) -> list[str]:
    """Armored public keys whose UID email matches one of `emails`."""
    if not _AVAILABLE:
        return []
    wanted = {(e or "").strip().lower() for e in emails if e}
    out = []
    for blob in settings.get("pgpPublicKeys") or []:
        k = _load_pub(blob)
        if k is None:
            continue
        for uid in k.userids:
            if (uid.email or "").lower() in wanted:
                out.append(blob)
                break
    return out


def have_keys_for(emails: list[str], settings: dict) -> bool:
    return bool(pubkeys_for(emails, settings))


def sign_and_encrypt(plaintext: str, settings: dict, recipients_armored: list[str],
                     do_sign: bool, do_encrypt: bool) -> str | None:
    """Produce an inline ASCII-armored PGP body, or None if it can't be done."""
    if not _AVAILABLE or not (do_sign or do_encrypt):
        return None
    priv, _pubs, pw = load_keystore(settings)
    msg = pgpy.PGPMessage.new(plaintext)
    try:
        if do_sign and priv is not None:
            with (priv.unlock(pw) if priv.is_protected else _NullCtx(priv)) as k:
                msg |= k.sign(msg)
        if do_encrypt:
            keys = [_load_pub(a) for a in recipients_armored]
            keys = [k for k in keys if k is not None]
            if not keys:
                return None
            if len(keys) == 1:
                enc = keys[0].pubkey.encrypt(msg) if keys[0].is_public is False else keys[0].encrypt(msg)
            else:
                # multi-recipient: use a session key
                from pgpy.constants import SymmetricKeyAlgorithm
                cipher = SymmetricKeyAlgorithm.AES256
                sk = cipher.gen_key()
                enc = msg
                for k in keys:
                    enc = k.encrypt(enc, cipher=cipher, sessionkey=sk)
                del sk
            return str(enc)
        return str(msg)
    except Exception:
        return None
