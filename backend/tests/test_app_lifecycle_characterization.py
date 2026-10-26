"""Characterization tests for ``apply_flight_log`` and the app ``lifespan``.

``apply_flight_log`` is the only way a measured figure becomes a number plans
are built on, so these pin exactly which fields it writes, what provenance it
records, and when it writes nothing. ``lifespan`` and ``_purge_checkpoints``
are pinned on the state they leave on the app and what they log. Every test
asserts on returned values, stored rows or app state, so code that returned or
did nothing would fail it.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.config import Settings, get_settings
from suas.db.flight_logs import MIN_APPLY_SAMPLES, apply_flight_log
from suas.db.models import AircraftRow, FlightLogRow
from suas.db.retention import record_thread
from suas.errors import FlightLogError
from suas.main import _purge_checkpoints, lifespan

_AIRFRAME = "Skydio_X10D"


# --- apply_flight_log ---------------------------------------------------------


async def _store_log(
    session_factory: async_sessionmaker[AsyncSession], log_id: str, **estimates: Any
) -> None:
    fields: dict[str, Any] = {
        "hover_median_w": None,
        "hover_samples": None,
        "hover_confidence": None,
        "cruise_median_w": None,
        "cruise_samples": None,
        "cruise_confidence": None,
        "airframe_id": _AIRFRAME,
    }
    fields.update(estimates)
    async with session_factory() as session:
        session.add(
            FlightLogRow(
                log_id=log_id,
                uploaded_at=datetime.now(UTC),
                sha256=f"sha-{log_id}",
                raw_csv="timestamp,alt_m,power_w\n",
                row_count=0,
                rejected_rows=0,
                applied=False,
                **fields,
            )
        )
        await session.commit()


async def _airframe(session_factory: async_sessionmaker[AsyncSession]) -> AircraftRow:
    async with session_factory() as session:
        aircraft = await session.get(AircraftRow, _AIRFRAME)
    assert aircraft is not None
    return aircraft


async def _log(session_factory: async_sessionmaker[AsyncSession], log_id: str) -> FlightLogRow:
    async with session_factory() as session:
        row = await session.get(FlightLogRow, log_id)
    assert row is not None
    return row


async def test_an_unknown_log_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(FlightLogError, match=r"^Unknown flight log: nope$"):
            await apply_flight_log(session, "nope")


async def test_a_log_for_an_unknown_airframe_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store_log(session_factory, "orphan", airframe_id="No_Such_Airframe")
    async with session_factory() as session:
        with pytest.raises(FlightLogError, match=r"^Unknown airframe: No_Such_Airframe$"):
            await apply_flight_log(session, "orphan")


async def test_both_estimates_at_the_bar_are_applied_with_provenance(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    before = await _airframe(session_factory)
    untouched = {
        k: v for k, v in before.provenance.items() if k not in {"hover_power_w", "cruise_power_w"}
    }
    await _store_log(
        session_factory,
        "both",
        hover_median_w=812.5,
        hover_samples=MIN_APPLY_SAMPLES,
        hover_confidence="high",
        cruise_median_w=640.0,
        cruise_samples=MIN_APPLY_SAMPLES + 5,
        cruise_confidence="medium",
    )

    with caplog.at_level(logging.INFO, logger="suas.db.flight_logs"):
        async with session_factory() as session:
            applied = await apply_flight_log(session, "both")

    assert applied == ["hover_power_w", "cruise_power_w"]
    after = await _airframe(session_factory)
    assert after.hover_power_w == 812.5
    assert after.cruise_power_w == 640.0
    hover = after.provenance["hover_power_w"]
    assert hover["value"] == 812.5
    assert hover["unit"] == "W"
    assert hover["source"] == "flight_log"
    assert hover["source_url"] is None
    assert hover["retrieved_at"] == date.today().isoformat()
    assert hover["confidence"] == "high"
    assert hover["notes"] == (
        f"Median of {MIN_APPLY_SAMPLES} selected samples from log both. Interquartile range 0.0 W."
    )
    assert after.provenance["cruise_power_w"]["confidence"] == "medium"
    assert after.provenance["cruise_power_w"]["value"] == 640.0
    assert (
        f"{MIN_APPLY_SAMPLES + 5} selected samples from log both"
        in (after.provenance["cruise_power_w"]["notes"])
    )
    assert {k: v for k, v in after.provenance.items() if k in untouched} == untouched
    assert (await _log(session_factory, "both")).applied is True
    assert (
        f"Applied flight log both to {_AIRFRAME}: ['hover_power_w', 'cruise_power_w']"
        in caplog.text
    )


async def test_only_the_estimate_that_clears_the_bar_is_applied(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    before = await _airframe(session_factory)
    await _store_log(
        session_factory,
        "hover-only",
        hover_median_w=900.0,
        hover_samples=MIN_APPLY_SAMPLES,
        hover_confidence="high",
        cruise_median_w=700.0,
        cruise_samples=MIN_APPLY_SAMPLES - 1,
        cruise_confidence="high",
    )
    async with session_factory() as session:
        applied = await apply_flight_log(session, "hover-only")

    assert applied == ["hover_power_w"]
    after = await _airframe(session_factory)
    assert after.hover_power_w == 900.0
    assert after.cruise_power_w == before.cruise_power_w
    assert after.provenance["cruise_power_w"] == before.provenance["cruise_power_w"]


async def test_a_missing_confidence_is_recorded_as_low(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store_log(
        session_factory,
        "no-confidence",
        cruise_median_w=700.0,
        cruise_samples=MIN_APPLY_SAMPLES,
        cruise_confidence=None,
    )
    async with session_factory() as session:
        applied = await apply_flight_log(session, "no-confidence")

    assert applied == ["cruise_power_w"]
    after = await _airframe(session_factory)
    assert after.provenance["cruise_power_w"]["confidence"] == "low"


@pytest.mark.parametrize(
    "estimates",
    [
        {"hover_median_w": None, "hover_samples": MIN_APPLY_SAMPLES},
        {"hover_median_w": 900.0, "hover_samples": None},
        {"hover_median_w": 900.0, "hover_samples": MIN_APPLY_SAMPLES - 1},
    ],
    ids=["no-median", "no-samples", "below-bar"],
)
async def test_an_unusable_estimate_changes_nothing(
    session_factory: async_sessionmaker[AsyncSession], estimates: dict[str, Any]
) -> None:
    before = await _airframe(session_factory)
    await _store_log(session_factory, "unusable", hover_confidence="high", **estimates)
    async with session_factory() as session:
        applied = await apply_flight_log(session, "unusable")

    assert applied == []
    after = await _airframe(session_factory)
    assert after.hover_power_w == before.hover_power_w
    assert after.provenance == before.provenance
    assert (await _log(session_factory, "unusable")).applied is False


# --- _purge_checkpoints -------------------------------------------------------


class _ExplodingSessionFactory:
    def __call__(self) -> Any:
        raise RuntimeError("database is down")


async def test_a_failed_retention_pass_is_logged_and_swallowed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(checkpoint_retention_days=30.0)
    with caplog.at_level(logging.ERROR, logger="suas.main"):
        result = await _purge_checkpoints(
            _ExplodingSessionFactory(),  # type: ignore[arg-type]
            InMemorySaver(),
            settings,
        )

    assert result is None
    assert "Checkpoint retention pass failed: database is down" in caplog.text


async def test_a_retention_pass_that_purges_logs_the_count(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with session_factory() as session:
        await record_thread(session, "old-thread")
    # Zero-day retention is disabled, so use the smallest positive window and
    # let the thread's creation time fall before it.
    settings = Settings(checkpoint_retention_days=1e-9)
    with caplog.at_level(logging.INFO, logger="suas.main"):
        await _purge_checkpoints(session_factory, InMemorySaver(), settings)

    assert "Retention purged 1 expired threads" in caplog.text


async def test_a_retention_pass_that_purges_nothing_logs_nothing(
    session_factory: async_sessionmaker[AsyncSession],
    caplog: pytest.LogCaptureFixture,
) -> None:
    settings = Settings(checkpoint_retention_days=30.0)
    with caplog.at_level(logging.INFO, logger="suas.main"):
        await _purge_checkpoints(session_factory, InMemorySaver(), settings)

    assert "Retention purged" not in caplog.text
    assert "Checkpoint retention pass failed" not in caplog.text


# --- lifespan -----------------------------------------------------------------


class _Records(logging.Handler):
    """Collects records from one logger.

    ``lifespan`` reconfigures the root logger, which removes pytest's capture
    handler, so records are collected on the module's own logger instead.
    """

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


@pytest.fixture
def sqlite_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[_Records]:
    monkeypatch.setenv("SUAS_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'life.db'}")
    monkeypatch.setenv("SUAS_API_KEY", "")
    monkeypatch.setenv("SUAS_LOG_LEVEL", "INFO")
    root = logging.getLogger()
    saved_handlers, saved_level = list(root.handlers), root.level
    records = _Records()
    module_logger = logging.getLogger("suas.main")
    module_logger.addHandler(records)
    get_settings.cache_clear()
    yield records
    get_settings.cache_clear()
    module_logger.removeHandler(records)
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


async def test_startup_wires_the_app_and_shutdown_releases_it(
    sqlite_settings: _Records,
) -> None:
    app = FastAPI()
    async with lifespan(app):
        assert isinstance(app.state.graph, CompiledStateGraph)
        assert isinstance(app.state.replan_graph, CompiledStateGraph)
        factory = app.state.session_factory
        async with factory() as session:
            assert await session.get(AircraftRow, _AIRFRAME) is not None
        engine = factory.kw["bind"]
    assert engine.pool.checkedout() == 0

    messages = "\n".join(sqlite_settings.messages)
    assert "API authentication is disabled; set SUAS_API_KEY in production" in messages
    assert "Not using PostgreSQL. If this is a deployment, SUAS_DATABASE_URL is unset" in messages
    assert "Database: " in messages


async def test_an_api_key_silences_the_auth_warning(
    sqlite_settings: _Records, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SUAS_API_KEY", "k" * 32)
    get_settings.cache_clear()
    app = FastAPI()
    async with lifespan(app):
        assert isinstance(app.state.graph, CompiledStateGraph)

    messages = "\n".join(sqlite_settings.messages)
    assert "API authentication is disabled" not in messages
    assert "Not using PostgreSQL" in messages
