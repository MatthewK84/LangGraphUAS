"""Property tests for the safety calculators.

Example tests pin one mission. These pin the direction of every input the
calculator takes: worse conditions may turn GO into NO_GO, never the other way
round. Each property was first run against a deliberately broken calculator and
watched fail, so each one is known to catch the error it names.

Examples are capped by the ``ci`` Hypothesis profile in ``conftest.py``.
"""

from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from suas.calculations.assessment import (
    _build_safety_flags,
    _decide,
    assess_mission,
    compute_inputs_hash,
    is_mission_viable,
)
from suas.calculations.battery import calculate_temperature_capacity_factor
from suas.calculations.gate import (
    REQUIRED_PROVENANCE_AIRCRAFT,
    REQUIRED_PROVENANCE_PAYLOAD,
    provenance_is_complete,
    resolve_mode,
)
from suas.schemas.assessment import AssessmentMode, Blocker, Decision
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.provenance import FieldProvenance, FieldSource
from suas.schemas.requests import MissionParams
from suas.schemas.responses import Calculations, SafetyFlags, WeatherReading

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
_PARAMS = MissionParams(
    distance_m=1000.0,
    hover_time_s=60.0,
    target_altitude_m=120.0,
    elevation_m=0.0,
    latitude=34.0,
    longitude=-80.0,
)
_FLAG_NAMES = list(SafetyFlags.model_fields)

_wind = st.floats(min_value=0.0, max_value=20.0, allow_nan=False)
_payload_kg = st.floats(min_value=0.0, max_value=4.0, allow_nan=False)
_battery_wh = st.floats(min_value=50.0, max_value=2000.0, allow_nan=False)
_temperature = st.floats(min_value=-40.0, max_value=60.0, allow_nan=False)
_distance_m = st.floats(min_value=100.0, max_value=20000.0, allow_nan=False)


def _weather(wind: float, gust: float, temperature_c: float = 20.0) -> WeatherReading:
    return WeatherReading(
        temperature_c=temperature_c,
        wind_speed_mps=wind,
        wind_gust_mps=gust,
        wind_direction=90.0,
        humidity_percent=40.0,
        conditions="generated",
    )


def _decision(
    *,
    wind: float = 3.0,
    gust: float = 4.0,
    payload_kg: float = 0.9,
    battery_wh: float = 588.0,
    distance_m: float = 1000.0,
) -> Decision:
    aircraft = _AIRCRAFT.model_copy(update={"battery_wh": battery_wh})
    payload = Payload(id="P", name="Sensor", weight_kg=payload_kg, power_draw_w=28.0)
    params = _PARAMS.model_copy(update={"distance_m": distance_m})
    calculations = assess_mission(
        aircraft=aircraft, payload=payload, params=params, weather=_weather(wind, gust)
    )
    decision, _reasons = _decide(calculations)
    return decision


def _ordered(low: float, high: float) -> tuple[float, float]:
    return (low, high) if low <= high else (high, low)


@given(st.dictionaries(st.text(max_size=8), st.integers() | st.text(max_size=8), max_size=12))
def test_inputs_hash_ignores_key_order(inputs: dict[str, Any]) -> None:
    reversed_inputs = dict(reversed(list(inputs.items())))
    assert compute_inputs_hash(reversed_inputs) == compute_inputs_hash(inputs)


@given(_wind, _wind)
def test_more_wind_never_turns_no_go_into_go(a: float, b: float) -> None:
    calm, windy = _ordered(a, b)
    if _decision(wind=calm, gust=0.0) is Decision.NO_GO:
        assert _decision(wind=windy, gust=0.0) is Decision.NO_GO


@given(_wind, _wind)
def test_stronger_gust_never_turns_no_go_into_go(a: float, b: float) -> None:
    low, high = _ordered(a, b)
    if _decision(wind=0.0, gust=low) is Decision.NO_GO:
        assert _decision(wind=0.0, gust=high) is Decision.NO_GO


@given(_payload_kg, _payload_kg)
def test_heavier_payload_never_turns_no_go_into_go(a: float, b: float) -> None:
    light, heavy = _ordered(a, b)
    if _decision(payload_kg=light) is Decision.NO_GO:
        assert _decision(payload_kg=heavy) is Decision.NO_GO


@given(_battery_wh, _battery_wh, _distance_m)
def test_smaller_battery_never_turns_no_go_into_go(a: float, b: float, distance: float) -> None:
    small, large = _ordered(a, b)
    if _decision(battery_wh=large, distance_m=distance) is Decision.NO_GO:
        assert _decision(battery_wh=small, distance_m=distance) is Decision.NO_GO


