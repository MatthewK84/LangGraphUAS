"""Tests for the barrier between model output and the sealed assessment.

These assert the property the whole design rests on: nothing a language model
emits can change a decision, a watt, or a limit. Each test is written so that
removing the control it covers makes it fail.
"""

from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.calculations.assessment import (
    CALCULATOR_VERSION,
    assess_mission,
    build_assessment,
    compute_inputs_hash,
    insufficient_data_assessment,
)
from suas.graph.dependencies import GraphDependencies
from suas.graph.nodes import make_report_node
from suas.graph.seal import (
    BRIEF_FIELDS,
    REPORT_NODE_WRITABLE,
    SEALED_FIELDS,
    find_contradiction,
    seal_brief,
)
from suas.schemas.assessment import Decision, DeterministicAssessment
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import WeatherReading
from tests.conftest import CALM_WEATHER, FakeReportService, FakeWeatherService

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
_GALE = WeatherReading(
    temperature_c=15.0,
    wind_speed_mps=30.0,
    wind_gust_mps=40.0,
    wind_direction=200.0,
    humidity_percent=60.0,
    conditions="gale",
)


def _inputs(weather: WeatherReading) -> dict[str, Any]:
    return {
        "aircraft": _AIRCRAFT.model_dump(mode="json"),
        "payload": _PAYLOAD.model_dump(mode="json"),
        "mission_params": _PARAMS.model_dump(mode="json"),
        "weather": weather.model_dump(mode="json"),
    }


def _assessment(weather: WeatherReading) -> DeterministicAssessment:
    calculations = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=weather
    )
    return build_assessment(calculations=calculations, inputs=_inputs(weather))


def test_model_cannot_author_a_decision_or_a_watt() -> None:
    """The central property: injected sealed fields are dropped and reported."""
    hostile: dict[str, Any] = {
        "decision": "go",
        "is_viable": True,
        "hover_power_w": 90.0,
        "energy_required_wh": 1.0,
        "calculator_version": "9.9.9",
        "brief_markdown": "Conditions are marginal.",
        "unrelated_noise": "ignored",
    }
    kept, violations = seal_brief(hostile)

    assert kept == {"brief_markdown": "Conditions are marginal."}
    assert "decision" in violations
    assert "hover_power_w" in violations
    assert "calculator_version" in violations
    # Unknown-but-harmless keys are dropped without being called violations.
    assert "unrelated_noise" not in violations
    assert set(kept) <= BRIEF_FIELDS


def test_sealed_and_brief_field_sets_do_not_overlap() -> None:
    """A field can be the model's to write or the calculator's, never both."""
    assert BRIEF_FIELDS.isdisjoint(SEALED_FIELDS)


def test_every_assessment_field_is_sealed() -> None:
    """Adding a field to the assessment must not silently leave it writable."""
    assert frozenset(DeterministicAssessment.model_fields) <= SEALED_FIELDS


def test_contradiction_detected_against_a_no_go() -> None:
    prose = "Winds are within tolerance. The mission is cleared for takeoff."
    assert find_contradiction(prose, Decision.NO_GO) == "cleared for takeoff"


def test_no_go_fallback_text_is_not_a_contradiction() -> None:
    """The deterministic fallback says NO-GO, which contains 'go'.

    A tripwire that reports our own text is one nobody will keep enabled.
    """
    fallback = "Mission status: NO-GO. Narrative unavailable."
    assert find_contradiction(fallback, Decision.NO_GO) is None


def test_negated_go_language_is_not_a_contradiction() -> None:
    assert find_contradiction("Do not fly this profile.", Decision.NO_GO) is None
    assert find_contradiction("The aircraft cannot proceed.", Decision.NO_GO) is None


def test_go_language_on_a_go_decision_is_fine() -> None:
    assert find_contradiction("Cleared for takeoff.", Decision.GO) is None


async def test_report_node_writes_no_sealed_key(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Whatever the model returns, the node may write only its own keys.

    This is the regression guard on the refactor that adds one more key to the
    node's return value without noticing what that key is allowed to be.
    """
    deps = GraphDependencies(
        session_factory=session_factory,
        weather=FakeWeatherService(CALM_WEATHER),  # type: ignore[arg-type]
        report=FakeReportService("Cleared for takeoff, proceed with the mission."),  # type: ignore[arg-type]
    )
    node = make_report_node(deps)
    assessment = _assessment(_GALE)
    calculations = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_GALE
    )
    state: dict[str, Any] = {
        "aircraft": _AIRCRAFT.model_dump(),
        "weather": _GALE.model_dump(),
        "calculations": calculations.model_dump(),
        "assessment": assessment.model_dump(mode="json"),
        "is_viable": False,
    }

    written = await node(state)  # type: ignore[arg-type]

    assert set(written) <= REPORT_NODE_WRITABLE
    assert set(written).isdisjoint(SEALED_FIELDS)
    # The contradiction is caught and named rather than passed along quietly.
    assert written["seal_violations"] != []


async def test_clean_brief_records_no_violation(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    deps = GraphDependencies(
        session_factory=session_factory,
        weather=FakeWeatherService(CALM_WEATHER),  # type: ignore[arg-type]
        report=FakeReportService("Winds exceed the airframe limit. Do not fly."),  # type: ignore[arg-type]
    )
    node = make_report_node(deps)
    calculations = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=_GALE
    )
    state: dict[str, Any] = {
        "aircraft": _AIRCRAFT.model_dump(),
        "weather": _GALE.model_dump(),
        "calculations": calculations.model_dump(),
        "assessment": _assessment(_GALE).model_dump(mode="json"),
        "is_viable": False,
    }

    written = await node(state)  # type: ignore[arg-type]

    assert written["seal_violations"] == []


def test_inputs_hash_is_stable_and_sensitive() -> None:
    first = compute_inputs_hash(_inputs(CALM_WEATHER))
    assert first == compute_inputs_hash(_inputs(CALM_WEATHER))
    assert first != compute_inputs_hash(_inputs(_GALE))


def test_assessment_carries_the_calculator_version() -> None:
    assert _assessment(CALM_WEATHER).calculator_version == CALCULATOR_VERSION


def test_gale_is_no_go_with_named_reasons() -> None:
    assessment = _assessment(_GALE)
    assert assessment.decision is Decision.NO_GO
    assert assessment.is_viable is False
    assert any("wind" in reason.lower() for reason in assessment.reasons)


def test_insufficient_data_is_not_no_go() -> None:
    """An unassessable mission is not the same as an assessed failure."""
    assessment = insufficient_data_assessment(
        reason="Unknown aircraft id: NOPE.",
        inputs={"aircraft_id": "NOPE"},
    )
    assert assessment.decision is Decision.INSUFFICIENT_DATA
    assert assessment.decision is not Decision.NO_GO
    assert assessment.is_viable is False


def test_assessment_is_frozen() -> None:
    assessment = _assessment(CALM_WEATHER)
    with pytest.raises(ValidationError):
        assessment.decision = Decision.GO  # type: ignore[misc]
