"""Freshness of the pinned Blue UAS snapshot.

A snapshot of any age used to be treated as current, or — more accurately —
no snapshot was stored at all and the gate always raised UNAVAILABLE. Age
must be judged against a configured threshold, and a missing or unreadable
date is not the same as a stale one.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from suas.blue_list import (
    DEFAULT_BLUE_LIST_MAX_AGE_S,
    compute_items_hash,
    load_snapshot,
    refresh_from_file,
    snapshot_fetched_at,
    write_snapshot,
)
from suas.calculations.assessment import assess_mission, build_assessment
from suas.calculations.gate import (
    GateInputs,
    blue_list_snapshot_is_stale,
    operational_blockers,
)
from suas.schemas.assessment import AssessmentMode, Blocker
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import WeatherReading, WeatherSource

_NOW = datetime(2026, 11, 14, 20, 0, 0, tzinfo=UTC)
_MAX_AGE_S = 7 * 24 * 3600


def _snapshot(
    fetched_at: str | None,
    items: list[dict[str, str]] | None = None,
    *,
    hash_value: str | None = None,
) -> dict[str, object]:
    body_items = items if items is not None else [{"id": "example", "status": "cleared"}]
    payload: dict[str, object] = {
        "source_url": "https://bluelist.dcma.mil/",
        "items": body_items,
        "content_hash": hash_value or compute_items_hash(body_items),
    }
    if fetched_at is not None:
        payload["fetched_at"] = fetched_at
    return payload


def test_default_threshold_is_seven_days() -> None:
    """ADR-002: the default is seven days, and it is configuration, not a literal in the gate."""
    assert DEFAULT_BLUE_LIST_MAX_AGE_S == 7 * 24 * 3600


def test_a_snapshot_exactly_at_the_threshold_is_not_stale() -> None:
    fetched_at = _NOW - timedelta(seconds=_MAX_AGE_S)
    assert blue_list_snapshot_is_stale(fetched_at, now=_NOW, max_age_s=_MAX_AGE_S) is False


def test_a_snapshot_one_second_over_the_threshold_is_stale() -> None:
    fetched_at = _NOW - timedelta(seconds=_MAX_AGE_S + 1)
    assert blue_list_snapshot_is_stale(fetched_at, now=_NOW, max_age_s=_MAX_AGE_S) is True


def test_a_missing_snapshot_date_is_not_called_stale() -> None:
    """No date means we cannot assert clearance, not that the snapshot is old."""
    assert blue_list_snapshot_is_stale(None, now=_NOW, max_age_s=_MAX_AGE_S) is False


def test_an_unparseable_snapshot_date_is_unknown() -> None:
    assert snapshot_fetched_at({"fetched_at": "not-a-date"}) is None
    assert snapshot_fetched_at({}) is None
    assert snapshot_fetched_at({"fetched_at": ""}) is None


def test_a_naive_snapshot_date_is_unknown() -> None:
    """A timestamp without a zone cannot be aged honestly."""
    assert snapshot_fetched_at({"fetched_at": "2026-11-14T20:00:00"}) is None


def test_gate_raises_unavailable_when_the_snapshot_is_missing() -> None:
    blockers = operational_blockers(
        GateInputs(
            weather_is_live=True,
            weather_degraded=False,
            assessment_is_complete=True,
            provenance_is_complete=True,
            power_is_operational_grade=True,
            blue_list_snapshot_available=False,
            blue_list_snapshot_stale=False,
        )
    )
    assert Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE in blockers
    assert Blocker.BLUE_LIST_SNAPSHOT_STALE not in blockers


def test_gate_raises_stale_when_the_pinned_snapshot_is_too_old() -> None:
    blockers = operational_blockers(
        GateInputs(
            weather_is_live=True,
            weather_degraded=False,
            assessment_is_complete=True,
            provenance_is_complete=True,
            power_is_operational_grade=True,
            blue_list_snapshot_available=True,
            blue_list_snapshot_stale=True,
        )
    )
    assert Blocker.BLUE_LIST_SNAPSHOT_STALE in blockers
    assert Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE not in blockers
    assert blockers.count(Blocker.BLUE_LIST_SNAPSHOT_STALE) == 1


def test_a_fresh_snapshot_is_not_a_blue_list_blocker() -> None:
    blockers = operational_blockers(
        GateInputs(
            weather_is_live=True,
            weather_degraded=False,
            assessment_is_complete=True,
            provenance_is_complete=True,
            power_is_operational_grade=True,
            blue_list_snapshot_available=True,
            blue_list_snapshot_stale=False,
        )
    )
    assert blockers == []


def test_a_mismatched_content_hash_is_unavailable(tmp_path: Path) -> None:
    path = tmp_path / "blue_list_snapshot.json"
    path.write_text(
        json.dumps(_snapshot("2026-11-14T20:00:00Z", hash_value="sha256:deadbeef")),
        encoding="utf-8",
    )
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.hash_matches is False
    assert loaded.usable_fetched_at is None


def test_write_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "blue_list_snapshot.json"
    items = [{"id": "cfg-1", "status": "cleared"}]
    written = write_snapshot(
        path,
        items=items,
        source_url="https://bluelist.dcma.mil/",
        fetched_at=_NOW,
    )
    loaded = load_snapshot(path)
    assert loaded is not None
    assert loaded.hash_matches is True
    assert loaded.usable_fetched_at == _NOW
    assert loaded.content_hash == written.content_hash
    assert loaded.content_hash.startswith("sha256:")


def test_load_snapshot_returns_none_when_the_file_is_missing(tmp_path: Path) -> None:
    assert load_snapshot(tmp_path / "missing.json") is None


def test_stale_snapshot_cannot_yield_operational(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "blue_list_snapshot.json"
    write_snapshot(
        path,
        items=[{"id": "cfg-1", "status": "cleared"}],
        source_url="https://bluelist.dcma.mil/",
        fetched_at=_NOW - timedelta(seconds=_MAX_AGE_S + 1),
    )
    monkeypatch.setenv("SUAS_BLUE_LIST_SNAPSHOT", str(path))
    monkeypatch.setenv("SUAS_BLUE_LIST_MAX_AGE_S", str(_MAX_AGE_S))
    from suas.config import get_settings

    get_settings.cache_clear()
    try:
        assessment = _plan_assessment(now=_NOW, requested=AssessmentMode.OPERATIONAL)
        assert assessment.mode is AssessmentMode.ADVISORY
        assert assessment.is_operational is False
        assert Blocker.BLUE_LIST_SNAPSHOT_STALE in assessment.blockers
    finally:
        get_settings.cache_clear()


def test_advisory_still_produces_a_plan_with_a_stale_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "blue_list_snapshot.json"
    write_snapshot(
        path,
        items=[{"id": "cfg-1", "status": "cleared"}],
        source_url="https://bluelist.dcma.mil/",
        fetched_at=_NOW - timedelta(seconds=_MAX_AGE_S + 1),
    )
    monkeypatch.setenv("SUAS_BLUE_LIST_SNAPSHOT", str(path))
    monkeypatch.setenv("SUAS_BLUE_LIST_MAX_AGE_S", str(_MAX_AGE_S))
    from suas.config import get_settings

    get_settings.cache_clear()
    try:
        assessment = _plan_assessment(now=_NOW, requested=AssessmentMode.ADVISORY)
        assert assessment.mode is AssessmentMode.ADVISORY
        assert assessment.decision is not None
        assert assessment.blockers != []
        assert Blocker.BLUE_LIST_SNAPSHOT_STALE in assessment.blockers
    finally:
        get_settings.cache_clear()


def test_the_threshold_comes_from_settings_not_a_literal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A one-hour snapshot is stale only when the configured age is shorter."""
    path = tmp_path / "blue_list_snapshot.json"
    write_snapshot(
        path,
        items=[{"id": "cfg-1", "status": "cleared"}],
        source_url="https://bluelist.dcma.mil/",
        fetched_at=_NOW - timedelta(seconds=3601),
    )
    monkeypatch.setenv("SUAS_BLUE_LIST_SNAPSHOT", str(path))
    from suas.config import get_settings

    monkeypatch.setenv("SUAS_BLUE_LIST_MAX_AGE_S", "3600")
    get_settings.cache_clear()
    try:
        stale = _plan_assessment(now=_NOW, requested=AssessmentMode.OPERATIONAL)
        assert Blocker.BLUE_LIST_SNAPSHOT_STALE in stale.blockers
    finally:
        get_settings.cache_clear()

    monkeypatch.setenv("SUAS_BLUE_LIST_MAX_AGE_S", "7200")
    get_settings.cache_clear()
    try:
        fresh = _plan_assessment(now=_NOW, requested=AssessmentMode.OPERATIONAL)
        assert Blocker.BLUE_LIST_SNAPSHOT_STALE not in fresh.blockers
        assert Blocker.BLUE_LIST_SNAPSHOT_UNAVAILABLE not in fresh.blockers
    finally:
        get_settings.cache_clear()


