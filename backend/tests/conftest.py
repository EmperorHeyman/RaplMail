"""Shared test fixtures.

Boots the FastAPI app against a throwaway temp data dir (its own SQLite DB +
secret store) so the e2e tests never touch the user's real mailbox/settings.
RAPLMAIL_DEV=1 disables the auth token so tests can call endpoints directly.
"""

import os
import tempfile

# Must be set BEFORE app modules import (config is read at import time).
os.environ["RAPLMAIL_DEV"] = "1"
os.environ.setdefault("RAPLMAIL_DATA_DIR", tempfile.mkdtemp(prefix="raplmail-test-"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c
