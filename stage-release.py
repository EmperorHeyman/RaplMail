"""Stage a RaplMail release for the website (raplmail.em-production.eu).

    .\\backend\\.venv\\Scripts\\python.exe stage-release.py           # version from tauri.conf.json
    .\\backend\\.venv\\Scripts\\python.exe stage-release.py 0.9.22

Run it after `build-desktop.ps1 -Release` (which signs the installers). It checks
every signature against the public key the installed apps trust (tauri.conf.json)
and refuses to stage anything that wouldn't install, then writes site-dist/:

    site-dist/                    the website (copied from site/)
    site-dist/updates/latest.json what the app's updater reads (+ the download links for the page)
    site-dist/updates/changelog.json   recent versions, for "What's new" on the page
    site-dist/download/           the installers

Upload site-dist/ to the subdomain's web root. Keep the old installers on the
server: a link someone saved keeps working, and you can roll back by pointing
latest.json at an older version again.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

ROOT = Path(__file__).resolve().parent
SITE_URL = "https://raplmail.em-production.eu"
CONF = ROOT / "frontend" / "src-tauri" / "tauri.conf.json"
BUNDLE = ROOT / "frontend" / "src-tauri" / "target" / "release" / "bundle"
CHANGELOG_VERSIONS = 12          # how many versions "What's new" on the page shows


class ReleaseError(Exception):
    pass


# --- minisign (what the Tauri updater checks) --------------------------------

def _minisign_lines(blob_b64: str) -> list[str]:
    return base64.b64decode(blob_b64).decode("utf-8").strip().splitlines()


def verify_signature(data: bytes, sig_b64: str, pubkey_b64: str) -> None:
    """Raise ReleaseError unless `sig_b64` (the .sig file, as Tauri writes it) is a
    valid signature of `data` by `pubkey_b64` (the pubkey in tauri.conf.json)."""
    pk = base64.b64decode(_minisign_lines(pubkey_b64)[1])
    if len(pk) != 42 or pk[:2] != b"Ed":
        raise ReleaseError("the public key in tauri.conf.json isn't a minisign Ed25519 key")
    key_id, key = pk[2:10], Ed25519PublicKey.from_public_bytes(pk[10:])

    lines = _minisign_lines(sig_b64)
    if len(lines) < 4 or not lines[2].startswith("trusted comment: "):
        raise ReleaseError("the .sig file isn't a minisign signature")
    sig = base64.b64decode(lines[1])
    if len(sig) != 74 or sig[:2] not in (b"Ed", b"ED"):
        raise ReleaseError("unknown signature algorithm in the .sig file")
    if sig[2:10] != key_id:
        raise ReleaseError("signed with a different key than the one the app trusts "
                           "(frontend/src-tauri/.tauri-updater.key doesn't match tauri.conf.json)")
    message = hashlib.blake2b(data, digest_size=64).digest() if sig[:2] == b"ED" else data
    try:
        key.verify(sig[10:], message)
        # the trusted comment is signed too (signature + comment text)
        key.verify(base64.b64decode(lines[3]), sig[10:] + lines[2][len("trusted comment: "):].encode("utf-8"))
    except InvalidSignature as exc:
        raise ReleaseError("the signature doesn't match the file") from exc


# --- changelog -----------------------------------------------------------------

_HEAD = re.compile(r"^## \[(\d+\.\d+\.\d+)\](?:\s*-\s*(\d{4}-\d{2}-\d{2}))?\s*$")


def _plain(text: str) -> str:
    """Markdown inline -> plain text (bold, code, links)."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text.strip()


def parse_changelog(md: str) -> list[dict]:
    """[{version, date, sections: [{title, items: [{lead, text}]}]}], newest first."""
    out: list[dict] = []
    cur = sec = None
    for line in md.splitlines():
        m = _HEAD.match(line)
        if m:
            cur = {"version": m.group(1), "date": m.group(2) or "", "sections": []}
            out.append(cur)
            sec = None
            continue
        if line.startswith("## "):          # [Unreleased] and anything else
            cur = sec = None
            continue
        if cur is None:
            continue
        if line.startswith("### "):
            sec = {"title": line[4:].strip(), "items": []}
            cur["sections"].append(sec)
        elif line.startswith("- ") and sec is not None:
            sec["items"].append(line[2:].strip())
        elif line.startswith("  ") and line.strip() and sec is not None and sec["items"]:
            prev = sec["items"][-1]                       # a wrapped point
            glue = "" if re.search(r"\w-$", prev) else " "   # "ready-to-" + "copy"
            sec["items"][-1] = prev + glue + line.strip()
    for v in out:
        for s in v["sections"]:
            s["items"] = [_item(i) for i in s["items"]]
    return out


def _item(md: str) -> dict:
    """A point as {lead, text}: its bold opening ("**Turn AI off completely.**") and the rest."""
    m = re.match(r"\*\*(.+?)\*\*\s*(.*)$", md)
    if m:
        return {"lead": _plain(m.group(1)), "text": _plain(m.group(2))}
    return {"lead": "", "text": _plain(md)}


