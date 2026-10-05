"""Sign-in code detection (app.sync.otp): real-world shapes must be found, and
everything that merely looks like a number must not be - a wrong code copied
over the clipboard is worse than none."""
import pytest

from app.sync.otp import find_code, html_to_text, looks_like_code_mail

FOUND = [
    ("Microsoft account security code",
     "Please use the following security code for the Microsoft account li**@a123.cz.\n\n"
     "Security code: 4281937\n\nIf you don't recognize the Microsoft account li**@a123.cz, you can click "
     "https://account.live.com/dp?ft=-DdNkG to remove your email address from that account.\n\nThanks,\nThe Microsoft account team",
     "4281937"),
    ("482931 is your Google verification code", "", "482931"),
    ("Google Verification Code",
     "G-482931 is your Google verification code. Don't share it with anyone.", "482931"),
    ("[GitHub] Please verify your device",
     "Hey lpeterek!\n\nA sign in attempt requires further verification because we did not recognize your device. "
     "To complete the sign in, enter the verification code on the unrecognized device.\n\n"
     "Device: Chrome on Windows\nVerification code: 551204\n\nIf you did not attempt to sign in to your account, "
     "your password may be compromised. Visit https://github.com/settings/security to create a new, strong password.",
     "551204"),
    ("Your Apple ID Code", "Your verification code is: 902114\nIf you didn't request this, ignore it.", "902114"),
    ("Your Amazon verification code",
     "To verify your identity, please use the following code:\n\n739102\n\nAmazon takes your account security very "
     "seriously. Amazon will never email you and ask you to disclose your password. Order #302-7654321-1234567",
     "739102"),
    ("Ověřovací kód", "Dobrý den,\nváš ověřovací kód pro přihlášení je 482 913. Platnost kódu je 5 minut.", "482913"),
    ("Přihlášení do Seznam.cz", "Kód pro ověření přihlášení: 123987\nKód zadejte do 10 minut.", "123987"),
    ("Your Steam account: Access from new computer",
     "Dear lpeterek,\n\nHere is the Steam Guard code you need to login to account lpeterek:\n\nF7K2X\n\n"
     "This email was generated because of a login attempt from a web or mobile device located at 1.2.3.4 (CZ).",
     "F7K2X"),
    ("Slack confirmation code: ABC-123",
     "Your confirmation code is below - enter it in your open browser window and we'll help you get signed in.\n\nABC-123",
     "ABC-123"),
    ("Your X confirmation code is wvpf6bzc", "Your X confirmation code is wvpf6bzc", "wvpf6bzc"),
    ("PayPal: your security code",
     "Your PayPal security code is 318274. Your code expires in 10 minutes. Please don't reply.", "318274"),
    ("Revolut", "Your Revolut verification code is 123-456. Never share it.", "123456"),
    ("Sign in to Robee", "Use this one-time code to sign in: 662019\nIt expires at 14:35 on 05.10.2026.", "662019"),
    ("Dvoufázové ověření", "Jednorázový kód: 90817263", "90817263"),
]

NOT_FOUND = [
    # promo / shopping - a "code", but not a sign-in
    ("Get 20% off this weekend", "Use code SAVE20 at checkout. 123456 happy customers can't be wrong."),
    ("Your order 4815162342 has shipped", "Order #4815162342 is on its way. Tracking 1Z999AA10123456784."),
    # a sign-in alert with no code - only a date, time and an address
    ("New sign-in to your account",
     "We noticed a new sign-in to your Microsoft account.\nCountry/region: Czechia\nIP address: 185.12.34.56\n"
     "Date: 05.10.2026 12:34 (GMT)\nIf this was you, you can ignore this message."),
    # password reset: the token lives in the link
    ("Reset your password", "Click here to reset your password: https://x.example/reset?token=abc123456789&u=99"),
    # a verification about an invoice, numbers are amounts and ids
    ("Verification of invoice 2026-001234", "Please verify the amount 12 500 Kč on invoice č. 2026001234 by 15.10.2026."),
    # nothing auth-related at all
    ("Lunch tomorrow?", "How about 12:00 at the canteen? Table 1234."),
    # a phone number near "code"
    ("Verify your phone", "We sent a code to +420 777 123 456. Didn't get it? Call 800 123 456."),
    # a year in a footer
    ("Your sign-in settings changed", "Your two-step settings were updated. © 2026 Example Inc."),
]


@pytest.mark.parametrize("subject,text,code", FOUND)
def test_finds_the_code(subject, text, code):
    assert find_code(subject, text) == code


@pytest.mark.parametrize("subject,text", NOT_FOUND)
def test_stays_quiet(subject, text):
    assert find_code(subject, text) is None


def test_html_only_mail():
    html = ("<html><head><style>.c{font-size:32px}</style></head><body><p>Your verification code:</p>"
            "<div class='c'><b>7&nbsp;3&nbsp;1</b></div><table><tr><td style='font-size:28px'>731904</td></tr></table>"
            "<p>Expires in 10 minutes.</p></body></html>")
    assert find_code("Verify your email", "", html) == "731904"
    assert "731904" in html_to_text(html)


def test_gate_on_subject_or_opening():
    assert looks_like_code_mail("Your verification code")
    assert looks_like_code_mail("Hello", "Enter this one-time code to sign in")
    assert not looks_like_code_mail("Weekly newsletter", "Use code SPRING for 10% off")


def test_two_equal_candidates_means_no_guess():
    assert find_code("Verify", "Verification code: 111222\nBackup code: 333444") is None
