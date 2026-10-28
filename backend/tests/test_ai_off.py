"""Settings -> AI assistant -> "Use AI" off: nothing AI runs - chat endpoints are
refused, Ollama isn't warmed, no briefing, no smart-search indexing - while the
Ollama status / unload calls keep working (turning AI off frees the GPU)."""
import pytest
from sqlmodel import Session

from app.core.db import get_engine
from app.models import Setting
from app.sync import embeddings
from app.sync.engine import SyncManager


def _blob():
    with Session(get_engine()) as s:
        row = s.get(Setting, 1)
        return dict(row.data) if row and row.data else None


def _restore(data):
    with Session(get_engine()) as s:
        row = s.get(Setting, 1)
        if data is None:
            if row is not None:
                s.delete(row)
        else:
            row = row or Setting(id=1, data={})
            row.data = data
            s.add(row)
        s.commit()


@pytest.fixture(autouse=True)
def _keep_settings():
    before = _blob()
    yield
    _restore(before)


def _set(**patch):
    with Session(get_engine()) as s:
        row = s.get(Setting, 1)
        data = dict(row.data) if row and row.data else {}
        data.update(patch)
        if row is None:
            s.add(Setting(id=1, data=data))
        else:
            row.data = data
            s.add(row)
        s.commit()


@pytest.fixture
def ai_off():
    _set(aiOn=False, digestEnabled=True, semanticEnabled=True, aiProvider="ollama")


def test_chat_endpoints_are_refused(client, ai_off):
    for path, body in (("/ai/summarize", {"message_id": 1}), ("/ai/ask", {"instruction": "hi"}),
                       ("/ai/search", {"query": "invoices"})):
        r = client.post(path, json=body)
        assert r.status_code == 409, (path, r.status_code)
        assert "turned off" in r.json()["detail"]


def test_ollama_is_not_warmed(client, ai_off):
    assert client.post("/ai/ollama/warm").json() == {"warmed": False}


def test_background_ai_work_stops(ai_off):
    enabled, _hour, _day = SyncManager._digest_settings(SyncManager.__new__(SyncManager))
    assert enabled is False
    with Session(get_engine()) as s:
        assert embeddings._embed_config(s)["enabled"] is False


def test_status_still_answers_while_off(client, ai_off):
    # Settings must still be able to show Ollama's state and free the GPU.
    assert client.get("/ai/status").status_code == 200


def test_back_on_works(client):
    _set(aiOn=True)
    assert client.post("/ai/ask", json={"instruction": "hi"}).status_code != 409
