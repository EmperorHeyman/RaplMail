"""CalDAV write round-trip against a REAL DAV server (Radicale).

Boots Radicale in a subprocess on a random localhost port (filesystem storage
in a temp dir, auth "none" so any user/password pair is accepted), creates a
calendar collection via MKCALENDAR, PUTs an event with the new put_event,
reads it back through the existing REPORT-based fetch_events, then deletes it
with delete_event and verifies it is gone. Skips if radicale is not installed
(pip install -r requirements-dev.txt).
"""

import base64
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone

import pytest

try:
    import radicale  # noqa: F401
    _HAVE_RADICALE = True
except ImportError:
    _HAVE_RADICALE = False

pytestmark = pytest.mark.skipif(
    not _HAVE_RADICALE, reason="radicale not installed (pip install -r requirements-dev.txt)")

_USER, _PW = "alice", "secret"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _mkcalendar(url: str) -> None:
    token = base64.b64encode(f"{_USER}:{_PW}".encode()).decode("ascii")
    req = urllib.request.Request(url, method="MKCALENDAR",
                                 headers={"Authorization": f"Basic {token}"})
    with urllib.request.urlopen(req, timeout=10):
        pass


@pytest.fixture(scope="module")
def dav_url(tmp_path_factory):
    """A running Radicale instance; yields the calendar collection URL."""
    storage = tmp_path_factory.mktemp("radicale-storage")
    port = _free_port()
    proc = subprocess.Popen(
        [sys.executable, "-m", "radicale",
         "--server-hosts", f"127.0.0.1:{port}",
         "--storage-filesystem-folder", str(storage),
         "--auth-type", "none"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.time() + 30
        while True:
            if proc.poll() is not None:
                # Radicale's multifilesystem storage does atomic renames that
                # need symlink privileges on Windows (WinError 1314) unless the
                # process is elevated / Developer Mode is on. That's an
                # environment limitation, not a fault in the code under test, so
                # skip cleanly - the round-trip still runs anywhere Radicale boots
                # (Linux CI, elevated shells).
                pytest.skip(f"radicale could not start in this environment (rc={proc.returncode})")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                if time.time() > deadline:
                    pytest.skip("radicale did not open its port within 30s")
                time.sleep(0.2)
        cal_url = f"http://127.0.0.1:{port}/{_USER}/testcal/"
        _mkcalendar(cal_url)
        yield cal_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


def test_put_fetch_delete_roundtrip(dav_url):
    from app.api.calendar import _build_event_ics
    from app.sync import caldav as dav

    uid = "raplmail-roundtrip-test@raplmail"
    start = datetime(2026, 8, 20, 9, 30, tzinfo=timezone.utc)
    end = datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc)
    ics = _build_event_ics(uid, "DAV round trip", start, end, False,
                           "HQ", "written by test", "me@example.com", "me@example.com")
    # Mirror the create_event write path: object PUTs are plain calendar data,
    # so the iTIP METHOD line is stripped before upload.
    ics = "\r\n".join(ln for ln in ics.split("\r\n") if not ln.startswith("METHOD:"))

    import urllib.parse
    obj_url = dav.put_event(dav_url, _USER, _PW, uid, ics)
    # put_event percent-encodes the uid into the object path.
    assert obj_url == f"{dav_url}{urllib.parse.quote(uid, safe='')}.ics"

    # Read back through the production REPORT path, not the raw file.
    events = dav.fetch_events(dav_url, _USER, _PW)
    match = [e for e in events if e.get("uid") == uid]
    assert len(match) == 1
    assert match[0]["summary"] == "DAV round trip"
    assert match[0]["location"] == "HQ"
    assert match[0]["start"] == start
    assert match[0]["end"] == end

    assert dav.delete_event(dav_url, _USER, _PW, uid) is True
    events = dav.fetch_events(dav_url, _USER, _PW)
    assert not [e for e in events if e.get("uid") == uid]
    # Deleting an already-gone object (404) still counts as success.
    assert dav.delete_event(dav_url, _USER, _PW, uid) is True
