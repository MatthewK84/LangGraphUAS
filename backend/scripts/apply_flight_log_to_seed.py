#!/usr/bin/env python3
"""Write the Astro Max flight-log hover estimate into aircraft.json.

The ingest API applies a log to the runtime database only. This script is the
explicit seed update: it uses the same estimator, writes hover_power_w from
log 054112f4 (992.07 W), and leaves cruise_power_w unchanged.

Usage:
    python3 backend/scripts/apply_flight_log_to_seed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suas.seed_from_log import apply_hover_to_seed


def main() -> int:
    """Apply the bundled 054112f4 CSV to the bundled seed and print the figure."""
    record = apply_hover_to_seed()
    print(f"hover_power_w={record.value} W source={record.source.value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
