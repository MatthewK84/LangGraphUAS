#!/usr/bin/env python3
"""Refresh the pinned Blue UAS snapshot from a local public file.

Ingest is deliberate and out-of-band: this script never runs on the request
path. Pass a JSON object with an `items` list (and optional `source_url`)
already retrieved from a public source. The script hashes the items, stamps
`fetched_at`, and writes the file the operational gate reads.

Usage:
    python3 backend/scripts/refresh_blue_list.py --from-file public.json
    python3 backend/scripts/refresh_blue_list.py --from-file public.json --output path.json
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suas.blue_list import configured_snapshot_path, refresh_from_file
from suas.config import get_settings


def main() -> int:
    """Write a hashed, time-stamped snapshot and print where it went."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-file",
        required=True,
        type=Path,
        help="local JSON with an items list, already retrieved from a public source",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="destination path; default is SUAS_BLUE_LIST_SNAPSHOT or the data dir",
    )
    parsed = parser.parse_args()
    if not parsed.from_file.is_file():
        print(f"error: {parsed.from_file} does not exist", file=sys.stderr)
        return 1
    dest = parsed.output or configured_snapshot_path(get_settings().blue_list_snapshot)
    written = refresh_from_file(parsed.from_file, dest, fetched_at=datetime.now(UTC))
    print(
        f"wrote {dest} ({len(written.items)} items, {written.content_hash}, "
        f"fetched_at={written.fetched_at.isoformat()})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
