"""The Astro Max seed hover comes from the confirmed flight log, not a typo."""

import json
from hashlib import sha256
from pathlib import Path

from suas.calculations.from_log import estimate_cruise_power
from suas.calculations.gate import (
    fields_are_operational_grade,
    power_is_operational_grade,
)
from suas.flight_log_import import parse_flight_log
from suas.reference_data import AIRCRAFT_FILE, PAYLOAD_FILE, load_entries
from suas.schemas.provenance import FieldSource
from suas.seed_from_log import (
    APPLIED_CSV,
    APPLIED_SOURCE_URL,
    ASTRO_MAX_ID,
    FLIGHT_LOG_DIR,
    PREVIOUS_DERIVED_CRUISE_W,
    apply_hover_to_seed,
    hover_estimate_from_csv,
)

_054 = FLIGHT_LOG_DIR / APPLIED_CSV
_8F7 = FLIGHT_LOG_DIR / "8f757ee6.csv"
_6CA = FLIGHT_LOG_DIR / "6ca79cb1.csv"


def test_the_three_evidence_csvs_match_the_screened_medians() -> None:
    assert hover_estimate_from_csv(_054).median_w == 992.07
    assert hover_estimate_from_csv(_8F7).median_w == 685.15
    assert hover_estimate_from_csv(_6CA).median_w == 561.66


def test_the_evidence_csvs_match_the_published_digests() -> None:
    assert sha256(_054.read_bytes()).hexdigest() == (
        "2d09ebe8e06d36d16b1fe52344ebb3462d17c96113dc085fb4a5f6f7745986e8"
    )
    assert sha256(_8F7.read_bytes()).hexdigest() == (
        "64313dcedcd8e536cdc2b41631d76f2898eab243ebe851e31d41799d50960ca1"
    )
    assert sha256(_6CA.read_bytes()).hexdigest() == (
        "aebe18f0a6a3d31e0011ae98d0b567b59abd016d788f087743bbb2c09f8a0ffe"
    )


def test_applying_the_astro_max_log_writes_hover_and_leaves_cruise(
    tmp_path: Path,
) -> None:
    seed = tmp_path / "aircraft.json"
    seed.write_text(
        Path(__file__)
        .resolve()
        .parents[1]
        .joinpath("suas", "data", "aircraft.json")
        .read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    # Restore a pre-apply hover so the write is visible even after the seed
    # itself has already been updated.
    data = json.loads(seed.read_text(encoding="utf-8"))
    data[ASTRO_MAX_ID]["hover_power_w"]["value"] = 483.1
    data[ASTRO_MAX_ID]["hover_power_w"]["source"] = "derived"
    seed.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    record = apply_hover_to_seed(seed_path=seed, csv_path=_054)
    written = json.loads(seed.read_text(encoding="utf-8"))[ASTRO_MAX_ID]

    assert record.value == 992.07
    assert record.source is FieldSource.FLIGHT_LOG
    assert written["hover_power_w"]["value"] == 992.07
    assert written["hover_power_w"]["source"] == "flight_log"
    assert written["hover_power_w"]["source_url"] == APPLIED_SOURCE_URL
    assert "054112f4" in written["hover_power_w"]["notes"]
    assert "8f757ee6" in written["hover_power_w"]["notes"]
    assert "6ca79cb1" in written["hover_power_w"]["notes"]
    assert written["cruise_power_w"]["value"] == PREVIOUS_DERIVED_CRUISE_W
    assert written["cruise_power_w"]["source"] == "derived"
    assert "4.5 m/s" in written["cruise_power_w"]["notes"]


def test_the_astro_max_seed_hover_is_the_confirmed_flight_log() -> None:
    airframe = next(e for e in load_entries(AIRCRAFT_FILE) if e.id == ASTRO_MAX_ID)
    hover = airframe.provenance["hover_power_w"]
    cruise = airframe.provenance["cruise_power_w"]
    assert hover.value == 992.07
    assert hover.source is FieldSource.FLIGHT_LOG
    assert hover.source_url == APPLIED_SOURCE_URL
    assert "054112f4" in hover.notes
    assert "8f757ee6" in hover.notes
    assert "6ca79cb1" in hover.notes
    assert cruise.value == PREVIOUS_DERIVED_CRUISE_W
    assert cruise.source is FieldSource.DERIVED


def test_the_astro_max_log_cruise_is_not_catalog_cruise() -> None:
    """A 4.5 m/s cruise window must not be applied as 14 m/s catalog cruise."""
    parsed = parse_flight_log(_054.read_text(encoding="utf-8"))
    cruise = estimate_cruise_power(parsed.samples)
    assert cruise is not None
    assert cruise.median_w == 1047.32


def test_lab_pair_stays_blocked_after_the_hover_log() -> None:
    """Hover is now flight-log grade; cruise and cruise speed still are not."""
    airframe = next(e for e in load_entries(AIRCRAFT_FILE) if e.id == ASTRO_MAX_ID).provenance
    payload = next(e for e in load_entries(PAYLOAD_FILE) if e.id == "Sony_ILX_LR1").provenance
    assert airframe["hover_power_w"].is_operational_grade is True
    assert airframe["cruise_power_w"].is_operational_grade is False
    assert airframe["cruise_speed_mps"].is_operational_grade is False
    assert power_is_operational_grade(airframe, payload) is False
    assert fields_are_operational_grade(airframe, payload) is False
