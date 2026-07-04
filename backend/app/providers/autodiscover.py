"""Email account autodiscovery.

Given just an email address, figure out how to connect: the provider type
(generic IMAP, Gmail, Microsoft 365), the auth method (password vs OAuth2), and
the IMAP/SMTP host/port/security. Mirrors what Thunderbird/Outlook do.

Resolution order (first hit wins):
  1. Known-provider table (gmail, seznam, icloud, …)
  2. MX lookup — detects M365 / Google-hosted *custom* domains (e.g. a company
     domain whose mail is really on Outlook or Google).
  3. Thunderbird ISPDB (autoconfig.thunderbird.net)
  4. Provider autoconfig URLs (autoconfig.<domain>, <domain>/.well-known/…)
  5. DNS SRV records (RFC 6186)
  6. Heuristic guess: imap.<domain> / smtp.<domain>
"""

from __future__ import annotations

from dataclasses import dataclass, field

_HTTP_TIMEOUT = 6.0


@dataclass
class Discovered:
    email: str
    domain: str
    provider: str = "imap"          # "imap" | "gmail" | "m365"
    auth: str = "password"          # "password" | "oauth"
    imap_host: str = ""
    imap_port: int = 993
    imap_ssl: bool = True
    smtp_host: str = ""
    smtp_port: int = 465
    smtp_starttls: bool = False
    display_name: str = ""
    source: str = "guess"           # where the config came from
    note: str = ""                  # user-facing hint (e.g. "needs an app password")
    confident: bool = False         # True if we trust hosts without user editing


# --- 1. Known providers ------------------------------------------------------
def _imap(host, port=993, ssl=True):
    return dict(imap_host=host, imap_port=port, imap_ssl=ssl)


def _smtp(host, port=465, starttls=False):
    return dict(smtp_host=host, smtp_port=port, smtp_starttls=starttls)

# Maps a domain to a fully-known configuration.
KNOWN: dict[str, dict] = {
    "gmail.com": dict(provider="gmail", auth="oauth", **_imap("imap.gmail.com"), **_smtp("smtp.gmail.com", 587, True), note="Sign in with Google."),
    "googlemail.com": dict(provider="gmail", auth="oauth", **_imap("imap.gmail.com"), **_smtp("smtp.gmail.com", 587, True), note="Sign in with Google."),
    "outlook.com": dict(provider="m365", auth="oauth", **_imap("outlook.office365.com"), **_smtp("smtp.office365.com", 587, True), note="Sign in with Microsoft."),
    "hotmail.com": dict(provider="m365", auth="oauth", **_imap("outlook.office365.com"), **_smtp("smtp.office365.com", 587, True), note="Sign in with Microsoft."),
    "live.com": dict(provider="m365", auth="oauth", **_imap("outlook.office365.com"), **_smtp("smtp.office365.com", 587, True), note="Sign in with Microsoft."),
    "seznam.cz": dict(**_imap("imap.seznam.cz"), **_smtp("smtp.seznam.cz", 465), note="Use your Seznam password."),
    "email.cz": dict(**_imap("imap.seznam.cz"), **_smtp("smtp.seznam.cz", 465), note="Use your Seznam password."),
    "centrum.cz": dict(**_imap("imap.centrum.cz"), **_smtp("smtp.centrum.cz", 465)),
    "atlas.cz": dict(**_imap("imap.centrum.cz"), **_smtp("smtp.centrum.cz", 465)),
    "icloud.com": dict(**_imap("imap.mail.me.com"), **_smtp("smtp.mail.me.com", 587, True), note="Requires an app-specific password."),
    "me.com": dict(**_imap("imap.mail.me.com"), **_smtp("smtp.mail.me.com", 587, True), note="Requires an app-specific password."),
    "yahoo.com": dict(**_imap("imap.mail.yahoo.com"), **_smtp("smtp.mail.yahoo.com", 465), note="Requires an app password."),
    "fastmail.com": dict(**_imap("imap.fastmail.com"), **_smtp("smtp.fastmail.com", 465), note="Use an app password."),
    "proton.me": dict(**_imap("127.0.0.1", 1143, False), **_smtp("127.0.0.1", 1025, True), note="Requires Proton Mail Bridge running locally."),
}


