"""Datasheet promotion invariants (#74 / #75).

Red first: every source=datasheet field must cite a manufacturer URL, a
retrieval date, and a quoted line in its notes. Teal Golden Eagle and Teal 2
are separate airframes.
"""

from __future__ import annotations

from suas.reference_data import AIRCRAFT_FILE, PAYLOAD_FILE, load_entries
from suas.schemas.provenance import FieldSource

_QUOTE_MARKERS = ("'", '"', "“", "”", "«", "»")
_RETRIEVED = "2026-10-28"
_MANUFACTURER_HOST_HINTS = (
    "skydio.com",
    "parrot.com",
    "tealdrones.com",
    "freeflysystems.com",
    "inspiredflight.com",
    "docs.inspiredflight.com",
    "oem.flir.com",
    "flir.com",
    "sony.net",
    "sony.jp",
    "sony.com",
    "nextvision-sys.com",
    "workswell.eu",
    "my.workswell.eu",
    "trilliumeng.com",
)


def _all_entries():
    return list(load_entries(AIRCRAFT_FILE)) + list(load_entries(PAYLOAD_FILE))


def test_teal_golden_eagle_and_teal_2_are_separate_airframes() -> None:
    airframes = {entry.id: entry for entry in load_entries(AIRCRAFT_FILE)}
    assert "Teal_Golden_Eagle" in airframes
    assert "Teal_2" in airframes
    ge = airframes["Teal_Golden_Eagle"]
    t2 = airframes["Teal_2"]
    assert "Teal 2" not in ge.name
    assert ge.name == "Teal Golden Eagle"
    assert t2.name == "Teal 2"
    assert ge.provenance["max_payload_kg"].value == 0.075
    assert ge.provenance["max_payload_kg"].source is FieldSource.DATASHEET
    assert t2.provenance["weight_kg"].value == 1.25
    assert t2.provenance["weight_kg"].source is FieldSource.DATASHEET


def test_every_datasheet_field_cites_url_date_and_quote() -> None:
    for entry in _all_entries():
        for field, record in entry.provenance.items():
            if record.source is not FieldSource.DATASHEET:
                continue
            label = f"{entry.id}.{field}"
            assert record.source_url, f"{label}: datasheet with no URL"
            assert any(host in record.source_url for host in _MANUFACTURER_HOST_HINTS), (
                f"{label}: URL is not a manufacturer host: {record.source_url}"
            )
            assert record.retrieved_at == _RETRIEVED, (
                f"{label}: retrieved_at {record.retrieved_at!r} != {_RETRIEVED!r}"
            )
            notes = record.notes or ""
            assert notes.strip(), f"{label}: datasheet notes empty"
            has_quote = any(m in notes for m in _QUOTE_MARKERS) or "Quote:" in notes
            assert has_quote, f"{label}: notes must quote the datasheet line"


def test_astro_wind_uses_conservative_end_of_advisory() -> None:
    record = next(
        e for e in load_entries(AIRCRAFT_FILE) if e.id == "Freefly_Astro_Max"
    ).provenance["max_wind_mps"]
    assert record.value == 8.0
    assert record.source is FieldSource.DATASHEET
    assert "8" in record.notes and "10" in record.notes


def test_if1200a_battery_is_dual_pack_system_energy() -> None:
    record = next(
        e for e in load_entries(AIRCRAFT_FILE) if e.id == "Inspired_Flight_IF1200A"
    ).provenance["battery_wh"]
    assert record.value == 1420.8
    assert record.source is FieldSource.DATASHEET
    assert "710.4" in record.notes
    assert "two" in record.notes.lower() or "2 x" in record.notes.lower() or "2x" in record.notes.lower()


def test_teal_2_unpublished_fields_are_unknown_not_invented() -> None:
    t2 = next(e for e in load_entries(AIRCRAFT_FILE) if e.id == "Teal_2")
    for field in ("battery_wh", "max_payload_kg", "hover_power_w", "cruise_power_w"):
        record = t2.provenance[field]
        assert record.source is FieldSource.UNKNOWN, field
        assert "not published" in record.notes.lower(), field