def test_refresh_script_writes_a_hashed_snapshot_from_a_file(tmp_path: Path) -> None:
    source = tmp_path / "public.json"
    source.write_text(
        json.dumps({"source_url": "https://bluelist.dcma.mil/", "items": [{"id": "a"}]}),
        encoding="utf-8",
    )
    dest = tmp_path / "out.json"
    written = refresh_from_file(source, dest, fetched_at=_NOW)
    loaded = load_snapshot(dest)
    assert loaded is not None
    assert loaded.hash_matches is True
    assert loaded.usable_fetched_at == _NOW
    assert written.content_hash == loaded.content_hash


_AIRCRAFT = Aircraft(
    id="TEST",
    name="Test Bird",
    weight_kg=6.0,
    max_payload_kg=2.7,
    battery_wh=588.0,
    max_wind_mps=12.0,
    cruise_speed_mps=15.0,
    hover_power_w=820.0,
    cruise_power_w=690.0,
    max_temp_c=50.0,
    min_temp_c=-20.0,
)
_PAYLOAD = Payload(id="P", name="Sensor", weight_kg=0.9, power_draw_w=28.0)
_PARAMS = MissionParams(
    distance_m=1000.0,
    hover_time_s=60.0,
    target_altitude_m=120.0,
    elevation_m=0.0,
    latitude=34.0,
    longitude=-80.0,
)
_LIVE = WeatherReading(
    temperature_c=20.0,
    wind_speed_mps=3.0,
    wind_gust_mps=4.0,
    wind_direction=90.0,
    humidity_percent=40.0,
    conditions="calm",
    source=WeatherSource.LIVE,
)


