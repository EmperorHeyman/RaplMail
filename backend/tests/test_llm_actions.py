"""Composer rewrite (/ai/rewrite) and context Q&A (/ai/ask).

The provider call (_call_chat) is monkeypatched so no network/model is needed —
we assert the request the endpoints build (system prompt, context transcript,
history) and the keyless-Ollama gating, which is the logic worth pinning down.
"""
import pytest
from sqlmodel import Session

from app.api import ai as ai_mod
from app.core.db import get_engine
from app.models import Account, Folder, Message, Setting


def _s():
    return Session(get_engine())


def _set_provider(provider="ollama", key=""):
    with _s() as s:
        row = s.get(Setting, 1) or Setting(id=1, data={})
        row.data = {**(row.data or {}), "aiProvider": provider, "aiApiKey": key}
        s.add(row); s.commit()


@pytest.fixture
def capture(monkeypatch):
    """Replace _call_chat with a recorder that returns a canned answer."""
    calls = {}

    def fake(cfg, system, turns, max_tokens=700):
        calls["cfg"] = cfg
        calls["system"] = system
        calls["turns"] = turns
        calls["max_tokens"] = max_tokens
        return "MODEL_OUTPUT"

    monkeypatch.setattr(ai_mod, "_call_chat", fake)
    return calls


# --- /ai/rewrite ------------------------------------------------------------
def test_rewrite_returns_result(client, capture):
    _set_provider("ollama")
    r = client.post("/ai/rewrite", json={"text": "helo their", "action": "grammar"})
    assert r.status_code == 200
    assert r.json()["result"] == "MODEL_OUTPUT"
    # The grammar task is in the system prompt; the input text is the user turn.
    assert "grammar" in capture["system"].lower()
    assert capture["turns"][-1]["content"] == "helo their"


def test_rewrite_translate_includes_target_language(client, capture):
    _set_provider("ollama")
    client.post("/ai/rewrite", json={"text": "hello", "action": "translate", "instruction": "Czech"})
    assert "Czech" in capture["system"]


def test_rewrite_custom_uses_instruction(client, capture):
    _set_provider("ollama")
    client.post("/ai/rewrite", json={"text": "hello", "action": "custom",
                                     "instruction": "make it rhyme"})
    assert "make it rhyme" in capture["system"]


def test_rewrite_empty_text_400(client, capture):
    _set_provider("ollama")
    r = client.post("/ai/rewrite", json={"text": "   ", "action": "rephrase"})
    assert r.status_code == 400


def test_rewrite_requires_provider_key_for_cloud(client, capture):
    _set_provider("anthropic", key="")     # cloud provider, no key → blocked
    r = client.post("/ai/rewrite", json={"text": "hi", "action": "rephrase"})
    assert r.status_code == 400


def test_rewrite_ollama_is_keyless(client, capture):
    _set_provider("ollama", key="")        # local, keyless → allowed
    r = client.post("/ai/rewrite", json={"text": "hi", "action": "rephrase"})
    assert r.status_code == 200


# --- /ai/ask ----------------------------------------------------------------
_seed_n = 0