@given(st.sampled_from(_FLAG_NAMES))
def test_any_failed_flag_is_no_go(failed: str) -> None:
    good = assess_mission(
        aircraft=_AIRCRAFT,
        payload=Payload(id="P", name="Sensor", weight_kg=0.9, power_draw_w=28.0),
        params=_PARAMS,
        weather=_weather(3.0, 4.0),
    )
    flags = SafetyFlags(**{name: name != failed for name in _FLAG_NAMES})
    calculations: Calculations = good.model_copy(update={"safety_flags": flags})
    decision, reasons = _decide(calculations)
    assert decision is Decision.NO_GO
    assert len(reasons) == 1
    assert is_mission_viable(calculations) is False


def test_all_flags_passing_is_go() -> None:
    good = assess_mission(
        aircraft=_AIRCRAFT,
        payload=Payload(id="P", name="Sensor", weight_kg=0.9, power_draw_w=28.0),
        params=_PARAMS,
        weather=_weather(3.0, 4.0),
    )
    assert _decide(good) == (Decision.GO, [])
    assert is_mission_viable(good) is True


@given(st.floats(min_value=0.0, max_value=30.0, allow_nan=False), _temperature)
def test_limits_are_inclusive(limit: float, temperature_c: float) -> None:
    """A reading exactly at a published limit is within it; one past it is not."""
    aircraft = _AIRCRAFT.model_copy(
        update={
            "max_wind_mps": limit,
            "max_temp_c": max(temperature_c, -20.0),
            "min_temp_c": min(temperature_c, -20.0),
            "pack_min_takeoff_c": temperature_c,
        }
    )
    at_limit = _build_safety_flags(
        battery_viable=True,
        payload_margin_kg=0.0,
        ground_speed_mps=1.0,
        weather=_weather(limit, limit, temperature_c),
        aircraft=aircraft,
    )
    assert at_limit.payload_within_limits
    assert at_limit.wind_within_limits
    assert at_limit.gust_within_limits
    assert at_limit.temperature_within_limits
    assert at_limit.pack_temp_within_takeoff_limits

    past_limit = _build_safety_flags(
        battery_viable=True,
        payload_margin_kg=-0.001,
        ground_speed_mps=0.0,
        weather=_weather(limit + 0.01, limit + 0.01, temperature_c - 0.01),
        aircraft=aircraft.model_copy(update={"min_temp_c": temperature_c}),
    )
    assert not past_limit.payload_within_limits
    assert not past_limit.wind_within_limits
    assert not past_limit.gust_within_limits
    assert not past_limit.temperature_within_limits
    assert not past_limit.pack_temp_within_takeoff_limits
    assert not past_limit.cruise_achievable


@given(_temperature, _temperature)
def test_capacity_factor_is_bounded_and_monotone(a: float, b: float) -> None:
    cold, warm = _ordered(a, b)
    cold_factor = calculate_temperature_capacity_factor(cold)
    warm_factor = calculate_temperature_capacity_factor(warm)
    assert 0.65 <= cold_factor <= warm_factor <= 1.0


@given(st.sampled_from(list(AssessmentMode)), st.lists(st.sampled_from(list(Blocker))))
def test_mode_never_exceeds_request(requested: AssessmentMode, blockers: list[Blocker]) -> None:
    granted = resolve_mode(requested, blockers)
    if blockers or requested is AssessmentMode.ADVISORY:
        assert granted is AssessmentMode.ADVISORY
    else:
        assert granted is AssessmentMode.OPERATIONAL


def _records(names: frozenset[str] | set[str]) -> dict[str, FieldProvenance]:
    return {
        name: FieldProvenance(value=1.0, unit="u", source=FieldSource.DATASHEET) for name in names
    }


@given(
    st.sets(st.sampled_from(sorted(REQUIRED_PROVENANCE_AIRCRAFT))),
    st.sets(st.sampled_from(sorted(REQUIRED_PROVENANCE_PAYLOAD))),
)
def test_provenance_needs_both_sides_complete(aircraft: set[str], payload: set[str]) -> None:
    expected = aircraft == REQUIRED_PROVENANCE_AIRCRAFT and payload == REQUIRED_PROVENANCE_PAYLOAD
    assert provenance_is_complete(_records(aircraft), _records(payload)) is expected
