"""Reset data/campus_customs_new.db to the original data/campus_customs.db values.

Required before any full run that resolves all tickets, so earlier test
payments (cash, invoice status, lease dates) don't leak into the run.

CLI:  .venv/bin/python backend/db_reset.py
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import audit
from config import HW5_ROOT

ORIGINAL_DB = HW5_ROOT / "data" / "campus_customs.db"
WORKING_DB = HW5_ROOT / "data" / "campus_customs_new.db"


def _sha1(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def reset_db(reason: str = "manual reset") -> str:
    """Copy the original DB over the working copy and verify they are byte-identical."""
    if not ORIGINAL_DB.exists():
        raise FileNotFoundError(f"Original database not found: {ORIGINAL_DB}")
    before = _sha1(WORKING_DB) if WORKING_DB.exists() else None
    for suffix in ("-wal", "-shm", "-journal"):
        WORKING_DB.with_name(WORKING_DB.name + suffix).unlink(missing_ok=True)
    shutil.copyfile(ORIGINAL_DB, WORKING_DB)
    after = _sha1(WORKING_DB)
    if after != _sha1(ORIGINAL_DB):
        raise RuntimeError("Reset failed: working DB does not match the original.")
    audit.record(
        "db_reset", run_id="db_reset", ticket_id=0, agent=None, reason=reason,
        sha1_before=before, sha1_after=after, changed=before != after,
    )
    return after


if __name__ == "__main__":
    print(f"campus_customs_new.db reset to original (sha1 {reset_db()})")