def _seed_message(subject="Server migration quote", body="The migration will cost 12000 CZK."):
    global _seed_n
    _seed_n += 1                       # unique per call (shared session-scoped DB)
    with _s() as s:
        acct = Account(email=f"ask{_seed_n}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        folder = Folder(account_id=acct.id, name="INBOX", path="INBOX")
        s.add(folder); s.commit(); s.refresh(folder)
        m = Message(account_id=acct.id, folder_id=folder.id, uid=1, message_id=f"<ask-{_seed_n}>",
                    from_addr="vendor@x.com", subject=subject, snippet=body)
        s.add(m); s.commit(); s.refresh(m)
        return m.id


def test_ask_builds_context_from_messages(client, capture):
    _set_provider("ollama")
    mid = _seed_message()
    r = client.post("/ai/ask", json={"instruction": "tldr", "message_ids": [mid]})
    assert r.status_code == 200
    assert r.json()["answer"] == "MODEL_OUTPUT"
    # The message content is injected into the system prompt as context.
    assert "Server migration quote" in capture["system"]
    assert "12000 CZK" in capture["system"]
    assert capture["turns"][-1] == {"role": "user", "content": "tldr"}


def test_ask_carries_history(client, capture):
    _set_provider("ollama")
    mid = _seed_message()
    client.post("/ai/ask", json={
        "instruction": "and in czech?", "message_ids": [mid],
        "history": [{"role": "user", "content": "tldr"},
                    {"role": "assistant", "content": "It's a quote."}],
    })
    roles = [t["role"] for t in capture["turns"]]
    assert roles == ["user", "assistant", "user"]
    assert capture["turns"][-1]["content"] == "and in czech?"


def test_ask_without_context_still_answers(client, capture):
    _set_provider("ollama")
    r = client.post("/ai/ask", json={"instruction": "hello"})
    assert r.status_code == 200
    assert "EMAILS" not in capture["system"]     # no context block when none given


def test_ask_empty_instruction_400(client, capture):
    _set_provider("ollama")
    r = client.post("/ai/ask", json={"instruction": "  "})
    assert r.status_code == 400


# --- /ai/search (natural-language → keywords) -------------------------------
def test_ai_search_extracts_keywords(client, monkeypatch):
    _set_provider("ollama")
    # Model may wrap output in quotes / extra lines; we take the first clean line.
    monkeypatch.setattr(ai_mod, "_call_chat", lambda *a, **k: '"audi crash plate"\n')
    r = client.post("/ai/search", json={"q": "najdi email kde se jedná o audi crash plate"})
    assert r.status_code == 200
    assert r.json()["query"] == "audi crash plate"


def test_ai_search_empty_400(client, capture):
    _set_provider("ollama")
    assert client.post("/ai/search", json={"q": "  "}).status_code == 400


# --- Live model search (parse ollama.com library links) --------------------
def test_parse_library_names_dedupes_in_order():
    html = ('<a href="/library/gemma3">..</a> <a href="/library/gemma4">..</a> '
            '<a href="/library/gemma3">dup</a> <a href="/library/qwen2.5">..</a>')
    assert ai_mod._parse_library_names(html) == ["gemma3", "gemma4", "qwen2.5"]


def test_ollama_search_endpoint(client, monkeypatch):
    monkeypatch.setattr(ai_mod, "_fetch_text",
                        lambda *a, **k: '<a href="/library/gemma3"></a><a href="/library/gemma4"></a>')
    r = client.get("/ai/ollama/search?q=gemma")
    assert r.status_code == 200
    assert r.json()["models"] == ["gemma3", "gemma4"]


def test_ollama_search_empty_query(client):
    assert client.get("/ai/ollama/search?q=").json()["models"] == []


# --- Ollama keep_alive typing (0/-1 must be numbers, not "missing unit" strings)
def test_keep_alive_number_vs_duration():
    assert ai_mod._keep_alive("adaptive") == -1
    assert ai_mod._keep_alive("-1") == -1
    assert ai_mod._keep_alive("0") == 0
    assert ai_mod._keep_alive("5m") == "5m"
    assert ai_mod._keep_alive("30s") == "30s"


# --- chips parsing (the "wtf is CHIPS" leak) --------------------------------
def test_split_chips_handles_malformed_marker():
    # The exact shape a small model produced (single-pipe, no closing ###).
    raw = ("Dear Jana,\n\nThank you. I'll take a look.\n\nBest regards, [Your Name]\n\n"
           "###CHIPS|Got it | Let me know if I have questions | I'll check it out today")
    draft, chips = ai_mod._split_chips(raw)
    assert "CHIPS" not in draft
    assert draft.endswith("[Your Name]")
    assert chips == ["Got it", "Let me know if I have questions", "I'll check it out today"]


def test_split_chips_canonical_and_colon_forms():
    d1, c1 = ai_mod._split_chips("Body text\n###CHIPS### a | b | c")
    assert d1 == "Body text" and c1 == ["a", "b", "c"]
    d2, c2 = ai_mod._split_chips("Body\nCHIPS: yes | no")
    assert d2 == "Body" and c2 == ["yes", "no"]


def test_split_chips_no_marker_and_no_false_positive():
    assert ai_mod._split_chips("Just a reply, no chips here.") == ("Just a reply, no chips here.", [])
    # The word "chips" in prose (no '#', not followed by ':'/'|') must not truncate.
    draft, chips = ai_mod._split_chips("I love fish and chips very much.")
    assert draft == "I love fish and chips very much." and chips == []


# --- draft reply: language instruction + clean chips ------------------------
def test_draft_reply_language_and_clean_chips(client, monkeypatch):
    _set_provider("ollama")
    mid = _seed_message(subject="Datovka", body="Ahoj, posílám info o Datovce. Díky!")

    def fake(cfg, system, turns, max_tokens=700):
        fake.system = system
        return "Ahoj Jano,\n\nDíky za info.\n\nS pozdravem\n###CHIPS|Rozumím | Ozvu se"
    monkeypatch.setattr(ai_mod, "_call_chat", fake)

    r = client.post("/ai/draft", json={"message_id": mid})
    assert r.status_code == 200
    body = r.json()
    assert "CHIPS" not in body["draft"]
    assert body["draft"].endswith("S pozdravem")
    assert body["chips"] == ["Rozumím", "Ozvu se"]
    assert "SAME LANGUAGE" in fake.system      # reply-in-thread-language instruction present
