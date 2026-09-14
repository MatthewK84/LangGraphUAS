"""The reference-data linter.

Every number this system plans with must say where it came from. These tests are
the enforcement: they fail on a bare value, on a datasheet claim with no URL
behind it, and on a citation inventory that has drifted from the data it
describes.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from suas.calculations.gate import (
    REQUIRED_PROVENANCE_AIRCRAFT,
    REQUIRED_PROVENANCE_PAYLOAD,
)
from suas.errors import SeedDataError
from suas.reference_data import (
    AIRCRAFT_FILE,
    DATA_DIR,
    PAYLOAD_FILE,
    ReferenceEntry,
    load_entries,
)
from suas.schemas.provenance import FieldSource

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_GENERATOR = _REPO_ROOT / "backend" / "scripts" / "generate_citations.py"

_EXPECTED_UNITS: dict[str, str] = {
    "weight_kg": "kg",
    "max_payload_kg": "kg",
    "battery_wh": "Wh",
    "max_wind_mps": "m/s",
    "cruise_speed_mps": "m/s",
    "hover_power_w": "W",
    "cruise_power_w": "W",
    "max_temp_c": "C",
    "min_temp_c": "C",
    "pack_min_takeoff_c": "C",
    "power_draw_w": "W",
}

# A source that asserts someone read a document must name the document. The
# weaker sources must at least say what they rest on.
_NEEDS_URL: frozenset[FieldSource] = frozenset({FieldSource.DATASHEET})
_NEEDS_NOTES: frozenset[FieldSource] = frozenset(
    {FieldSource.DERIVED, FieldSource.ESTIMATE, FieldSource.UNKNOWN, FieldSource.SECONDARY}
)


def _all_entries() -> list[tuple[str, ReferenceEntry]]:
    return [(AIRCRAFT_FILE, entry) for entry in load_entries(AIRCRAFT_FILE)] + [
        (PAYLOAD_FILE, entry) for entry in load_entries(PAYLOAD_FILE)
    ]


@pytest.mark.parametrize("filename", [AIRCRAFT_FILE, PAYLOAD_FILE])
def test_reference_files_parse(filename: str) -> None:
    entries = load_entries(filename)
    assert entries, filename


def test_every_required_field_is_present_and_accounted_for() -> None:
    for filename, entry in _all_entries():
        required = (
            REQUIRED_PROVENANCE_AIRCRAFT
            if filename == AIRCRAFT_FILE
            else REQUIRED_PROVENANCE_PAYLOAD
        )
        missing = required - entry.provenance.keys()
        assert not missing, f"{entry.id} is missing provenance for: {sorted(missing)}"


def test_a_datasheet_claim_must_cite_the_datasheet() -> None:
    """The whole point. Claiming a manufacturer document means naming it."""
    for _, entry in _all_entries():
        for field, record in entry.provenance.items():
            if record.source in _NEEDS_URL:
                assert record.source_url, f"{entry.id}.{field}: source=datasheet with no URL"
                assert record.retrieved_at, (
                    f"{entry.id}.{field}: source=datasheet with no retrieval date"
                )


def test_weak_sources_say_what_they_rest_on() -> None:
    for _, entry in _all_entries():
        for field, record in entry.provenance.items():
            if record.source in _NEEDS_NOTES:
                assert record.notes.strip(), (
                    f"{entry.id}.{field}: source={record.source.value} with no notes"
                )


def test_units_are_what_the_field_name_says() -> None:
    for _, entry in _all_entries():
        for field, record in entry.provenance.items():
            expected = _EXPECTED_UNITS.get(field)
            assert expected is not None, f"{entry.id}.{field}: no expected unit registered"
            assert record.unit == expected, f"{entry.id}.{field}: unit {record.unit!r}"


def test_a_bare_number_is_rejected() -> None:
    """The linter has to fail on the thing it exists to prevent."""
    import suas.reference_data as reference_data

    bad = {"X": {"id": "X", "name": "X", "weight_kg": 2.0}}
    path = DATA_DIR / "_lint_probe.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    try:
        with pytest.raises(SeedDataError, match="bare value"):
            reference_data.load_entries("_lint_probe.json")
    finally:
        path.unlink()


def test_unknown_provenance_keys_are_rejected() -> None:
    import suas.reference_data as reference_data

    bad = {
        "X": {
            "id": "X",
            "name": "X",
            "weight_kg": {
                "value": 2.0,
                "unit": "kg",
                "source": "estimate",
                "vibes": "good",
            },
        }
    }
    path = DATA_DIR / "_lint_probe2.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    try:
        with pytest.raises(SeedDataError, match="invalid provenance"):
            reference_data.load_entries("_lint_probe2.json")
    finally:
        path.unlink()


def test_citations_file_is_current() -> None:
    """CITATIONS.md is generated. A stale one is a lie about the data."""
    result = subprocess.run(
        [sys.executable, str(_GENERATOR), "--check"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
