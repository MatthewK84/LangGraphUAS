"""The numeric trace: prose may restate numbers, never invent them.

Step 5 of the output pipeline in docs/backlog/13-brief-output-allowlist.md. The
seal stops the model writing a sealed *field*; this stops it writing a number
into the *prose*, which is the only channel it has left.
"""

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.api.observability import MetricsRegistry
from suas.calculations.assessment import assess_mission, build_assessment
from suas.graph.dependencies import GraphDependencies
from suas.graph.nodes import make_report_node
from suas.graph.seal import REPORT_NODE_WRITABLE, unsupported_numerics
from tests.conftest import CALM_WEATHER, FakeReportService, FakeWeatherService
from tests.test_seal import _AIRCRAFT, _PARAMS, _PAYLOAD, _inputs

SUPPORTING = '{"hover_power_w": 119.94, "battery_wh": 274.0, "max_wind_mps": 12.0}'


def test_a_number_the_calculator_never_produced_is_caught() -> None:
    found = unsupported_numerics("Hover power is 90 W for this payload.", SUPPORTING)

    assert found == ["90 W"]


def test_restating_a_supported_number_is_fine() -> None:
    assert unsupported_numerics("Hover power is 119.94 W.", SUPPORTING) == []


def test_rounding_a_supported_number_is_fine() -> None:
    """A calculator value of 119.94 written as "120 W" is readable prose, not invention."""
    assert unsupported_numerics("Hover power is about 120 W.", SUPPORTING) == []


def test_rounding_does_not_launder_a_different_number() -> None:
    """120 rounds from 119.94; 90 does not round from anything here."""
    found = unsupported_numerics("Draw is 90 W and wind is 12 m/s.", SUPPORTING)

    assert found == ["90 W"]


def test_bare_integers_are_not_claims() -> None:
    """ "3 limiting factors" is not a statement about the world; "3 W" is."""
    assert unsupported_numerics("There are 3 limiting factors.", SUPPORTING) == []


def test_every_instance_is_returned_for_logging() -> None:
    found = unsupported_numerics("90 W, then 7 m/s, then 55 %.", SUPPORTING)

    assert len(found) == 3


def test_an_empty_supporting_set_does_not_crash() -> None:
    assert unsupported_numerics("Hover power is 90 W.", "") == ["90 W"]


# --- metrics -----------------------------------------------------------------


def test_suppression_is_counted_by_reason() -> None:
    """A contradiction and an invented number need different responses."""
    metrics = MetricsRegistry()
    metrics.record_brief_suppressed("contradiction")
    metrics.record_brief_suppressed("unsupported_numeric")
    metrics.record_brief_suppressed("unsupported_numeric")

    rendered = metrics.render()

    assert 'suas_brief_suppressed_total{reason="contradiction"} 1' in rendered
    assert 'suas_brief_suppressed_total{reason="unsupported_numeric"} 2' in rendered


def test_hallucinated_citations_are_counted() -> None:
    metrics = MetricsRegistry()
    metrics.record_hallucinated_citations(2)
    metrics.record_hallucinated_citations(0)

    assert "suas_hallucinated_citation_total 2" in metrics.render()


def test_both_counters_are_exported_at_zero() -> None:
    """A counter that only appears once it fires cannot be alerted on."""
    rendered = MetricsRegistry().render()

    assert "suas_hallucinated_citation_total 0" in rendered
    assert "suas_brief_suppressed_total" in rendered


# --- wired into the node, not merely importable -------------------------------
#
# The pure-function tests above all pass with the call removed from the report
# node. These do not: they are what makes the trace a control rather than a
# utility.


async def _run_report(
    session_factory: async_sessionmaker[AsyncSession], text: str
) -> dict[str, Any]:
    deps = GraphDependencies(
        session_factory=session_factory,
        weather=FakeWeatherService(CALM_WEATHER),  # type: ignore[arg-type]
        report=FakeReportService(text),  # type: ignore[arg-type]
    )
    calculations = assess_mission(
        aircraft=_AIRCRAFT, payload=_PAYLOAD, params=_PARAMS, weather=CALM_WEATHER
    )
    assessment = build_assessment(calculations=calculations, inputs=_inputs(CALM_WEATHER))
    state: dict[str, Any] = {
        "aircraft": _AIRCRAFT.model_dump(),
        "weather": CALM_WEATHER.model_dump(),
        "calculations": calculations.model_dump(),
        "assessment": assessment.model_dump(mode="json"),
        "is_viable": True,
        "citations": [],
    }
    return await make_report_node(deps)(state)  # type: ignore[arg-type,no-any-return]


async def test_the_node_suppresses_a_brief_stating_an_invented_wattage(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    written = await _run_report(
        session_factory, "Conditions are good. Hover power is 903 W for this payload."
    )

    assert written["seal_violations"], "an invented wattage reached the operator"
    assert all(code.startswith("unsupported_numeric:") for code in written["seal_violations"])
    assert "903 W" not in written["report"], "the suppressed prose was published anyway"
    assert set(written) <= REPORT_NODE_WRITABLE


async def test_the_node_leaves_a_brief_that_only_restates_the_calculator(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The trace must not suppress everything; that would prove nothing."""
    written = await _run_report(session_factory, "Conditions are within limits.")

    assert written["seal_violations"] == []
    assert written["report"] == "Conditions are within limits."


def test_the_trace_is_unit_blind_and_that_is_recorded() -> None:
    """A known hole, asserted so it stays known.

    Matching is on the numeric value alone. A wind speed in the supporting text
    will vouch for a wattage that happens to round to it. Recorded as a test
    rather than left in a docstring, so that closing it later is a visible
    change rather than a silent one.
    """
    wind_only = '{"max_wind_mps": 6.9}'

    assert unsupported_numerics("Hover power is 7 W.", wind_only) == []
    assert unsupported_numerics("Hover power is 903 W.", wind_only) == ["903 W"]
