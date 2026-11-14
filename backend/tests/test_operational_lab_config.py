"""Operational mode is scoped to one lab configuration and is off by default."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from suas.blue_list import write_snapshot
from suas.calculations.assessment import assess_mission, build_assessment
from suas.calculations.gate import (
    LAB_OPERATIONAL_AIRFRAME_ID,
    LAB_OPERATIONAL_PAYLOAD_ID,
    GateInputs,
    configuration_is_lab_operational,
    fields_are_operational_grade,
    operational_blockers,
)
from suas.config import get_settings
from suas.schemas.assessment import AssessmentMode, Blocker, blocker_reason
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.provenance import FieldProvenance, FieldSource
from suas.schemas.requests import MissionParams, MissionRequest
from suas.schemas.responses import WeatherReading, WeatherSource

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

_NOW = datetime(2026, 11, 14, 20, 0, 0, tzinfo=UTC)

_REQUIRED_AIRCRAFT = (
    "weight_kg",
    "max_payload_kg",
    "battery_wh",
    "max_wind_mps",
    "cruise_speed_mps",
    "hover_power_w",
    "cruise_power_w",
    "max_temp_c",
    "min_temp_c",
)
_REQUIRED_PAYLOAD = ("weight_kg", "power_draw_w")


def _record(source: FieldSource) -> FieldProvenance:
    return FieldProvenance(value=1.0, unit="u", source=source, confidence="high")


def _provenance(
    *,
    aircraft_source: FieldSource = FieldSource.DATASHEET,
    payload_source: FieldSource = FieldSource.DATASHEET,
    aircraft_overrides: dict[str, FieldSource] | None = None,
) -> tuple[dict[str, FieldProvenance], dict[str, FieldProvenance]]:
    aircraft = {field: _record(aircraft_source) for field in _REQUIRED_AIRCRAFT}
    if aircraft_overrides:
        for field, source in aircraft_overrides.items():
            aircraft[field] = _record(source)
    payload = {field: _record(payload_source) for field in _REQUIRED_PAYLOAD}
    return aircraft, payload


def _aircraft(
    *,
    model_id: str = LAB_OPERATIONAL_AIRFRAME_ID,
    provenance: dict[str, FieldProvenance] | None = None,
) -> Aircraft:
    if provenance is None:
        provenance, _ = _provenance()
    return Aircraft(
        id=model_id,
        name="lab airframe",
        weight_kg=13.6,
        max_payload_kg=3.0,
        battery_wh=899.0,
        max_wind_mps=10.0,
        cruise_speed_mps=15.0,
        hover_power_w=450.0,
        cruise_power_w=405.0,
        max_temp_c=45.0,
        min_temp_c=-20.0,
        provenance=provenance,
    )


def _payload(
    *,
    model_id: str = LAB_OPERATIONAL_PAYLOAD_ID,
    provenance: dict[str, FieldProvenance] | None = None,
) -> Payload:
    if provenance is None:
        _, provenance = _provenance()
    return Payload(
        id=model_id,
        name="lab payload",
        weight_kg=0.25,
        power_draw_w=6.5,
        provenance=provenance,
    )


_PARAMS = MissionParams(
    distance_m=2000.0,
    hover_time_s=180.0,
    target_altitude_m=80.0,
    elevation_m=0.0,
    latitude=34.0,
    longitude=-80.0,
)

_LIVE = WeatherReading(
    temperature_c=18.0,
    wind_speed_mps=3.0,
    wind_gust_mps=4.0,
    wind_direction=180.0,
    humidity_percent=45.0,
    conditions="clear",
    source=WeatherSource.LIVE,
    fetched_at=_NOW,
)


def _fresh_snapshot(path: Path) -> None:
    write_snapshot(
        path,
        items=[{"name": "lab fixture, not a published clearance"}],
        source_url="file:fixture",
        fetched_at=_NOW - timedelta(hours=1),
    )


def _plan(
    *,
    aircraft: Aircraft,
    payload: Payload,
    requested_mode: AssessmentMode = AssessmentMode.OPERATIONAL,
    snapshot: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SUAS_BLUE_LIST_SNAPSHOT", str(snapshot))
    get_settings.cache_clear()
    try:
        calculations = assess_mission(
            aircraft=aircraft, payload=payload, params=_PARAMS, weather=_LIVE
        )
        return build_assessment(
            calculations=calculations,
            inputs={"weather": _LIVE.model_dump(mode="json")},
            requested_mode=requested_mode,
            weather=_LIVE,
            aircraft=aircraft,
            payload=payload,
            now=_NOW,
        )
    finally:
        get_settings.cache_clear()


def test_plan_request_defaults_to_advisory() -> None:
    """Operational mode is off unless the caller asks for it."""
    request = MissionRequest.model_validate(
        {
            "aircraft_id": LAB_OPERATIONAL_AIRFRAME_ID,
            "payload_id": LAB_OPERATIONAL_PAYLOAD_ID,
            "mission_params": _PARAMS.model_dump(),
        }
    )
    assert request.assessment_mode is AssessmentMode.ADVISORY


def test_only_the_named_lab_pair_is_in_scope() -> None:
    assert configuration_is_lab_operational(
        LAB_OPERATIONAL_AIRFRAME_ID, LAB_OPERATIONAL_PAYLOAD_ID
    )
    assert not configuration_is_lab_operational("Freefly_Alta_X", LAB_OPERATIONAL_PAYLOAD_ID)
    assert not configuration_is_lab_operational(LAB_OPERATIONAL_AIRFRAME_ID, "None")
    assert not configuration_is_lab_operational(None, None)


def test_a_non_grade_required_field_is_not_operational_grade() -> None:
    aircraft, payload = _provenance(aircraft_overrides={"cruise_speed_mps": FieldSource.ESTIMATE})
    assert not fields_are_operational_grade(aircraft, payload)
    aircraft, payload = _provenance()
    assert fields_are_operational_grade(aircraft, payload)


def test_a_non_grade_payload_field_is_not_operational_grade() -> None:
    aircraft, payload = _provenance()
    payload["power_draw_w"] = _record(FieldSource.ESTIMATE)
    assert not fields_are_operational_grade(aircraft, payload)


def test_wrong_airframe_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fresh_snapshot(tmp_path / "snap.json")
    assessment = _plan(
        aircraft=_aircraft(model_id="Freefly_Alta_X"),
        payload=_payload(),
        snapshot=tmp_path / "snap.json",
        monkeypatch=monkeypatch,
    )
    assert assessment.mode is AssessmentMode.ADVISORY
    assert Blocker.CONFIGURATION_NOT_LAB_OPERATIONAL in assessment.blockers
    assert "Freefly Astro Max" in blocker_reason(Blocker.CONFIGURATION_NOT_LAB_OPERATIONAL)
    assert "Sony ILX-LR1" in blocker_reason(Blocker.CONFIGURATION_NOT_LAB_OPERATIONAL)


def test_wrong_payload_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fresh_snapshot(tmp_path / "snap.json")
    assessment = _plan(
        aircraft=_aircraft(),
        payload=_payload(model_id="None"),
        snapshot=tmp_path / "snap.json",
        monkeypatch=monkeypatch,
    )
    assert assessment.mode is AssessmentMode.ADVISORY
    assert Blocker.CONFIGURATION_NOT_LAB_OPERATIONAL in assessment.blockers


def test_an_estimate_field_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _fresh_snapshot(tmp_path / "snap.json")
    aircraft_prov, payload_prov = _provenance(
        aircraft_overrides={"cruise_speed_mps": FieldSource.ESTIMATE}
    )
    assessment = _plan(
        aircraft=_aircraft(provenance=aircraft_prov),
        payload=_payload(provenance=payload_prov),
        snapshot=tmp_path / "snap.json",
        monkeypatch=monkeypatch,
    )
    assert assessment.mode is AssessmentMode.ADVISORY
    assert Blocker.FIELD_NOT_OPERATIONAL_GRADE in assessment.blockers
    assert Blocker.CONFIGURATION_NOT_LAB_OPERATIONAL not in assessment.blockers


def test_lab_configuration_is_operational_only_when_every_blocker_is_cleared(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pin the exact inputs that would grant operational in a fixture environment."""
    _fresh_snapshot(tmp_path / "snap.json")
    assessment = _plan(
        aircraft=_aircraft(),
        payload=_payload(),
        snapshot=tmp_path / "snap.json",
        monkeypatch=monkeypatch,
    )
    assert assessment.mode is AssessmentMode.OPERATIONAL
    assert assessment.blockers == []


def test_production_grade_values_on_the_lab_pair_still_do_not_clear_the_gate() -> None:
    """Seed hover/cruise are derived and cruise speed is an estimate, so no GO."""
    blockers = operational_blockers(
        GateInputs(
            weather_is_live=True,
            weather_degraded=False,
            assessment_is_complete=True,
            provenance_is_complete=True,
            power_is_operational_grade=False,
            corpus_quarantined=False,
            blue_list_snapshot_available=True,
            blue_list_snapshot_stale=False,
            configuration_is_lab_operational=True,
            fields_are_operational_grade=False,
        )
    )
    assert Blocker.POWER_NOT_OPERATIONAL_GRADE in blockers
    assert Blocker.FIELD_NOT_OPERATIONAL_GRADE in blockers
    assert Blocker.CONFIGURATION_NOT_LAB_OPERATIONAL not in blockers