def discover(email: str) -> Discovered:
    email = email.strip()
    domain = email.rsplit("@", 1)[-1].lower() if "@" in email else ""
    d = Discovered(email=email, domain=domain)
    if not domain:
        return d

    if domain in KNOWN:
        _apply(d, KNOWN[domain], source="known", confident=True)
        return d

    mx = _detect_by_mx(domain)
    if mx:
        _apply(d, mx, source="mx", confident=True)
        return d

    for fetcher in (_from_ispdb, _from_provider_autoconfig):
        cfg = fetcher(domain, email)
        if cfg:
            _apply(d, cfg, source=cfg.pop("_source", "autoconfig"), confident=True)
            return d

    srv = _from_srv(domain)
    if srv:
        _apply(d, srv, source="srv", confident=True)
        return d

    # Last resort: guess and let the user confirm.
    _apply(d, dict(**_imap(f"imap.{domain}"), **_smtp(f"mail.{domain}", 587, True)),
           source="guess", confident=False)
    d.note = d.note or "We guessed these settings — please double-check them."
    return d


def _apply(d: Discovered, cfg: dict, *, source: str, confident: bool) -> None:
    for k, v in cfg.items():
        if hasattr(d, k):
            setattr(d, k, v)
    d.source = source
    d.confident = confident


# --- 2. MX-based detection ---------------------------------------------------
# A custom domain (e.g. rapl-group.eu) usually has its mail hosted by a known
# provider; the MX records reveal which. We match MX hostnames to a config so
# "vanity" domains on Seznam/Google/M365/etc. resolve to the right IMAP/SMTP.
_MX_RULES: list[tuple[tuple[str, ...], dict]] = [
    (("protection.outlook.com", "mail.protection.outlook", "outlook.com"),
     dict(provider="m365", auth="oauth", **_imap("outlook.office365.com"),
          **_smtp("smtp.office365.com", 587, True),
          note="Hosted on Microsoft 365 — sign in with Microsoft.")),
    (("aspmx.l.google.com", "googlemail.com", "google.com", "psmtp.com"),
     dict(provider="gmail", auth="oauth", **_imap("imap.gmail.com"),
          **_smtp("smtp.gmail.com", 587, True),
          note="Hosted on Google Workspace — sign in with Google.")),
    (("seznam.cz",),
     dict(**_imap("imap.seznam.cz"), **_smtp("smtp.seznam.cz", 465),
          note="Hosted on Seznam — use your Seznam password (enable IMAP in Seznam settings).")),
    (("centrum.cz", "atlas.cz"),
     dict(**_imap("imap.centrum.cz"), **_smtp("smtp.centrum.cz", 465),
          note="Hosted on Centrum.")),
    (("icloud.com", "mail.me.com", "apple.com"),
     dict(**_imap("imap.mail.me.com"), **_smtp("smtp.mail.me.com", 587, True),
          note="Hosted on iCloud — requires an app-specific password.")),
    (("messagingengine.com", "fastmail.com"),
     dict(**_imap("imap.fastmail.com"), **_smtp("smtp.fastmail.com", 465),
          note="Hosted on Fastmail — use an app password.")),
    (("zoho.com", "zoho.eu", "zohomail"),
     dict(**_imap("imap.zoho.com"), **_smtp("smtp.zoho.com", 465),
          note="Hosted on Zoho.")),
    (("yahoodns.net", "yahoo.com"),
     dict(**_imap("imap.mail.yahoo.com"), **_smtp("smtp.mail.yahoo.com", 465),
          note="Hosted on Yahoo — requires an app password.")),
    (("mailgun.org", "pphosted.com", "mimecast.com"),  # gateways — fall through unless nothing else
     dict()),
]


