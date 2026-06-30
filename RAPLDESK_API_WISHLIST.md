# RaplDesk API — what RaplMail needs to be great

> A client-driven wishlist for the ticketing API (`/admin/addons/api/v1/api.php`).
> Written from the perspective of building the **Tickets** view in RaplMail. Ordered
> by impact. The #1 item unblocks almost everything else.

---

## 0. The root problem: the key has no identity

Right now an API key authenticates a *request* but the client has **no idea who it
belongs to**. That forces the user to hand-type their own numeric `user_id` (which
nobody knows), and makes "My tickets / My departments" impossible to build. Fix
this one thing and the whole UX falls into place.

### ➤ `GET /me`  (NEW — highest priority)
Return the identity the API key is bound to.

```json
{
  "status": "success",
  "data": {
    "user": {
      "id": 25,
      "name": "Lukáš Peterek",
      "email": "lpeterek@a123systems.eu",
      "role": "agent",
      "firm_id": 1,
      "firm_name": "A123 Systems",
      "department_ids": [3, 7],
      "department_names": ["IT Support", "Infrastructure"]
    }
  }
}
```
- Scope: any valid key (no extra scope), or `users.read`.
- Eliminates the manual "user id" field entirely — replies/new tickets use `me.id`.
- `department_ids` powers the **My departments** tab.

---

## 1. Ticket list: a `scope` filter (powers the tabs)

The client wants four tabs. Make them one query param so the server does the work
(and pagination stays correct):

### ➤ `GET /tickets?scope={scope}`  (NEW param)
| `scope`        | Meaning                                                        |
|----------------|----------------------------------------------------------------|
| `mine`         | `assigned_to` = the key's user (the **My tickets** tab)        |
| `created`      | `created_by` = the key's user (**My created**)                 |
| `unassigned`   | no assignee **and** in one of my departments (**Unassigned**)  |
| `department`   | any ticket in one of my departments (**My departments**)       |
| `all`          | everything the key may see (default)                           |

Notes:
- `scope` resolves against `GET /me`, so the client never sends ids for these.
- Today there's **no way to query unassigned** at all — `assigned_to=` is the only
  assignee filter and it needs an id. Please support `assigned_to=none` (or
  `unassigned=1`) as well, even without `scope`.
- Combine with the existing `status`/`priority`/`search`/`page` params.

---

## 2. Return **IDs**, not just names, in the ticket list

The list currently returns `assigned_to_name`, `created_by_name`, `department_name`,
`firm_name` — but **not their ids**. So the client can't filter by them, can't
pre-select them in the assignee/department dropdowns, and can't act on them without
a second lookup.

### ➤ Add to each ticket in `GET /tickets` and `GET /tickets/{id}`:
```json
{
  "assigned_to_user_id": 25,
  "created_by_user_id": 42,
  "department_id": 3,
  "firm_id": 1,
  "help_topic_id": 12,
  "last_reply_at": "2025-11-10 09:30:00",
  "last_reply_by_name": "Tech Support",
  "unread": true,
  "deadline_at": "2025-11-15 17:00:00",
  "is_overdue": false
}
```
Rule of thumb: **every object returns both its `id` and its human label.** Names are
for display; ids are for action.

---

## 3. Tab counts (badges) — `GET /tickets/counts`  (NEW)

So the tabs can show numbers without fetching every ticket:
```json
{
  "status": "success",
  "data": { "mine": 7, "created": 3, "unassigned": 12, "department": 40, "all": 128,
            "by_status": { "open": 30, "in_progress": 8, "on_hold": 2 } }
}
```
- Resolves "mine/created/unassigned/department" against `GET /me`.
- Lets the sidebar/tab bar show live counts cheaply.

---

## 4. Assign without knowing ids

### ➤ Accept `"me"` in `PUT /tickets/{id}`:
```json
{ "assigned_to_user_id": "me" }      // assign to the key's user — "grab" a ticket
```
### ➤ List assignable agents for the dropdown:
`GET /users?role=agent&department_id=3` already works *if* it returns ids (it does) —
just make sure `department_id` filtering is supported so the assignee picker only
shows relevant agents.

---

## 5. Incremental sync — `GET /tickets?updated_after=<ISO>`  (NEW param)

So RaplMail can poll cheaply and surface **new/updated tickets** (notifications,
live "wall monitor") without re-pulling everything:
```
GET /tickets?updated_after=2025-11-10T09:00:00Z&scope=department
```
Return only tickets changed since that timestamp, newest-`updated_at` first.
(Even better long-term: a webhook on ticket create/reply — but `updated_after`
covers 90% with zero infra.)

---

## 6. Smaller niceties (nice-to-have, not blocking)

- **`GET /help_topics`** (+ ids/names) so the New-ticket form can offer a topic picker.
- **Status/priority enums** echoed somewhere (e.g. `GET /meta`) so the client doesn't
  hardcode `open/assigned/in_progress/on_hold/closed`.
- **Reply attachments** in `GET /tickets/{id}/replies` (ids + filenames + a download
  URL via `attachments.read`), and accept attachment ids when posting a reply.
- **`search`** should also match ticket **body of replies**, not just title/description.
- **Consistent timestamps** — ISO‑8601 with timezone (`2025-11-10T09:30:00+01:00`)
  everywhere instead of `YYYY-MM-DD HH:MM:SS` (ambiguous tz).
- **Pagination on replies** for very long threads.

---

## Priority order for implementation

1. **`GET /me`** — unblocks identity, kills the manual user-id field.
2. **IDs in the ticket list** (#2) — unblocks filtering/assignment.
3. **`scope=mine|created|unassigned|department`** (#1) — the tabs.
4. **`GET /tickets/counts`** (#3) — tab badges.
5. `updated_after` (#5), assign-`me` (#4), then the niceties.

Items 1–3 are what make the RaplMail Tickets view feel native instead of
id-juggling. Everything else is polish.
