"""Promote a flight-log hover estimate into the bundled seed.

``POST /api/logs?apply=true`` writes the runtime database only. The seed file
is a separate, explicit act: this module uses the same parser and hover
estimator, then writes ``aircraft.json``. Cruise is left alone unless the
caller opts in, because a log flown far below catalog cruise speed is not
evidence for ``cruise_power_w``.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

from suas.calculations.from_log import PowerEstimate, estimate_hover_power
from suas.flight_log_import import parse_flight_log
from suas.reference_data import DATA_DIR
from suas.schemas.provenance import FieldProvenance, FieldSource

AIRCRAFT_SEED: Final[Path] = DATA_DIR / "aircraft.json"
FLIGHT_LOG_DIR: Final[Path] = DATA_DIR / "flight_logs"
ASTRO_MAX_ID: Final[str] = "Freefly_Astro_Max"

# The only screened log labelled Astro Max, and the conservative hover median.
APPLIED_CSV: Final[str] = "054112f4.csv"
APPLIED_SOURCE_URL: Final[str] = (
    "https://review.px4.io/plot_app?log=054112f4-683e-49c2-8777-097f5fe35df2"
)
APPLIED_RETRIEVED_AT: Final[str] = "2026-11-14"

# Leave the previous derived cruise figure in place; see apply_hover_to_seed.
PREVIOUS_DERIVED_HOVER_W: Final[float] = 483.1
PREVIOUS_DERIVED_CRUISE_W: Final[float] = 434.8


def hover_estimate_from_csv(path: Path) -> PowerEstimate:
    """Return the hover estimate the ingest path would record for this CSV."""
    parsed = parse_flight_log(path.read_text(encoding="utf-8"))
    estimate = estimate_hover_power(parsed.samples)
    if estimate is None:
        raise ValueError(f"{path} produced no hover estimate")
    return estimate


def _hover_notes(estimate: PowerEstimate) -> str:
    """Return seed notes that name the applied log and the supporting two."""
    return (
        f"Median of {estimate.sample_count} selected hover samples from PX4 "
        "Flight Review log 054112f4-683e-49c2-8777-097f5fe35df2 (CC BY 4.0). "
        f"Interquartile range {estimate.iqr_w} W. Source SHA-256 "
        "5bcef1faf0bcd0a72e5ac38a4b36150951635f80edd5d888c4ae942f50b50618, "
        "retrieved 2026-11-14 14:53:58 EST. This is the only screened log "
        "labelled Astro Max, and the conservative (highest) of the three "
        "usable hover medians. Supporting evidence, not applied: "
        "8f757ee6-8978-4c7c-badc-0544b3a83906 (685.15 W, 152 samples, not "
        "labelled Astro Max) and 6ca79cb1-017c-457d-b1c5-f4f401d87eb0 "
        "(561.66 W, 3536 samples, not labelled Astro Max)."
    )


def _cruise_notes() -> str:
    """Return notes that explain why catalog cruise power was not updated."""
    return (
        f"Previously derived as 0.90 * the datasheet-endurance hover "
        f"({PREVIOUS_DERIVED_HOVER_W} W). Not updated from the flight logs: "
        "the Astro Max log's cruise window was flown at a median 4.5 m/s, not "
        "the 14 m/s catalog cruise, so that power is not evidence for catalog "
        "cruise_power_w. Not recomputed from the new hover figure, because "
        "that would invent a cruise number the logs do not support."
    )


def apply_hover_to_seed(
    *,
    airframe_id: str = ASTRO_MAX_ID,
    csv_path: Path | None = None,
    seed_path: Path | None = None,
) -> FieldProvenance:
    """Write the CSV's hover estimate into the seed; leave cruise unchanged."""
    seed = seed_path or AIRCRAFT_SEED
    csv = csv_path or (FLIGHT_LOG_DIR / APPLIED_CSV)
    estimate = hover_estimate_from_csv(csv)
    record = FieldProvenance(
        value=estimate.median_w,
        unit="W",
        source=FieldSource.FLIGHT_LOG,
        source_url=APPLIED_SOURCE_URL,
        retrieved_at=APPLIED_RETRIEVED_AT,
        confidence=estimate.confidence,
        notes=_hover_notes(estimate),
    )
    data = json.loads(seed.read_text(encoding="utf-8"))
    entry = data[airframe_id]
    entry["hover_power_w"] = record.model_dump(mode="json")
    cruise = dict(entry["cruise_power_w"])
    cruise["notes"] = _cruise_notes()
    entry["cruise_power_w"] = cruise
    seed.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return record