def _detect_by_mx(domain: str) -> dict | None:
    hosts = _mx_hosts(domain)
    if not hosts:
        return None
    for keys, cfg in _MX_RULES:
        if not cfg:
            continue
        for h in hosts:
            if any(k in h for k in keys):
                out = dict(cfg)
                out.setdefault("confident", True)
                return out
    return None


def _mx_hosts(domain: str) -> list[str]:
    try:
        import dns.resolver

        answers = dns.resolver.resolve(domain, "MX", lifetime=4.0)
        return [str(r.exchange).rstrip(".").lower() for r in answers]
    except Exception:
        return []


# --- 3/4. Thunderbird ISPDB + provider autoconfig ----------------------------
def _from_ispdb(domain: str, email: str) -> dict | None:
    url = f"https://autoconfig.thunderbird.net/v1.1/{domain}"
    return _fetch_and_parse(url, source="ispdb")


def _from_provider_autoconfig(domain: str, email: str) -> dict | None:
    for url in (
        f"https://autoconfig.{domain}/mail/config-v1.1.xml?emailaddress={email}",
        f"https://{domain}/.well-known/autoconfig/mail/config-v1.1.xml?emailaddress={email}",
    ):
        cfg = _fetch_and_parse(url, source="autoconfig")
        if cfg:
            return cfg
    return None


def _fetch_and_parse(url: str, *, source: str) -> dict | None:
    import httpx  # deferred — autodiscovery runs once per added account
    try:
        resp = httpx.get(url, timeout=_HTTP_TIMEOUT, follow_redirects=True)
        if resp.status_code != 200 or not resp.text.strip().startswith("<"):
            return None
        cfg = _parse_autoconfig_xml(resp.text)
        if cfg:
            cfg["_source"] = source
        return cfg
    except Exception:
        return None


def _parse_autoconfig_xml(xml: str) -> dict | None:
    import xml.etree.ElementTree as ET

    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return None
    cfg: dict = {}
    for inc in root.iter("incomingServer"):
        if inc.get("type") != "imap":
            continue
        host = _text(inc, "hostname")
        if not host:
            continue
        socket = (_text(inc, "socketType") or "SSL").upper()
        cfg.update(_imap(host, int(_text(inc, "port") or 993), socket == "SSL"))
        if "oauth2" in (_text(inc, "authentication") or "").lower():
            cfg["auth"] = "oauth"
        break
    for out in root.iter("outgoingServer"):
        if out.get("type") != "smtp":
            continue
        host = _text(out, "hostname")
        if not host:
            continue
        socket = (_text(out, "socketType") or "SSL").upper()
        cfg.update(_smtp(host, int(_text(out, "port") or 465), socket == "STARTTLS"))
        break
    return cfg if cfg.get("imap_host") else None


def _text(el, tag: str) -> str:
    child = el.find(tag)
    return child.text.strip() if child is not None and child.text else ""


# --- 5. DNS SRV (RFC 6186) ---------------------------------------------------
def _from_srv(domain: str) -> dict | None:
    imap = _srv_lookup(f"_imaps._tcp.{domain}")
    smtp = _srv_lookup(f"_submission._tcp.{domain}")
    if not imap:
        return None
    cfg = _imap(imap[0], imap[1], ssl=True)
    if smtp:
        cfg.update(_smtp(smtp[0], smtp[1], starttls=(smtp[1] == 587)))
    else:
        cfg.update(_smtp(f"smtp.{domain}", 587, True))
    return cfg


def _srv_lookup(name: str) -> tuple[str, int] | None:
    try:
        import dns.resolver

        answers = dns.resolver.resolve(name, "SRV", lifetime=4.0)
        rec = sorted(answers, key=lambda r: r.priority)[0]
        return str(rec.target).rstrip(".").lower(), int(rec.port)
    except Exception:
        return None
