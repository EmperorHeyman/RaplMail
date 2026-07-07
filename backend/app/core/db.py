"""SQLite engine, session management, and FTS5 full-text search setup."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from app.core.config import get_settings

_engine: Engine | None = None


def _configure_sqlite(dbapi_conn, _record) -> None:
    """Per-connection pragmas: WAL for concurrency, foreign keys on, faster sync."""
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=30000")
    # Cap the per-connection page cache so idle pooled connections (one per account
    # poller) don't each pin an unbounded amount of RAM. Negative = KiB. Reads are
    # served mostly from the shared mmap window below, so the private heap cache
    # can stay small (-4000 ≈ 4 MB/connection) without losing speed.
    cur.execute("PRAGMA cache_size=-4000")
    cur.execute("PRAGMA temp_store=MEMORY")
    # Memory-map the database file for reads: page access skips read() syscalls
    # and the mapping is file-backed + shared between connections (it doesn't
    # multiply per-connection like cache_size does).
    cur.execute("PRAGMA mmap_size=134217728")
    # A crash/kill can leave a huge -wal behind; cap what it grows back to after
    # a checkpoint so disk (and recovery time) stay bounded.
    cur.execute("PRAGMA journal_size_limit=33554432")
    cur.close()


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        settings = get_settings()
        settings.ensure_dirs()
        _engine = create_engine(
            f"sqlite:///{settings.db_path}",
            connect_args={"check_same_thread": False},
        )
        event.listen(_engine, "connect", _configure_sqlite)
    return _engine


# FTS5 virtual table mirroring searchable message fields, kept in sync via triggers.
_FTS_SETUP = [
    """
    CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
        subject, from_addr, from_name, snippet, body,
        content='', contentless_delete=1, tokenize='unicode61'
    )
    """,
]


# Columns added after the initial schema — applied to existing DBs via ALTER,
# since SQLModel.create_all() never alters existing tables.
_MIGRATIONS: dict[str, dict[str, str]] = {
    "message": {
        "body_html": "ALTER TABLE message ADD COLUMN body_html TEXT DEFAULT ''",
        "body_text": "ALTER TABLE message ADD COLUMN body_text TEXT DEFAULT ''",
        "body_fetched": "ALTER TABLE message ADD COLUMN body_fetched BOOLEAN DEFAULT 0",
        "category": "ALTER TABLE message ADD COLUMN category TEXT DEFAULT 'primary'",
        "unsubscribe": "ALTER TABLE message ADD COLUMN unsubscribe TEXT DEFAULT ''",
        "pending_action": "ALTER TABLE message ADD COLUMN pending_action TEXT DEFAULT ''",
        "attachments": "ALTER TABLE message ADD COLUMN attachments TEXT DEFAULT '[]'",
        "brand_domain": "ALTER TABLE message ADD COLUMN brand_domain TEXT DEFAULT ''",
        "snooze_presence": "ALTER TABLE message ADD COLUMN snooze_presence BOOLEAN DEFAULT 0",
        "auth_status": "ALTER TABLE message ADD COLUMN auth_status TEXT DEFAULT ''",
        "pinned": "ALTER TABLE message ADD COLUMN pinned BOOLEAN DEFAULT 0",
    },
    "messagestate": {
        "snooze_presence": "ALTER TABLE messagestate ADD COLUMN snooze_presence BOOLEAN DEFAULT 0",
        "is_pinned": "ALTER TABLE messagestate ADD COLUMN is_pinned BOOLEAN DEFAULT 0",
        # Device-sync last-writer-wins timestamp (nullable on legacy rows = oldest).
        "updated_at": "ALTER TABLE messagestate ADD COLUMN updated_at TIMESTAMP",
    },
    "account": {
        "aliases": "ALTER TABLE account ADD COLUMN aliases TEXT DEFAULT '[]'",
        "sort_order": "ALTER TABLE account ADD COLUMN sort_order INTEGER DEFAULT 0",
    },
    "calendarevent": {
        "source": "ALTER TABLE calendarevent ADD COLUMN source TEXT DEFAULT 'mail'",
        "color": "ALTER TABLE calendarevent ADD COLUMN color TEXT DEFAULT ''",
    },
    "mutedthread": {
        "participants": "ALTER TABLE mutedthread ADD COLUMN participants TEXT DEFAULT ''",
    },
    "folder": {
        # Some very old DBs predate uidvalidity on the folder row; add it if missing
        # so the UIDVALIDITY-reset guard can read/write it safely.
        "uidvalidity": "ALTER TABLE folder ADD COLUMN uidvalidity INTEGER",
        "backfill_min_uid": "ALTER TABLE folder ADD COLUMN backfill_min_uid INTEGER",
        "backfill_done": "ALTER TABLE folder ADD COLUMN backfill_done BOOLEAN DEFAULT 0",
    },
}


def _apply_migrations(conn) -> None:
    for table, columns in _MIGRATIONS.items():
        existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
        if not existing:
            continue  # table will be created by create_all with the new columns
        for col, ddl in columns.items():
            if col not in existing:
                conn.execute(text(ddl))


# Composite/partial indexes for the hot queries. SQLModel's index=True only
# covers single columns at table creation; these are applied to existing DBs too.
_INDEXES = [
    # Folder list + unified inbox: filter by folder, newest first.
    "CREATE INDEX IF NOT EXISTS ix_msg_folder_date ON message (folder_id, date DESC)",
    # Smart Inbox groups: filter by category, newest first.
    "CREATE INDEX IF NOT EXISTS ix_msg_category_date ON message (category, date DESC)",
    # Snoozed view / snooze-hiding predicate on every list query.
    "CREATE INDEX IF NOT EXISTS ix_msg_snooze_until ON message (snooze_until) WHERE snooze_until IS NOT NULL",
    # Presence-snooze resurface scan ('until I'm back').
    "CREATE INDEX IF NOT EXISTS ix_msg_snooze_presence ON message (snooze_presence) WHERE snooze_presence = 1",
]


def init_db() -> None:
    """Create all tables, run column migrations, indexes, and the FTS index. Idempotent."""
    engine = get_engine()
    SQLModel.metadata.create_all(engine)
    with engine.connect() as conn:
        _apply_migrations(conn)
        for stmt in _FTS_SETUP:
            conn.execute(text(stmt))
        for stmt in _INDEXES:
            conn.execute(text(stmt))
        conn.commit()


def index_message_fts(session: Session, rowid: int, *, subject: str, from_addr: str,
                      from_name: str, snippet: str, body: str) -> None:
    """Upsert a message into the FTS index (content-less table keyed by rowid)."""
    # Older DBs created this table without `contentless_delete=1`, and SQLite then
    # rejects any DELETE on it ("cannot DELETE from contentless fts5 table"). The
    # DELETE only matters when re-indexing an existing rowid; for new messages
    # there's nothing to remove. Wrap it in a SAVEPOINT so a rejection rolls back
    # ONLY the delete (not the caller's pending message insert) and the INSERT
    # still runs — worst case a re-indexed row leaves a duplicate, deduped on read.
    try:
        with session.begin_nested():
            session.exec(text("DELETE FROM message_fts WHERE rowid = :rid").bindparams(rid=rowid))
    except Exception:
        pass
    session.exec(
        text(
            "INSERT INTO message_fts(rowid, subject, from_addr, from_name, snippet, body) "
            "VALUES (:rid, :subject, :from_addr, :from_name, :snippet, :body)"
        ).bindparams(rid=rowid, subject=subject, from_addr=from_addr,
                     from_name=from_name, snippet=snippet, body=body)
    )


def get_session() -> Iterator[Session]:
    """FastAPI dependency yielding a session."""
    with Session(get_engine()) as session:
        yield session
