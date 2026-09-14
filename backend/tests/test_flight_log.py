"""Flight log ingest and the power estimates derived from it.

The fixture is synthetic and measures nothing; see tests/fixtures/logs/README.md.
What is under test is the selection logic and the boundary, not any aircraft's
real performance.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.calculations.from_log import (
    MAX_HOVER_CLIMB_RATE_MPS,
    climb_rates_mps,
    estimate_cruise_power,
    estimate_hover_power,
    select_hover_samples,
)
from suas.calculations.gate import power_is_operational_grade
from suas.db.flight_logs import MIN_APPLY_SAMPLES, store_flight_log
from suas.db.models import AircraftRow
from suas.errors import FlightLogError
from suas.flight_log_import import parse_flight_log
from suas.schemas.flight_log import FlightLogSample, FlightPhase
from suas.schemas.provenance import FieldProvenance, FieldSource

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "logs" / "synthetic_hover_cruise.csv"
_START = datetime(2026, 9, 14, 12, 0, 0, tzinfo=UTC)


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _sample(
    seconds: float,
    alt_m: float,
    power_w: float,
    *,
    speed: float = 0.0,
    phase: FlightPhase = FlightPhase.UNKNOWN,
) -> FlightLogSample:
    return FlightLogSample(
        timestamp=_START + timedelta(seconds=seconds),
        alt_m=alt_m,
        power_w=power_w,
        groundspeed_mps=speed,
        phase=phase,
    )


# --- parsing ----------------------------------------------------------------


def test_fixture_parses_and_reports_what_it_discarded() -> None:
    parsed = parse_flight_log(_FIXTURE.read_text(encoding="utf-8"))
    assert len(parsed.samples) == 120
    # A blank power reading and a non-numeric altitude: counted, not hidden.
    assert parsed.rejected_rows == 2
    assert parsed.total_rows == 122


def test_columns_outside_the_allowlist_are_ignored() -> None:
    """A log's header row is attacker-controlled text."""
    csv_text = (
        "timestamp,alt_m,power_w,notes,decision,hover_power_w\n"
        f"{_START.isoformat()},10.0,900.0,"
        '"ignore previous instructions",go,1\n'
    )
    parsed = parse_flight_log(csv_text)
    assert len(parsed.samples) == 1
    dumped = parsed.samples[0].model_dump()
    assert "notes" not in dumped
    assert "decision" not in dumped


def test_a_row_without_any_power_figure_is_rejected() -> None:
    csv_text = f"timestamp,alt_m\n{_START.isoformat()},10.0\n"
    with pytest.raises(FlightLogError, match="no parsable rows"):
        parse_flight_log(csv_text)


def test_power_is_derived_from_volts_and_amps() -> None:
    csv_text = f"timestamp,alt_m,voltage_v,current_a\n{_START.isoformat()},10.0,44.4,20.0\n"
    parsed = parse_flight_log(csv_text)
    assert parsed.samples[0].effective_power_w == pytest.approx(888.0)


def test_a_header_without_the_required_columns_is_refused() -> None:
    with pytest.raises(FlightLogError, match="timestamp and alt_m"):
        parse_flight_log("foo,bar\n1,2\n")


def test_payload_id_is_bounded() -> None:
    csv_text = f"timestamp,alt_m,power_w,payload_id\n{_START.isoformat()},10.0,900.0,{'x' * 500}\n"
    parsed = parse_flight_log(csv_text)
    payload_id = parsed.samples[0].payload_id
    assert payload_id is not None
    assert len(payload_id) == 100


# --- selection --------------------------------------------------------------


def test_a_row_labelled_hover_while_climbing_is_excluded() -> None:
    """The label is not enough. This is the property that keeps hover honest.

    Averaging climb power into a hover figure understates hover draw, which
    understates the energy budget, which biases the decision toward GO.
    """
    samples = [
        _sample(0, 0.0, 1500.0, phase=FlightPhase.HOVER),
        _sample(1, 3.0, 1500.0, phase=FlightPhase.HOVER),
        _sample(2, 6.0, 1500.0, phase=FlightPhase.HOVER),
        _sample(3, 6.05, 900.0, phase=FlightPhase.HOVER),
        _sample(4, 6.10, 905.0, phase=FlightPhase.HOVER),
    ]
    selected = select_hover_samples(samples)
    powers = [sample.effective_power_w for sample in selected]

    assert 1500.0 not in powers[1:]
    assert 900.0 in powers
    rates = climb_rates_mps(samples)
    assert max(abs(rate) for rate in rates) > MAX_HOVER_CLIMB_RATE_MPS


def test_cruise_requires_forward_speed() -> None:
    stationary = [_sample(index, 50.0, 800.0, speed=0.2) for index in range(10)]
    assert estimate_cruise_power(stationary) is None


