"""Composer rewrite (/ai/rewrite) and context Q&A (/ai/ask).

The provider call (_call_chat) is monkeypatched so no network/model is needed -
we assert the request the endpoints build (system prompt, context transcript,
history) and the keyless-Ollama gating, which is the logic worth pinning down.
"""
import pytest
from sqlmodel import Session

from app.api import ai as ai_mod
from app.core.db import get_engine
from app.models import Account, Folder, FolderRole, Message, Setting


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


# --- /ai/agent (answer OR propose a confirmed mailbox action) ---------------
def test_parse_action_reads_op_and_filters():
    p = ai_mod._parse_action("ACTION: mark_seen unread")
    assert p == {"op": "mark_seen", "action": "seen", "filters": {"unread": True}}
    p2 = ai_mod._parse_action("ACTION: archive from:noreply@x.com")
    assert p2["action"] == "archive" and p2["filters"] == {"from": "noreply@x.com"}


def test_parse_action_handles_quotes_and_fences():
    p = ai_mod._parse_action('```\nACTION: delete unread subject:"big sale"\n```')
    assert p["action"] == "delete"
    assert p["filters"] == {"subject": "big sale", "unread": True}


def test_parse_action_none_for_prose_and_unknown_ops():
    # A normal answer that merely mentions the word must not become an action.
    assert ai_mod._parse_action("Here's a summary.\nNo ACTION: needed here.") is None
    assert ai_mod._parse_action("ACTION: teleport all mail") is None   # unknown op
    assert ai_mod._parse_action("Just a plain reply.") is None


def _seed_inbox_unread(subject, n):
    """Seed n unread messages in an inbox-ROLE folder (agent scopes to inbox)."""
    global _seed_n
    _seed_n += 1
    ids = []
    with _s() as s:
        acct = Account(email=f"agent{_seed_n}@example.com"); s.add(acct); s.commit(); s.refresh(acct)
        folder = Folder(account_id=acct.id, name="INBOX", path="INBOX", role=FolderRole.inbox)
        s.add(folder); s.commit(); s.refresh(folder)
        for i in range(n):
            m = Message(account_id=acct.id, folder_id=folder.id, uid=100 + i,
                        message_id=f"<agent-{_seed_n}-{i}>", from_addr="v@x.com",
                        subject=subject, snippet="body", is_seen=False)
            s.add(m); s.commit(); s.refresh(m); ids.append(m.id)
    return ids


