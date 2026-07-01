"""In-memory ring buffer of recent log records, for the in-app Debug window.

A single handler attached to the root logger keeps the last N formatted records
in memory (no disk, no PII leaving the machine). The /debug API reads from it so
the user can see what the backend is doing without a console.
"""

from __future__ import annotations

import logging
import traceback
from collections import deque
from datetime import datetime, timezone
from threading import Lock

_MAX = 800  # keep the last ~800 lines; plenty to diagnose a sync/send stall


class RingBufferHandler(logging.Handler):
    def __init__(self, capacity: int = _MAX):
        super().__init__()
        self._buf: deque[dict] = deque(maxlen=capacity)
        self._lock = Lock()
        self._seq = 0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = record.getMessage()
        except Exception:
            # Bad %-args — keep the raw template rather than losing the line.
            msg = str(record.msg)
        if record.exc_info:
            try:
                msg = msg + "\n" + "".join(traceback.format_exception(*record.exc_info))
            except Exception:
                pass
        with self._lock:
            self._seq += 1
            self._buf.append({
                "seq": self._seq,
                "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "msg": msg,
            })

    def records(self, since: int = 0, level: str | None = None) -> list[dict]:
        with self._lock:
            items = [r for r in self._buf if r["seq"] > since]
        if level:
            wanted = logging.getLevelName(level.upper())
            if isinstance(wanted, int):
                items = [r for r in items if logging.getLevelName(r["level"]) >= wanted]
        return items

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()


_handler: RingBufferHandler | None = None


def get_log_buffer() -> RingBufferHandler:
    """The process-wide ring buffer handler (installed lazily)."""
    global _handler
    if _handler is None:
        _handler = RingBufferHandler()
    return _handler


def install(level: int = logging.INFO) -> RingBufferHandler:
    """Attach the ring buffer to the root logger so all app + uvicorn logs land in
    it. Idempotent. Also ensures our own 'raplmail' loggers emit at INFO+."""
    handler = get_log_buffer()
    root = logging.getLogger()
    if handler not in root.handlers:
        root.addHandler(handler)
    if root.level == logging.NOTSET or root.level > level:
        root.setLevel(level)
    # Make sure our own subsystem loggers propagate at a useful level.
    logging.getLogger("raplmail").setLevel(level)
    return handler
