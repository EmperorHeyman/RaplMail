"""Where opening a message spends its time.

A message body comes from the server the first time it's opened: wait for the
account's connection (one per account, shared with background preloads and
flag updates), connect and sign in if it went cold, download the raw message,
then parse it. Any of these can stall, and "it just spins" says nothing about
which. Every body load records its phases here so the reader can say what it's
waiting for while it waits, and Settings -> Debug can show the recent history
(and slow ones are logged).
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from datetime import datetime, timezone

log = logging.getLogger("raplmail.open")

# A load slower than this (seconds) is logged with its phase breakdown.
SLOW_SECONDS = 3.0


class LoadTrace:
    """One body load: the phase it's in now and how long each earlier one took."""

    def __init__(self, message_id: int, why: str, account_id: int | None, subject: str = "") -> None:
        self.message_id = message_id
        self.why = why or "open"
        self.account_id = account_id
        self.subject = subject or ""
        self.at = datetime.now(timezone.utc).isoformat()
        self.started = time.monotonic()
        self.phase = ""
        self.phase_started = self.started
        self.phases: list[tuple[str, float]] = []
        self.info: dict = {}
        self.error = ""
        self.done = False
        self.total = 0.0

    def mark(self, name: str, **info) -> None:
        """End the current phase and start `name`."""
        now = time.monotonic()
        if self.phase:
            self.phases.append((self.phase, now - self.phase_started))
        self.phase, self.phase_started = name, now
        if info:
            self.info.update(info)

    def note(self, **info) -> None:
        self.info.update(info)

    def finish(self, error: str = "") -> None:
        now = time.monotonic()
        if self.phase:
            self.phases.append((self.phase, now - self.phase_started))
        self.phase = ""
        self.error = error
        self.done = True
        self.total = now - self.started

    def snapshot(self) -> dict:
        now = time.monotonic()
        phases = [{"name": n, "ms": round(d * 1000)} for n, d in self.phases]
        return {
            "message_id": self.message_id, "why": self.why, "account_id": self.account_id,
            "subject": self.subject, "at": self.at,
            "phase": self.phase,
            "phase_ms": round((now - self.phase_started) * 1000) if self.phase else 0,
            "elapsed_ms": round(((self.total if self.done else now - self.started)) * 1000),
            "phases": phases, "info": dict(self.info),
            "error": self.error, "done": self.done,
        }

    def summary(self) -> str:
        parts = []
        for n, d in self.phases:
            if d >= 0.05:
                parts.append(f"{n} {d:.1f}s")
        if self.info.get("bytes"):
            parts.append(f"{self.info['bytes'] / 1_000_000:.1f} MB")
        return ", ".join(parts) or "-"


class LoadTracker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: dict[int, LoadTrace] = {}
        self._recent: deque[LoadTrace] = deque(maxlen=60)

    def start(self, message_id: int, why: str, account_id: int | None, subject: str = "") -> LoadTrace:
        t = LoadTrace(message_id, why, account_id, subject)
        with self._lock:
            self._active[message_id] = t
        return t

    def end(self, trace: LoadTrace, error: str = "") -> None:
        trace.finish(error)
        with self._lock:
            if self._active.get(trace.message_id) is trace:
                del self._active[trace.message_id]
            self._recent.appendleft(trace)
        if error:
            log.warning("couldn't load message %s (%s) after %.1fs: %s [%s]",
                        trace.message_id, trace.why, trace.total, error, trace.summary())
        elif trace.total >= SLOW_SECONDS:
            log.warning("slow load: message %s (%s) took %.1fs [%s]",
                        trace.message_id, trace.why, trace.total, trace.summary())

    def status(self, message_id: int) -> dict | None:
        """The live trace of a load in progress, else the latest finished one."""
        with self._lock:
            t = self._active.get(message_id)
            if t is None:
                t = next((r for r in self._recent if r.message_id == message_id), None)
            return t.snapshot() if t else None

    def recent(self) -> list[dict]:
        with self._lock:
            active = [t.snapshot() for t in self._active.values()]
            return active + [t.snapshot() for t in self._recent]


tracker = LoadTracker()