def _plan_assessment(*, now: datetime, requested: AssessmentMode):
    calculations = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_LIVE
    )
    return build_assessment(
        calculations=calculations,
        inputs={"weather": _LIVE.model_dump(mode="json")},
        requested_mode=requested,
        weather=_LIVE,  # keep typo-free
        now=now,
    )


def test_stale_blocker_has_an_operator_facing_reason() -> None:
    from suas.schemas.assessment import blocker_reason

    reason = blocker_reason(Blocker.BLUE_LIST_SNAPSHOT_STALE)
    assert "older than the configured maximum age" in reason
    assert "bluelist.dcma.mil" in reason


def test_unreadable_or_malformed_snapshot_is_unavailable(tmp_path: Path) -> None:
    """A file that cannot be read as a snapshot does not become a date we can age."""
    garbage = tmp_path / "garbage.json"
    garbage.write_text("{not-json", encoding="utf-8")
    assert load_snapshot(garbage) is None

    binary = tmp_path / "binary.json"
    binary.write_bytes(b"\xff\xfe not utf-8")
    assert load_snapshot(binary) is None

    listed = tmp_path / "list.json"
    listed.write_text("[]", encoding="utf-8")
    assert load_snapshot(listed) is None

    bad_items = tmp_path / "items.json"
    bad_items.write_text(
        json.dumps({"fetched_at": _NOW.isoformat(), "content_hash": "sha256:x", "items": {}}),
        encoding="utf-8",
    )
    assert load_snapshot(bad_items) is None


def test_refresh_from_file_rejects_a_source_that_is_not_an_object_with_items(
    tmp_path: Path,
) -> None:
    listed = tmp_path / "list.json"
    listed.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="JSON object"):
        refresh_from_file(listed, tmp_path / "out.json", fetched_at=_NOW)

    missing = tmp_path / "no-items.json"
    missing.write_text(json.dumps({"source_url": "https://example.test"}), encoding="utf-8")
    with pytest.raises(ValueError, match="items list"):
        refresh_from_file(missing, tmp_path / "out.json", fetched_at=_NOW)


def test_refresh_from_file_invents_a_file_source_url_when_the_input_omits_one(
    tmp_path: Path,
) -> None:
    source = tmp_path / "public.json"
    source.write_text(json.dumps({"items": [{"name": "Astro Max"}]}), encoding="utf-8")
    written = refresh_from_file(source, tmp_path / "out.json", fetched_at=_NOW)
    assert written.source_url.startswith("file:")


def test_configured_snapshot_path_falls_back_to_the_data_dir() -> None:
    from suas.blue_list import DEFAULT_SNAPSHOT_PATH, configured_snapshot_path

    assert configured_snapshot_path("") == DEFAULT_SNAPSHOT_PATH
    assert configured_snapshot_path("var/snapshots/custom.json") == Path(
        "var/snapshots/custom.json"
    )
