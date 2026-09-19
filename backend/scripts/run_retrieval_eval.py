#!/usr/bin/env python3
"""Run the retrieval evaluation and print or write the baseline.

Offline. Builds a throwaway database, ingests the synthetic evaluation corpus,
runs every fixture through the same ``retrieve()`` the planner calls, and
reports metrics with Wilson intervals.

    python3 backend/scripts/run_retrieval_eval.py
    python3 backend/scripts/run_retrieval_eval.py --write

The measurement itself lives in ``suas.eval.harness`` so that this script and
the CI gate in ``tests/test_rag_gates.py`` cannot drift apart.

Refreshing the baseline is a deliberate act: --write, then a commit whose
message says why the numbers moved. A baseline that updates itself records
nothing.
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from suas.db.models import Base
from suas.eval.harness import BASELINE, measure


async def run() -> dict[str, object]:
    """Measure against a throwaway in-memory database."""
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    try:
        return await measure(async_sessionmaker(engine, expire_on_commit=False))
    finally:
        await engine.dispose()


def main() -> int:
    """Run the evaluation and print or write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="update the committed baseline")
    parsed = parser.parse_args()

    report = asyncio.run(run())
    rendered = json.dumps(report, indent=2) + "\n"
    if parsed.write:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(rendered, encoding="utf-8")
        print(f"wrote {BASELINE}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
