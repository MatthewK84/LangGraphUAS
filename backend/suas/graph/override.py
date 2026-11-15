"""Override model-authored decision, mode, and numerics with the sealed result.

The calculator always runs in code before any model call. This module is the
point that makes that fact observable in a scored answer or a logged
disagreement: the model may propose values, and none of them survive.
"""

from dataclasses import dataclass
from math import isclose
from typing import Any, Final

from suas.eval.mission_scoring import ModelAnswer
from suas.schemas.assessment import DeterministicAssessment
from suas.schemas.responses import Calculations

_FLOAT_REL: Final[float] = 1e-9
_FLOAT_ABS: Final[float] = 1e-6


@dataclass(frozen=True)
class SealedOverride:
    """A scored answer owned by the seal, plus every field the model contested."""

    answer: ModelAnswer
    disagreements: tuple[dict[str, Any], ...]


def apply_sealed_override(
    assessment: DeterministicAssessment,
    calculations: Calculations,
    model: ModelAnswer | None,
    *,
    narrative: str | None = None,
) -> SealedOverride:
    """Return the sealed decision, mode, and figures, keeping only model prose.

    A field the model omitted is filled from the seal and is not a disagreement.
    A field the model stated, if it differs, is recorded and then overwritten.
    """
    sealed_decision = assessment.decision.value
    sealed_mode = assessment.mode.value
    sealed_hover = calculations.effective_hover_power_w
    sealed_residual = calculations.battery_check.margin_wh
    prose = narrative if narrative is not None else (model.prose if model is not None else "")
    disagreements: list[dict[str, Any]] = []
    if model is not None:
        _contest(disagreements, "decision", model.decision, sealed_decision)
        _contest(disagreements, "mode", model.mode, sealed_mode)
        _contest(disagreements, "hover_power_w", model.hover_power_w, sealed_hover)
        _contest(disagreements, "residual_wh", model.residual_wh, sealed_residual)
    return SealedOverride(
        answer=ModelAnswer(
            decision=sealed_decision,
            mode=sealed_mode,
            hover_power_w=sealed_hover,
            residual_wh=sealed_residual,
            prose=prose,
        ),
        disagreements=tuple(disagreements),
    )


def _contest(
    disagreements: list[dict[str, Any]],
    field: str,
    proposed: object,
    sealed: object,
) -> None:
    """Record ``field`` when the model stated a value that is not the sealed one."""
    if proposed is None:
        return
    if _same(proposed, sealed):
        return
    disagreements.append({"field": field, "model": proposed, "sealed": sealed})


def _same(proposed: object, sealed: object) -> bool:
    """Return whether two stated values agree, with a tight tolerance for floats."""
    if isinstance(proposed, float) and isinstance(sealed, (int, float)):
        return isclose(proposed, float(sealed), rel_tol=_FLOAT_REL, abs_tol=_FLOAT_ABS)
    if isinstance(proposed, (int, float)) and isinstance(sealed, (int, float)):
        return isclose(float(proposed), float(sealed), rel_tol=_FLOAT_REL, abs_tol=_FLOAT_ABS)
    return proposed == sealed