def notes_text(entry: dict) -> str:
    """The release notes as the app shows them: section titles and "- " points."""
    parts = []
    for s in entry["sections"]:
        parts.append(s["title"])
        parts.extend("- " + " ".join(x for x in (i["lead"], i["text"]) if x) for i in s["items"])
    return "\n".join(parts)


# --- staging -------------------------------------------------------------------

def stage(version: str, out: Path) -> dict:
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    pubkey = conf["plugins"]["updater"]["pubkey"]
    feed = conf["plugins"]["updater"]["endpoints"][0]
    if feed != f"{SITE_URL}/updates/latest.json":
        raise ReleaseError(f"tauri.conf.json points the updater at {feed}, not {SITE_URL}/updates/latest.json")

    files = {
        "nsis": BUNDLE / "nsis" / f"RaplMail_{version}_x64-setup.exe",
        "msi": BUNDLE / "msi" / f"RaplMail_{version}_x64_en-US.msi",
    }
    signed = {}
    for kind, path in files.items():
        sig_path = path.with_name(path.name + ".sig")
        if not path.exists():
            raise ReleaseError(f"missing {path} - build {version} first (build-desktop.ps1 -Version {version} -Release)")
        if not sig_path.exists():
            raise ReleaseError(f"missing {sig_path.name} - the build wasn't signed (use build-desktop.ps1 -Release)")
        data = path.read_bytes()
        sig = sig_path.read_text(encoding="utf-8").strip()
        verify_signature(data, sig, pubkey)
        signed[kind] = {"path": path, "sig": sig, "size": len(data),
                        "sha256": hashlib.sha256(data).hexdigest()}

    log = parse_changelog((ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    entry = next((v for v in log if v["version"] == version), None)
    if entry is None or not entry["sections"]:
        raise ReleaseError(f"CHANGELOG.md has no \"## [{version}]\" section - write the release notes first")

    if out.exists():
        shutil.rmtree(out)
    # the pages' templates and generator stay out of the upload
    shutil.copytree(ROOT / "site", out, ignore=shutil.ignore_patterns("*.template.html", "build-site.mjs", "msym-site.mjs"))
    (out / "download").mkdir(exist_ok=True)
    (out / "updates").mkdir(exist_ok=True)
    for s in signed.values():
        shutil.copy2(s["path"], out / "download" / s["path"].name)
    # /download/ always hands out the newest installer - a link that never goes stale
    # (and what the page's download button points at without JavaScript). The rule
    # lives in the root .htaccess: a download/.htaccess of its own would take that
    # folder over, and Apache's own slash redirect there says http:// (it can't see
    # the TLS proxy), which Chrome blocks for downloads.
    ht = out / ".htaccess"
    text = ht.read_text(encoding="utf-8")
    if "__LATEST_SETUP__" not in text:
        raise ReleaseError("site/.htaccess lost its __LATEST_SETUP__ download rule")
    ht.write_text(text.replace("__LATEST_SETUP__", signed["nsis"]["path"].name), encoding="utf-8")

    url = lambda kind: f"{SITE_URL}/download/{signed[kind]['path'].name}"   # noqa: E731
    pub_date = (datetime.strptime(entry["date"], "%Y-%m-%d").replace(hour=12, tzinfo=timezone.utc)
                if entry["date"] else datetime.now(timezone.utc))
    latest = {
        "version": version,
        "notes": notes_text(entry),
        "pub_date": pub_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        # What the updater installs: the setup.exe for installs made with it, the
        # MSI for MSI installs; plain "windows-x86_64" is the fallback.
        "platforms": {
            "windows-x86_64": {"signature": signed["nsis"]["sig"], "url": url("nsis")},
            "windows-x86_64-nsis": {"signature": signed["nsis"]["sig"], "url": url("nsis")},
            "windows-x86_64-msi": {"signature": signed["msi"]["sig"], "url": url("msi")},
        },
        # For the website's download buttons (the updater ignores this).
        "downloads": {k: {"url": url(k), "file": s["path"].name, "size": s["size"], "sha256": s["sha256"]}
                      for k, s in signed.items()},
    }
    (out / "updates" / "latest.json").write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")
    recent = [v for v in log if v["sections"]][:CHANGELOG_VERSIONS]
    (out / "updates" / "changelog.json").write_text(json.dumps(recent, ensure_ascii=False, indent=1), encoding="utf-8")
    return latest


def main() -> int:
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    version = sys.argv[1] if len(sys.argv) > 1 else conf["version"]
    out = ROOT / "site-dist"
    try:
        latest = stage(version, out)
    except ReleaseError as exc:
        print(f"Not staged: {exc}", file=sys.stderr)
        return 1
    print(f"Staged RaplMail {version} in {out}")
    print("  signatures: OK (match the key in tauri.conf.json)")
    for k, d in latest["downloads"].items():
        print(f"  {k:5} {d['file']}  {d['size'] / 1e6:.1f} MB")
    print(f"Upload everything in {out.name}/ to the web root of {SITE_URL}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