def test_agent_proposes_resolved_action(client, monkeypatch):
    _set_provider("ollama")
    # A distinctive subject so resolution matches exactly the rows we seed
    # (the DB is shared across tests, so filter to our own mail).
    ids = _seed_inbox_unread("zzagentmark", 3)
    monkeypatch.setattr(ai_mod, "_call_chat", lambda *a, **k: "ACTION: mark_seen subject:zzagentmark")
    r = client.post("/ai/agent", json={"instruction": "mark those as read"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "action"
    assert body["action"] == "seen"
    assert body["count"] == 3
    assert set(ids).issubset(set(body["ids"]))
    assert len(body["sample"]) == 3


def test_agent_answers_normally_without_action(client, monkeypatch):
    _set_provider("ollama")
    monkeypatch.setattr(ai_mod, "_call_chat", lambda *a, **k: "You press E to mark a message done.")
    r = client.post("/ai/agent", json={"instruction": "how do I mark something done?"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "answer"
    assert "E to mark" in body["answer"]


def test_agent_empty_instruction_400(client):
    _set_provider("ollama")
    assert client.post("/ai/agent", json={"instruction": "  "}).status_code == 400


# --- /ai/agent: a weak model leaking ANSWER/ACT/RULE labels into a plain answer
# The exact "vomit" a small local model produced for "shrň mi nové maily": prose
# prefixed with ANSWER: plus tacked-on ACT:/RULE:/MAKE A RULE: lines. None of that
# scaffolding may reach the user; the answer is just the prose.
_VOMIT = (
    "ANSWER: Tento email obsahuje styly pro webovou stranku, kterymi se nastavuji "
    "vzhled pisma OpenAI Sans.\n\n"
    "ACT: archivovat email\n"
    'RULE: {"field":"subject","op":"contains","value":"[OpenAI Sans]","action":"archive","arg":""}\n\n'
    "MAKE A RULE: Kdyz budete chapat vetsinu svych e-mailu s pismem OpenAI, mohlo by "
    "to pomoci automaticke archivovani.\n"
    'RULE: {"field":"subject","op":"contains","value":"[OpenAI]","action":"archive","arg":""}'
)


def test_clean_answer_strips_leaked_protocol():
    out = ai_mod._clean_answer(_VOMIT)
    assert out.startswith("Tento email obsahuje styly")   # ANSWER: prefix removed
    for junk in ("ANSWER:", "ACT:", "RULE:", "MAKE A RULE:", "{", "archive"):
        assert junk not in out


def test_clean_answer_leaves_normal_prose_untouched():
    plain = "You press E to mark a message done.\nUse the slider to see done mail."
    assert ai_mod._clean_answer(plain) == plain
    # A word like "act" or "rules" in prose (not a line-leading directive) survives.
    prose = "These rules act on new mail. Ruleset is in Settings."
    assert ai_mod._clean_answer(prose) == prose


def test_agent_answer_is_sanitized_end_to_end(client, monkeypatch):
    _set_provider("ollama")
    monkeypatch.setattr(ai_mod, "_call_chat", lambda *a, **k: _VOMIT)
    r = client.post("/ai/agent", json={"instruction": "shrn mi nove maily"})
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "answer"                       # a summary is NOT an action
    assert body["answer"].startswith("Tento email obsahuje styly")
    for junk in ("ANSWER:", "ACT:", "RULE:", "MAKE A RULE:"):
        assert junk not in body["answer"]


# --- /ai/agent: propose a filtering RULE ------------------------------------
def test_parse_rule_contains():
    p = ai_mod._parse_rule('RULE: {"field":"subject","op":"contains","value":"[ZERV] Daily Report","action":"mark_done","arg":"","name":"ZERV"}')
    assert p["match_field"] == "subject" and p["match_op"] == "contains"
    assert p["match_value"] == "[ZERV] Daily Report" and p["action"] == "mark_done"


def test_parse_rule_regex_validated():
    ok = ai_mod._parse_rule('RULE: {"field":"subject","op":"regex","value":"\\\\[ZERV\\\\]","action":"mark_done"}')
    assert ok and ok["match_op"] == "regex" and ok["match_value"] == r"\[ZERV\]"
    # An un-compilable pattern is rejected rather than saved as a dead rule.
    assert ai_mod._parse_rule('RULE: {"field":"subject","op":"regex","value":"[unclosed","action":"mark_done"}') is None


def test_parse_rule_rejects_bad_vocab_and_prose():
    assert ai_mod._parse_rule('RULE: {"field":"nope","op":"contains","value":"x","action":"mark_done"}') is None
    assert ai_mod._parse_rule('RULE: {"field":"subject","op":"contains","value":"x","action":"teleport"}') is None
    assert ai_mod._parse_rule("Sure, here's how rules work in RaplMail...") is None


def test_agent_proposes_rule(client, monkeypatch):
    _set_provider("ollama")
    monkeypatch.setattr(ai_mod, "_call_chat",
                        lambda *a, **k: 'RULE: {"field":"subject","op":"contains","value":"ZERV","action":"mark_done","arg":"","name":"z"}')
    r = client.post("/ai/agent", json={"instruction": "always mark the zerv report done"})
    assert r.status_code == 200
    b = r.json()
    assert b["kind"] == "rule"
    assert b["rule"]["match_field"] == "subject" and b["rule"]["action"] == "mark_done"


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


# --- mistral-friendly output unwrapping (rewrite/translate) -----------------
# Small models ignore "output ONLY the text" and wrap it in fences / quotes / a
# "Sure, here's..." preamble. _unwrap_output strips those so the composer gets
# clean text.
def test_unwrap_output_strips_fences_quotes_preamble():
    assert ai_mod._unwrap_output("```\nHello there\n```") == "Hello there"
    assert ai_mod._unwrap_output("```text\nHello there\n```") == "Hello there"
    assert ai_mod._unwrap_output('"Hello there"') == "Hello there"
    assert ai_mod._unwrap_output("Sure, here's the rewritten text:\nHello there") == "Hello there"
    assert ai_mod._unwrap_output("Here is the translation:\nAhoj") == "Ahoj"


def test_unwrap_output_preserves_clean_text_and_inner_quotes():
    assert ai_mod._unwrap_output("Hello there") == "Hello there"
    assert ai_mod._unwrap_output('He said "hi" to me') == 'He said "hi" to me'
    assert ai_mod._unwrap_output("") == ""


def test_rewrite_unwraps_model_wrapping(client, monkeypatch):
    _set_provider("ollama")
    monkeypatch.setattr(ai_mod, "_call_chat", lambda *a, **k: "```\nDear Jana, thank you.\n```")
    r = client.post("/ai/rewrite", json={"text": "dear jana thx", "action": "improve"})
    assert r.status_code == 200
    assert r.json()["result"] == "Dear Jana, thank you."


# --- /ai/summarize ----------------------------------------------------------
def test_summarize_builds_prompt_and_returns(client, capture):
    _set_provider("ollama")
    mid = _seed_message(subject="Quarterly numbers", body="Revenue up 12 percent this quarter.")
    r = client.post("/ai/summarize", json={"message_id": mid})
    assert r.status_code == 200
    assert r.json()["summary"] == "MODEL_OUTPUT"
    blob = capture["system"] + " " + capture["turns"][-1]["content"]
    assert "Quarterly numbers" in blob


def test_summarize_nothing_to_summarize_404(client, capture):
    _set_provider("ollama")
    assert client.post("/ai/summarize", json={"message_id": 999999}).status_code == 404


# --- /ai/digest -------------------------------------------------------------
def test_digest_returns_briefing(client, capture):
    _set_provider("ollama")
    _seed_inbox_unread("zzdigest topic", 3)
    r = client.post("/ai/digest", json={})
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 3
    assert body["digest"] == "MODEL_OUTPUT"


# --- /ai/triage -------------------------------------------------------------
def test_triage_parses_scores_json(client, monkeypatch):
    _set_provider("ollama")
    ids = _seed_inbox_unread("zztriage", 2)
    payload = f'[{{"id": {ids[0]}, "score": 90, "reason": "personal"}}]'
    # A leading preamble before the JSON must not defeat parsing.
    monkeypatch.setattr(ai_mod, "_call_chat", lambda *a, **k: "Here are the scores:\n" + payload)
    r = client.post("/ai/triage", json={"limit": 40})
    assert r.status_code == 200
    assert any(s["id"] == ids[0] and s["score"] == 90 for s in r.json()["scores"])


def test_triage_bad_json_is_empty(client, monkeypatch):
    _set_provider("ollama")
    _seed_inbox_unread("zztriagebad", 1)
    monkeypatch.setattr(ai_mod, "_call_chat", lambda *a, **k: "no json here")
    r = client.post("/ai/triage", json={"limit": 40})
    assert r.status_code == 200
    assert r.json()["scores"] == []
