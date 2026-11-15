"""Narrative numbers must come from the sealed result, with unit rules."""

from __future__ import annotations

from suas.eval.mission_scoring import ModelAnswer, invented_numbers
from suas.graph.override import apply_sealed_override
from suas.graph.seal import ground_narrative, unsupported_numerics
from suas.schemas.assessment import Decision
from tests.test_mission_eval import _fixture
from tests.test_sealed_override import _pp01_sealed


def test_restating_a_sealed_hover_wattage_is_supported() -> None:
    """The ps-02 false flag: 520.12 W copied from the calculator is not invented."""
    answer = ModelAnswer(
        decision="go",
        mode="advisory",
        hover_power_w=520.12,
        residual_wh=153.1,
        prose=(
            "The mission is go with advisory mode. The hover power is "
            "corrected to 520.12W, and the residual energy is 153.1Wh."
        ),
    )
    fixture = _fixture(
        expected_hover_power_w=520.12,
        expected_residual_wh_range=(152.1, 154.1),
    )
    assert invented_numbers(fixture, answer) == []


def test_an_invented_watt_hour_is_rejected_and_the_template_is_used() -> None:
    """The pp-01 invention: 225.7 Wh is not a sealed figure."""
    assessment, calculations = _pp01_sealed()
    model = ModelAnswer(
        decision="go",
        mode="operational",
        residual_wh=225.7,
        prose="Within temperature and wind limits, residual 225.7 Wh.",
    )
    sealed = apply_sealed_override(assessment, calculations, model)
    published, invented = ground_narrative(sealed.answer.prose, assessment, calculations)
    assert invented == ["225.7 Wh"]
    assert "225.7" not in published
    assert "The generated brief was withheld" in published
    assert assessment.decision is Decision.NO_GO
    assert "NO-GO" in published


def test_a_wind_speed_does_not_support_a_wattage() -> None:
    fixture = _fixture()
    # Calm fixture weather is 3 m/s in the pack's usual shape; pin it.
    answer = ModelAnswer(decision="go", prose="Hover power is 3 W.")
    assert invented_numbers(fixture, answer) == ["3 W"]


def test_text_only_supporting_path_still_accepts_rounding() -> None:
    """Callers that pass only text keep the original unit-blind rounding rule."""
    assert unsupported_numerics("about 120 W", "required energy 119.94") == []
    assert unsupported_numerics("about 90 W", "required energy 119.94") == ["90 W"]
