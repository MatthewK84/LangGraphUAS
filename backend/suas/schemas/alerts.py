"""What a replan tells an operator.

An alert is a statement about the difference between what was briefed and what
the aircraft is reporting. It carries both number sets and the delta between
them, so the recommendation can be checked rather than taken on faith.
"""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """How much attention an alert demands."""

    INFO = "info"
    WATCH = "watch"
    WARNING = "warning"
    ABORT = "abort"


class AlertCode(StrEnum):
    """Machine-readable reasons a replan raised something."""

    ENERGY_BELOW_RESERVE = "ENERGY_BELOW_RESERVE"
    ENERGY_NEAR_RESERVE = "ENERGY_NEAR_RESERVE"
    WIND_EXCEEDS_LIMIT = "WIND_EXCEEDS_LIMIT"
    SOC_STALE = "SOC_STALE"
    WEATHER_DEGRADED = "WEATHER_DEGRADED"
    PAYLOAD_MISMATCH = "PAYLOAD_MISMATCH"


class RecommendedAction(StrEnum):
    """What the operator should do about it."""

    CONTINUE = "continue"
    LAND_SOON = "land_soon"
    LAND_NOW = "land_now"
    ADVISORY_ONLY = "advisory_only"


# Ordered worst-last, so the overall severity of a set of alerts is a max.
_SEVERITY_ORDER: dict[Severity, int] = {
    Severity.INFO: 0,
    Severity.WATCH: 1,
    Severity.WARNING: 2,
    Severity.ABORT: 3,
}

_ACTION_ORDER: dict[RecommendedAction, int] = {
    RecommendedAction.CONTINUE: 0,
    RecommendedAction.ADVISORY_ONLY: 1,
    RecommendedAction.LAND_SOON: 2,
    RecommendedAction.LAND_NOW: 3,
}


class Alert(BaseModel):
    """One finding from comparing a briefed plan against live telemetry."""

    model_config = ConfigDict(frozen=True)

    severity: Severity
    code: AlertCode
    message: str
    briefed: dict[str, Any] = Field(default_factory=dict)
    live: dict[str, Any] = Field(default_factory=dict)
    delta: dict[str, Any] = Field(default_factory=dict)
    recommended_action: RecommendedAction = RecommendedAction.CONTINUE


def worst_severity(alerts: list[Alert]) -> Severity:
    """Return the highest severity among alerts, or INFO when there are none."""
    if not alerts:
        return Severity.INFO
    return max((alert.severity for alert in alerts), key=lambda item: _SEVERITY_ORDER[item])


def strongest_action(alerts: list[Alert]) -> RecommendedAction:
    """Return the most cautious recommended action among alerts."""
    if not alerts:
        return RecommendedAction.CONTINUE
    return max(
        (alert.recommended_action for alert in alerts),
        key=lambda item: _ACTION_ORDER[item],
    )
