// RAPL Desk namespaces: "tickets.*" (TicketsView - the helpdesk ticket list,
// detail and new-ticket form) and "rapldesk.*" (SettingsRaplDesk - instance
// connections + agent identity).
// Flat "ns.key" → text; {placeholders} are filled by t(key, { ... }).
// Every en key MUST also exist in cs (missing keys fall back to English).
export default {
  en: {
    // ------ TicketsView ------
    // Header, stats & toolbar.
    "tickets.title": "Tickets",
    "tickets.refresh": "Refresh",
    "tickets.newTicket": "New ticket",
    "tickets.statTotal": "total",
    "tickets.statOpen": "open",
    "tickets.statClosed": "closed",

    // Scope tabs.
    "tickets.tabAll": "All",
    "tickets.tabMine": "My tickets",
    "tickets.tabDept": "My dept",
    "tickets.tabUnassigned": "Unassigned",
    "tickets.tabCreated": "Created",
    "tickets.signedInVia": "Signed in via this API key",

    // Filters.
    "tickets.searchPlaceholder": "Search tickets…",
    "tickets.anyStatus": "Any status",
    "tickets.anyPriority": "Any priority",

    // Hint under the "mine"/"created" tabs (split around the <b>/<code> parts).
    "tickets.tabHintPre": "Set your RaplDesk user id in",
    "tickets.settingsPath": "Settings → RAPL Desk",
    "tickets.tabHintMid": "(or add",
    "tickets.tabHintEnd": "to the API) to use this tab.",

    // Empty / loading states.
    "tickets.noDesk": "No RAPL Desk connected.",
    "tickets.connectInSettings": "Connect in Settings → RAPL Desk",
    "tickets.loading": "Loading…",
    "tickets.noMatch": "No tickets match.",

    // List row.
    "tickets.unread": "Unread",
    "tickets.unassigned": "unassigned",
    "tickets.overdue": "overdue",
    "tickets.pastDeadline": "Past deadline",

    // Pager.
    "tickets.prev": "‹ Prev",
    "tickets.next": "Next ›",
    "tickets.pageInfo": "Page {page} / {pages} · {total} total",

    // Detail view.
    "tickets.backToList": "‹ All tickets",
    "tickets.status": "Status",
    "tickets.priority": "Priority",
    "tickets.byName": "by {name}",
    "tickets.internal": "internal",
    "tickets.noReplies": "No replies yet.",
    "tickets.replyPlaceholder": "Write a reply…",
    "tickets.internalNote": "Internal note",
    "tickets.sending": "Sending…",
    "tickets.reply": "Reply",

    // New-ticket form.
    "tickets.fTitle": "Title",
    "tickets.fDescription": "Description",
    "tickets.fFirm": "Firm",
    "tickets.fCreatedBy": "Created by",
    "tickets.fDepartment": "Department",
    "tickets.fAssign": "Assign",
    "tickets.assignToMe": "Assign to me",
    "tickets.phFirmId": "firm id",
    "tickets.phUserId": "user id",
    "tickets.phOptional": "optional",
    "tickets.cancel": "Cancel",
    "tickets.creating": "Creating…",
    "tickets.createTicket": "Create ticket",

    // Status labels (keyed by the API's status ids).
    "tickets.st.open": "Open",
    "tickets.st.assigned": "Assigned",
    "tickets.st.in_progress": "In progress",
    "tickets.st.on_hold": "On hold",
    "tickets.st.closed": "Closed",

    // Priority labels (keyed by the API's priority ids).
    "tickets.pri.low": "Low",
    "tickets.pri.normal": "Normal",
    "tickets.pri.high": "High",
    "tickets.pri.critical": "Critical",

    // Errors & toasts.
    "tickets.errNotAllowed": "Not allowed ({http}) - this API key is missing the required scope.",
    "tickets.err404": "404 Not Found - check the instance Base URL. Called: {url}",
    "tickets.errGeneric": "RaplDesk error",
    "tickets.setUserIdFirst": "Set your RaplDesk user id in Settings → RAPL Desk first",
    "tickets.replyPosted": "Reply posted",
    "tickets.fieldSet": "Ticket: {field} → {value}",
    "tickets.titleDescRequired": "Title and description are required",
    "tickets.firmCreatorRequired": "Firm and 'created by' user are required",
    "tickets.created": "Ticket created",

    // ------ SettingsRaplDesk ------
    "rapldesk.title": "RAPL Desk (ticketing)",
    // Intro hint, split around the two <b> segments.
    "rapldesk.hintA": "Connect one or more RaplDesk instances by base URL + API key. Tickets show up under",
    "rapldesk.hintTickets": "Tickets",
    "rapldesk.hintB": " in the sidebar. Keys are stored encrypted in your vault (and never leave your machine except to call that instance). The key's",
    "rapldesk.hintScopes": "scopes",
    "rapldesk.hintC": "decide what you can do - for full use grant tickets.read/write, users.read, departments.read, firms.read and reports.read.",

    // Instance list & add form.
    "rapldesk.keyMissing": "key missing",
    "rapldesk.remove": "Remove",
    "rapldesk.noInstances": "No instances yet.",
    "rapldesk.name": "Name",
    "rapldesk.baseUrl": "Base URL",
    "rapldesk.apiKey": "API key",
    "rapldesk.phName": "A123 Tickets",
    "rapldesk.phKey": "Bearer token",
    "rapldesk.connecting": "Connecting…",
    "rapldesk.connect": "Connect",
    "rapldesk.cancel": "Cancel",
    "rapldesk.addInstance": "Add instance",

    // Agent identity card.
    "rapldesk.identityTitle": "Your agent identity",
    "rapldesk.identityHint": "RaplDesk requires a user id when posting replies or creating tickets. Enter the user id of your agent account so replies are attributed to you.",
    "rapldesk.userIdLabel": "RaplDesk user id",
    "rapldesk.phUserId": "e.g. 25",

    // Toasts & confirms.
    "rapldesk.urlKeyRequired": "URL and API key are required",
    "rapldesk.connected": "RAPL Desk connected",
    "rapldesk.couldntConnect": "Couldn't connect",
    "rapldesk.removeConfirm": "Remove {name}?",
    "rapldesk.removed": "Removed",
  },
  cs: {
    // ------ TicketsView ------
    // Hlavička, statistiky a lišta nástrojů.
    "tickets.title": "Tikety",
    "tickets.refresh": "Obnovit",
    "tickets.newTicket": "Nový tiket",
    "tickets.statTotal": "celkem",
    "tickets.statOpen": "otevřené",
    "tickets.statClosed": "uzavřené",

    // Záložky rozsahu.
    "tickets.tabAll": "Vše",
    "tickets.tabMine": "Moje tikety",
    "tickets.tabDept": "Moje oddělení",
    "tickets.tabUnassigned": "Nepřiřazené",
    "tickets.tabCreated": "Vytvořené",
    "tickets.signedInVia": "Přihlášeni přes tento API klíč",

    // Filtry.
    "tickets.searchPlaceholder": "Hledat tikety…",
    "tickets.anyStatus": "Libovolný stav",
    "tickets.anyPriority": "Libovolná priorita",

    // Nápověda pod záložkami „moje“/„vytvořené“ (rozdělená kolem <b>/<code>).
    "tickets.tabHintPre": "Nastavte své ID uživatele RaplDesk v",
    "tickets.settingsPath": "Nastavení → RAPL Desk",
    "tickets.tabHintMid": "(nebo přidejte",
    "tickets.tabHintEnd": "do API), abyste mohli tuto záložku používat.",

    // Prázdné stavy / načítání.
    "tickets.noDesk": "Není připojen žádný RAPL Desk.",
    "tickets.connectInSettings": "Připojit v Nastavení → RAPL Desk",
    "tickets.loading": "Načítání…",
    "tickets.noMatch": "Žádné odpovídající tikety.",

    // Řádek seznamu.
    "tickets.unread": "Nepřečteno",
    "tickets.unassigned": "nepřiřazeno",
    "tickets.overdue": "po termínu",
    "tickets.pastDeadline": "Po termínu",

    // Stránkování.
    "tickets.prev": "‹ Předchozí",
    "tickets.next": "Další ›",
    "tickets.pageInfo": "Strana {page} / {pages} · celkem {total}",

    // Detail tiketu.
    "tickets.backToList": "‹ Všechny tikety",
    "tickets.status": "Stav",
    "tickets.priority": "Priorita",
    "tickets.byName": "vytvořil(a) {name}",
    "tickets.internal": "interní",
    "tickets.noReplies": "Zatím žádné odpovědi.",
    "tickets.replyPlaceholder": "Napište odpověď…",
    "tickets.internalNote": "Interní poznámka",
    "tickets.sending": "Odesílání…",
    "tickets.reply": "Odpovědět",

    // Formulář nového tiketu.
    "tickets.fTitle": "Název",
    "tickets.fDescription": "Popis",
    "tickets.fFirm": "Firma",
    "tickets.fCreatedBy": "Vytvořil",
    "tickets.fDepartment": "Oddělení",
    "tickets.fAssign": "Přiřazení",
    "tickets.assignToMe": "Přiřadit mně",
    "tickets.phFirmId": "ID firmy",
    "tickets.phUserId": "ID uživatele",
    "tickets.phOptional": "volitelné",
    "tickets.cancel": "Zrušit",
    "tickets.creating": "Vytváření…",
    "tickets.createTicket": "Vytvořit tiket",

    // Popisky stavů (klíčované podle id stavů z API).
    "tickets.st.open": "Otevřený",
    "tickets.st.assigned": "Přiřazený",
    "tickets.st.in_progress": "V řešení",
    "tickets.st.on_hold": "Pozastavený",
    "tickets.st.closed": "Uzavřený",

    // Popisky priorit (klíčované podle id priorit z API).
    "tickets.pri.low": "Nízká",
    "tickets.pri.normal": "Normální",
    "tickets.pri.high": "Vysoká",
    "tickets.pri.critical": "Kritická",

    // Chyby a hlášení.
    "tickets.errNotAllowed": "Přístup odepřen ({http}) - tomuto API klíči chybí potřebné oprávnění (scope).",
    "tickets.err404": "404 Nenalezeno - zkontrolujte Base URL instance. Voláno: {url}",
    "tickets.errGeneric": "Chyba RaplDesk",
    "tickets.setUserIdFirst": "Nejprve nastavte své ID uživatele RaplDesk v Nastavení → RAPL Desk",
    "tickets.replyPosted": "Odpověď odeslána",
    "tickets.fieldSet": "Tiket: {field} → {value}",
    "tickets.titleDescRequired": "Název a popis jsou povinné",
    "tickets.firmCreatorRequired": "Firma a pole „Vytvořil“ jsou povinné",
    "tickets.created": "Tiket vytvořen",

    // ------ SettingsRaplDesk ------
    "rapldesk.title": "RAPL Desk (tikety)",
    // Úvodní nápověda, rozdělená kolem dvou <b> částí.
    "rapldesk.hintA": "Připojte jednu či více instancí RaplDesk pomocí base URL + API klíče. Tikety najdete v postranním panelu pod položkou",
    "rapldesk.hintTickets": "Tikety",
    "rapldesk.hintB": ". Klíče jsou uloženy zašifrované ve vašem trezoru (a nikdy neopustí váš počítač - používají se jen k volání dané instance). O tom, co můžete dělat, rozhodují",
    "rapldesk.hintScopes": "rozsahy oprávnění (scopes)",
    "rapldesk.hintC": "klíče - pro plné využití udělte tickets.read/write, users.read, departments.read, firms.read a reports.read.",

    // Seznam instancí a formulář přidání.
    "rapldesk.keyMissing": "chybí klíč",
    "rapldesk.remove": "Odebrat",
    "rapldesk.noInstances": "Zatím žádné instance.",
    "rapldesk.name": "Název",
    "rapldesk.baseUrl": "Base URL",
    "rapldesk.apiKey": "API klíč",
    "rapldesk.phName": "A123 Tickets",
    "rapldesk.phKey": "Bearer token",
    "rapldesk.connecting": "Připojování…",
    "rapldesk.connect": "Připojit",
    "rapldesk.cancel": "Zrušit",
    "rapldesk.addInstance": "Přidat instanci",

    // Karta identity agenta.
    "rapldesk.identityTitle": "Vaše identita agenta",
    "rapldesk.identityHint": "RaplDesk vyžaduje ID uživatele při odesílání odpovědí a vytváření tiketů. Zadejte ID uživatele svého agentského účtu, aby se odpovědi připisovaly vám.",
    "rapldesk.userIdLabel": "ID uživatele RaplDesk",
    "rapldesk.phUserId": "např. 25",

    // Hlášení a potvrzení.
    "rapldesk.urlKeyRequired": "URL a API klíč jsou povinné",
    "rapldesk.connected": "RAPL Desk připojen",
    "rapldesk.couldntConnect": "Připojení se nezdařilo",
    "rapldesk.removeConfirm": "Odebrat {name}?",
    "rapldesk.removed": "Odebráno",
  },
};
