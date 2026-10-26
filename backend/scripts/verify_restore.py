"""Verify a restored database: every acknowledgement still matches its plan.

Run after ``scripts/restore.sh`` with ``SUAS_DATABASE_URL`` pointing at the
restored database (docs/ops.md, Backup and restore). Exits 0 when every stored
acknowledgement's ``inputs_hash`` equals its checkpoint's sealed assessment, 1
naming each thread that does not, and 2 when the database is not Postgres,
since only Postgres keeps checkpoints.
"""

import asyncio
import sys

from suas.config import get_settings
from suas.db.engine import create_engine, create_session_factory
from suas.db.restore_check import verify_acknowledgements
from suas.graph.checkpointer import build_checkpointer


async def _run() -> int:
    settings = get_settings()
    if not settings.uses_postgres:
        print("verify_restore: SUAS_DATABASE_URL must be the restored Postgres", file=sys.stderr)
        return 2
    engine = create_engine(settings.database_url)
    try:
        async with build_checkpointer(settings) as checkpointer:
            check = await verify_acknowledgements(create_session_factory(engine), checkpointer)
    finally:
        await engine.dispose()
    for line in check.broken:
        print(f"[FAIL] {line}")
    print(
        f"{check.checked - len(check.broken)} acknowledgement(s) verified, {len(check.broken)} broken"
    )
    return 1 if check.broken else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_run()))
