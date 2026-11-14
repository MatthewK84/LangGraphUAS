"""Ingest of the redacted Astro Max excerpt, in the test database only.

The production seed is not an ingest target. These tests apply the real
excerpt to Freefly_Astro_Max in the test database, then check that
``suas/data/aircraft.json`` on disk is byte-for-byte unchanged.
"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.calculations.from_log import estimate_hover_power, select_hover_samples
from suas.db.flight_logs import MIN_APPLY_SAMPLES, apply_flight_log, store_flight_log
from suas.db.models import AircraftRow
from suas.flight_log_import import parse_flight_log
from suas.schemas.provenance import FieldProvenance, FieldSource

_FIXTURE = Path(__file__).resolve().parent / "fixtures" / "logs" / "astro_max_hover_excerpt.csv"
_SEED = Path(__file__).resolve().parents[1] / "suas" / "data" / "aircraft.json"
_AIRFRAME = "Freefly_Astro_Max"


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


def _seed_hover_w() -> float:
    """Return the hover figure still written in the on-disk seed file."""
    payload = json.loads(_SEED.read_text(encoding="utf-8"))
    return float(payload[_AIRFRAME]["hover_power_w"]["value"])


def _prefix_with_hover_count(content: str, count: int) -> str:
    """Return a leading excerpt whose selected hover samples equal ``count``."""
    lines = content.splitlines()
    kept = [lines[0]]
    for line in lines[1:]:
        kept.append(line)
        text = "\n".join(kept) + "\n"
        hover = select_hover_samples(parse_flight_log(text).samples)
        if len(hover) == count:
            return text
        if len(hover) > count:
            break
    raise AssertionError(f"the excerpt has no prefix with exactly {count} hover samples")


def test_excerpt_has_enough_hover_samples_and_no_payload() -> None:
    parsed = parse_flight_log(_FIXTURE.read_text(encoding="utf-8"))
    hover = select_hover_samples(parsed.samples)
    estimate = estimate_hover_power(parsed.samples)
    assert len(hover) >= MIN_APPLY_SAMPLES
    assert estimate is not None
    assert estimate.sample_count == len(hover)
    assert all(sample.payload_id in {None, ""} for sample in parsed.samples)
    # Identifiers and pack serials must not have been copied into the fixture.
    text = _FIXTURE.read_text(encoding="utf-8")
    assert "sys_uuid" not in text
    assert "serial" not in text.lower()


async def test_applying_the_excerpt_changes_hover_power_in_the_test_database(
    app_with_graph: FastAPI,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    content = _FIXTURE.read_text(encoding="utf-8")
    estimate = estimate_hover_power(parse_flight_log(content).samples)
    assert estimate is not None
    seed_hover = _seed_hover_w()
    seed_before = _SEED.read_bytes()

    async with _client(app_with_graph) as client:
        response = await client.post(
            f"/api/logs?airframe_id={_AIRFRAME}&apply=true",
            content=content.encode("utf-8"),
            headers={"Content-Type": "text/csv"},
        )

    assert response.status_code == 200
    body = response.json()
    assert "hover_power_w" in body["applied_fields"]
    assert body["hover"]["sample_count"] >= MIN_APPLY_SAMPLES

    async with session_factory() as session:
        aircraft = await session.get(AircraftRow, _AIRFRAME)
        assert aircraft is not None
        record = FieldProvenance.model_validate(aircraft.provenance["hover_power_w"])

    assert record.source is FieldSource.FLIGHT_LOG
    assert aircraft.hover_power_w == pytest.approx(estimate.median_w)
    assert aircraft.hover_power_w != pytest.approx(seed_hover)
    assert _SEED.read_bytes() == seed_before
    assert _seed_hover_w() == pytest.approx(seed_hover)


async def test_fewer_than_thirty_hover_samples_are_stored_but_not_applied(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    content = _prefix_with_hover_count(_FIXTURE.read_text(encoding="utf-8"), MIN_APPLY_SAMPLES - 1)
    seed_before = _SEED.read_bytes()
    seed_hover = _seed_hover_w()

    async with session_factory() as session:
        row = await store_flight_log(session, airframe_id=_AIRFRAME, content=content)
        applied = await apply_flight_log(session, row.log_id)
        aircraft = await session.get(AircraftRow, _AIRFRAME)

    assert row.hover_samples == MIN_APPLY_SAMPLES - 1
    assert applied == []
    assert aircraft is not None
    assert aircraft.hover_power_w == pytest.approx(seed_hover)
    assert FieldProvenance.model_validate(aircraft.provenance["hover_power_w"]).source is not (
        FieldSource.FLIGHT_LOG
    )
    assert _SEED.read_bytes() == seed_before
