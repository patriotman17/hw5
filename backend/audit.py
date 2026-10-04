"""Append-only audit trail at output/audit_trail.json.

The file is a JSON array. Each write takes an exclusive cross-process lock
(fcntl.flock on a sidecar .lock file), reads the existing array, appends, and
atomically replaces the file, so earlier entries are never dropped even when
several ticket runs write at once. If the existing file is not a valid JSON
array we refuse to write rather than wipe it.
"""

from __future__ import annotations

import fcntl
import json
import os
import threading
from datetime import datetime, timezone
from typing import Any

from config import AUDIT_PATH

_lock = threading.Lock()
_LOCK_PATH = AUDIT_PATH.with_name(AUDIT_PATH.name + ".lock")
_MAX_PREVIEW_CHARS = 1500
_TRUNCATED_FIELDS = {"result"}


def preview(value: Any) -> Any:
    """Keep audit entries readable: long payloads are truncated, short ones kept as-is."""
    text = json.dumps(value, default=str)
    if len(text) <= _MAX_PREVIEW_CHARS:
        return value
    return text[:_MAX_PREVIEW_CHARS] + "...[truncated]"


def _read_existing() -> list[dict]:
    if not AUDIT_PATH.exists() or AUDIT_PATH.stat().st_size == 0:
        return []
    data = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise RuntimeError(f"{AUDIT_PATH} is not a JSON array; refusing to overwrite it.")
    return data


def read_entries() -> list[dict]:
    """All entries, oldest first. Safe without the lock: writers replace the file atomically."""
    return _read_existing()


def record(event: str, *, run_id: str, ticket_id: int, agent: str | None = None, **details: Any) -> dict:
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "run_id": run_id,
        "ticket_id": ticket_id,
        "agent": agent,
        "event": event,
        # Only raw MCP tool results are truncated; decisions, reasons, and errors are kept whole.
        **{k: preview(v) if k in _TRUNCATED_FIELDS else v for k, v in details.items()},
    }
    AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock, open(_LOCK_PATH, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            entries = _read_existing()
            entry["seq"] = len(entries) + 1
            entries.append(entry)
            tmp = AUDIT_PATH.with_name(f"{AUDIT_PATH.name}.{os.getpid()}.tmp")
            tmp.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")
            os.replace(tmp, AUDIT_PATH)
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
    return entry
