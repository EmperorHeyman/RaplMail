"""Anti-phishing screening: the domain/TLD blocklist matcher, the header-only
spoof heuristics (brand impersonation + display-name/domain mismatch), and the
AI-verdict parser. Pure functions - no live mailbox or model needed."""
from app.api.ai import _parse_screen
from app.sync.authcheck import spoof_warnings
from app.sync.screening import (header_spoof_flags, matches_blocked_domain,
                                 normalize_blocklist)


# --- blocklist normalization ------------------------------------------------
def test_normalize_blocklist_from_string_and_list():
    assert normalize_blocklist(".ru, spammer.com\n@Bad.IO") == ["ru", "spammer.com", "bad.io"]
    assert normalize_blocklist(["RU", "ru", " ru "]) == ["ru"]          # dedup + trim
    assert normalize_blocklist("") == []
    assert normalize_blocklist(None) == []


# --- blocklist matching -----------------------------------------------------
def test_blocked_tld_matches_any_subdomain():
    blocked = normalize_blocklist(".ru")
    assert matches_blocked_domain("evil@x.ru", blocked) is True
    assert matches_blocked_domain("evil@deep.sub.ru", blocked) is True
    assert matches_blocked_domain("ok@example.com", blocked) is False
    # A domain that merely ENDS with the letters "ru" but isn't the .ru TLD is safe.
    assert matches_blocked_domain("ok@peru.com", blocked) is False


def test_blocked_exact_domain_and_subdomain():
    blocked = normalize_blocklist("spammer.com")
    assert matches_blocked_domain("a@spammer.com", blocked) is True
    assert matches_blocked_domain("a@mail.spammer.com", blocked) is True
    assert matches_blocked_domain("a@notspammer.com", blocked) is False   # not a subdomain
    assert matches_blocked_domain("", blocked) is False


# --- brand impersonation heuristic ------------------------------------------
def test_brand_name_from_wrong_domain_is_flagged():
    # The user's exact example: "LinkedIn" in the name, address on a throwaway TLD.
    flags = header_spoof_flags("gdfjkg@whatever.ru", "LinkedIn")
    assert flags, "brand-name-from-wrong-domain should be flagged"
    assert "impersonation" in " ".join(flags).lower()


def test_legit_brand_domain_not_flagged():
    # Real LinkedIn mail (even from a sending subdomain) must NOT be flagged.
    assert header_spoof_flags("notifications-noreply@e.linkedin.com", "LinkedIn") == []
    assert header_spoof_flags("no-reply@paypal.com", "PayPal") == []


def test_brand_word_inside_other_word_not_flagged():
    # "apple" appears inside "Applebee's" - word-boundary matching must not trip.
    assert header_spoof_flags("info@applebees.com", "Applebee's Grill") == []


def test_display_name_domain_mismatch_still_works():
    # Pre-existing check: name cites a domain absent from the real address.
    flags = spoof_warnings("x@random.io", "security@paypal.com", "")
    assert any("paypal.com" in f for f in flags)


# --- AI verdict parsing -----------------------------------------------------
def test_parse_screen_strict_format():
    v, r = _parse_screen("VERDICT: dangerous\nREASON: Spoofed sender asking for a gift card.")
    assert v == "dangerous"
    assert "gift card" in r.lower()


def test_parse_screen_defaults_safe_when_unclear():
    v, _ = _parse_screen("This message appears to be a normal newsletter.")
    assert v == "safe"


def test_parse_screen_keyword_fallback():
    v, _ = _parse_screen("This looks like a phishing attempt targeting your bank login.")
    assert v == "dangerous"