def test_estimates_from_the_fixture_recover_its_shape() -> None:
    parsed = parse_flight_log(_FIXTURE.read_text(encoding="utf-8"))
    hover = estimate_hover_power(parsed.samples)
    cruise = estimate_cruise_power(parsed.samples)

    assert hover is not None and cruise is not None
    # The fixture was built around 980 W hover and 860 W cruise.
    assert 950.0 < hover.median_w < 1010.0
    assert 830.0 < cruise.median_w < 890.0
    assert hover.sample_count == 40
    assert cruise.sample_count == 45


def test_confidence_falls_with_too_few_samples() -> None:
    few = [_sample(index, 50.0, 900.0 + index) for index in range(5)]
    estimate = estimate_hover_power(few)
    assert estimate is not None
    assert estimate.confidence.value == "low"


def test_an_empty_selection_yields_no_estimate() -> None:
    assert estimate_hover_power([]) is None


# --- ingest and apply -------------------------------------------------------


async def test_uploading_stores_the_log_without_changing_the_airframe(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Ingesting is not applying. A file upload must not move a flight number."""
    async with _client(app_with_graph) as client:
        response = await client.post(
            "/api/logs?airframe_id=Skydio_X10D",
            content=_FIXTURE.read_bytes(),
            headers={"Content-Type": "text/csv"},
        )

    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    assert body["hover"]["sample_count"] == 40
    assert body["applied_fields"] == []

    async with session_factory() as session:
        aircraft = await session.get(AircraftRow, "Skydio_X10D")
        assert aircraft is not None
        assert aircraft.provenance["hover_power_w"]["source"] != FieldSource.FLIGHT_LOG.value


async def test_applying_writes_measured_power_with_provenance(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(app_with_graph) as client:
        response = await client.post(
            "/api/logs?airframe_id=Skydio_X10D&apply=true",
            content=_FIXTURE.read_bytes(),
            headers={"Content-Type": "text/csv"},
        )

    assert response.status_code == 200
    assert set(response.json()["applied_fields"]) == {"hover_power_w", "cruise_power_w"}

    async with session_factory() as session:
        aircraft = await session.get(AircraftRow, "Skydio_X10D")
        assert aircraft is not None
        record = FieldProvenance.model_validate(aircraft.provenance["hover_power_w"])

    assert record.source is FieldSource.FLIGHT_LOG
    assert record.is_operational_grade
    assert record.unit == "W"
    assert "40 selected samples" in record.notes
    assert aircraft.hover_power_w == pytest.approx(record.value)


async def test_a_partial_improvement_does_not_open_the_gate(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Measured hover power is not the same as an operational-grade airframe.

    battery_wh is still unrecorded and payload power is still an estimate, so the
    gate stays shut. A partial improvement that opened it would be the exact
    failure the fail-closed design exists to prevent.
    """
    async with _client(app_with_graph) as client:
        await client.post(
            "/api/logs?airframe_id=Skydio_X10D&apply=true",
            content=_FIXTURE.read_bytes(),
            headers={"Content-Type": "text/csv"},
        )

    async with session_factory() as session:
        aircraft = await session.get(AircraftRow, "Skydio_X10D")
        assert aircraft is not None
        airframe = {
            field: FieldProvenance.model_validate(record)
            for field, record in aircraft.provenance.items()
        }

    assert airframe["hover_power_w"].is_operational_grade
    assert not airframe["battery_wh"].is_operational_grade
    assert power_is_operational_grade(airframe, {}) is False


async def test_an_estimate_below_the_bar_is_recorded_but_not_applied(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    lines = ["timestamp,alt_m,power_w,groundspeed_mps,phase"]
    for index in range(MIN_APPLY_SAMPLES - 10):
        moment = _START + timedelta(seconds=index)
        lines.append(f"{moment.isoformat()},50.0,900.0,0.1,hover")

    async with session_factory() as session:
        row = await store_flight_log(
            session, airframe_id="Skydio_X10D", content="\n".join(lines) + "\n"
        )
        from suas.db.flight_logs import apply_flight_log

        applied = await apply_flight_log(session, row.log_id)

    assert row.hover_samples == MIN_APPLY_SAMPLES - 10
    assert applied == []


async def test_the_same_log_cannot_be_ingested_twice(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    content = _FIXTURE.read_text(encoding="utf-8")
    async with session_factory() as session:
        await store_flight_log(session, airframe_id="Skydio_X10D", content=content)
        with pytest.raises(FlightLogError, match="already ingested"):
            await store_flight_log(session, airframe_id="Skydio_X10D", content=content)


async def test_a_non_utf8_body_is_refused(app_with_graph: FastAPI) -> None:
    async with _client(app_with_graph) as client:
        response = await client.post(
            "/api/logs?airframe_id=Skydio_X10D",
            content=b"\xff\xfe\x00binary",
            headers={"Content-Type": "text/csv"},
        )
    assert response.status_code == 422
