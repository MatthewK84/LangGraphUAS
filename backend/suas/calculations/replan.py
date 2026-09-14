"""Comparing a briefed plan against what the aircraft is reporting.

Pure functions. The briefed assessment is evidence of what was signed; this
module does not touch it. It computes what is left in the pack, what the rest of
the mission needs, and says where the two no longer meet.

The energy question is deliberately asked the conservative way round. Remaining
capacity is derated for the temperature the aircraft is actually in, not the one
it was briefed for, and the reserve is measured against the same derated
capacity rather than the nameplate figure -- a reserve computed on nameplate
watt-hours is not a reserve on a cold day.
"""

from dataclasses import dataclass
from typing import Final

from suas.calculations.battery import calculate_temperature_capacity_factor
from suas.calculations.physics import calculate_energy_required
from suas.schemas.alerts import Alert, AlertCode, RecommendedAction, Severity
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.telemetry import TelemetrySnapshot

# A snapshot older than this cannot carry operational weight: the aircraft has
# moved and drawn power since, and the numbers describe a moment that is gone.
MAX_OPERATIONAL_SNAPSHOT_AGE_S: Final[float] = 30.0

# Residual below this multiple of the reserve is a warning rather than an abort.
# One and a half leaves room to reach an alternate; the exact figure is a policy
# choice and lives in config, not in judgement at the call site.
NEAR_RESERVE_MULTIPLE: Final[float] = 1.5


@dataclass(frozen=True)
class LiveEnergy:
    """What the pack holds now, and what the rest of the mission needs."""

    available_wh: float
    reserve_wh: float
    required_wh: float
    residual_wh: float
    temperature_factor: float

    @property
    def is_below_reserve(self) -> bool:
        """Return whether the remaining mission eats into the reserve."""
        return self.residual_wh < self.reserve_wh

    @property
    def is_near_reserve(self) -> bool:
        """Return whether the residual is uncomfortably close to the reserve."""
        return self.residual_wh < self.reserve_wh * NEAR_RESERVE_MULTIPLE


def compute_live_energy(
    *,
    aircraft: Aircraft,
    payload: Payload,
    snapshot: TelemetrySnapshot,
    reserve_percent: float,
) -> LiveEnergy:
    """Return the live energy picture for the remainder of a mission.

    Capacity is state of charge against the nameplate pack, derated for the
    temperature the aircraft reports. The energy still required is computed for
    the leg the aircraft says is left, not the one it was briefed on.
    """
    factor: float = calculate_temperature_capacity_factor(snapshot.oat_c)
    available_wh: float = aircraft.battery_wh * snapshot.soc_fraction * factor
    reserve_wh: float = aircraft.battery_wh * factor * (reserve_percent / 100.0)

    payload_power_w: float = payload.power_draw_w if snapshot.payload_attached else 0.0
    required_wh: float = calculate_energy_required(
        distance_m=snapshot.remaining_leg_m,
        hover_time_s=snapshot.remaining_hover_s,
        ground_speed_mps=aircraft.cruise_speed_mps,
        hover_power_w=aircraft.hover_power_w,
        cruise_power_w=aircraft.cruise_power_w,
        payload_power_w=payload_power_w,
    )
    return LiveEnergy(
        available_wh=round(available_wh, 2),
        reserve_wh=round(reserve_wh, 2),
        required_wh=round(required_wh, 2),
        residual_wh=round(available_wh - required_wh, 2),
        temperature_factor=factor,
    )


def _energy_alert(live: LiveEnergy, briefed_margin_wh: float) -> Alert | None:
    """Return the energy alert this comparison warrants, if any."""
    delta = {"residual_wh": round(live.residual_wh - briefed_margin_wh, 2)}
    briefed = {"margin_wh": briefed_margin_wh}
    observed = {
        "available_wh": live.available_wh,
        "required_wh": live.required_wh,
        "residual_wh": live.residual_wh,
        "reserve_wh": live.reserve_wh,
    }
    if live.is_below_reserve:
        return Alert(
            severity=Severity.ABORT,
            code=AlertCode.ENERGY_BELOW_RESERVE,
            message=(
                f"Remaining energy {live.residual_wh} Wh is below the "
                f"{live.reserve_wh} Wh reserve for the leg still to fly."
            ),
            briefed=briefed,
            live=observed,
            delta=delta,
            recommended_action=RecommendedAction.LAND_NOW,
        )
    if live.is_near_reserve:
        return Alert(
            severity=Severity.WARNING,
            code=AlertCode.ENERGY_NEAR_RESERVE,
            message=(
                f"Remaining energy {live.residual_wh} Wh is within "
                f"{NEAR_RESERVE_MULTIPLE} x the {live.reserve_wh} Wh reserve."
            ),
            briefed=briefed,
            live=observed,
            delta=delta,
            recommended_action=RecommendedAction.LAND_SOON,
        )
    return None


def _wind_alert(aircraft: Aircraft, snapshot: TelemetrySnapshot) -> Alert | None:
    """Return a wind alert when reported wind exceeds the airframe limit."""
    if snapshot.wind_mps is None:
        return Alert(
            severity=Severity.WATCH,
            code=AlertCode.WEATHER_DEGRADED,
            message="Snapshot reports no wind, so the wind limit could not be checked.",
            briefed={"max_wind_mps": aircraft.max_wind_mps},
            live={"wind_mps": None},
            recommended_action=RecommendedAction.ADVISORY_ONLY,
        )
    if snapshot.wind_mps > aircraft.max_wind_mps:
        return Alert(
            severity=Severity.ABORT,
            code=AlertCode.WIND_EXCEEDS_LIMIT,
            message=(
                f"Reported wind {snapshot.wind_mps} m/s exceeds the airframe "
                f"limit of {aircraft.max_wind_mps} m/s."
            ),
            briefed={"max_wind_mps": aircraft.max_wind_mps},
            live={"wind_mps": snapshot.wind_mps},
            delta={"wind_mps": round(snapshot.wind_mps - aircraft.max_wind_mps, 2)},
            recommended_action=RecommendedAction.LAND_NOW,
        )
    return None


def _staleness_alert(snapshot: TelemetrySnapshot, age_s: float) -> Alert | None:
    """Return a staleness alert when the snapshot is too old to act on."""
    if age_s <= MAX_OPERATIONAL_SNAPSHOT_AGE_S:
        return None
    return Alert(
        severity=Severity.WATCH,
        code=AlertCode.SOC_STALE,
        message=(
            f"Snapshot is {round(age_s, 1)} s old, beyond the "
            f"{MAX_OPERATIONAL_SNAPSHOT_AGE_S} s limit for operational use."
        ),
        live={"age_s": round(age_s, 1), "ts": snapshot.ts.isoformat()},
        recommended_action=RecommendedAction.ADVISORY_ONLY,
    )


def _payload_alert(payload: Payload, snapshot: TelemetrySnapshot) -> Alert | None:
    """Return an alert when the aircraft reports a payload state we did not brief."""
    briefed_has_payload: bool = payload.weight_kg > 0.0
    if briefed_has_payload == snapshot.payload_attached:
        return None
    return Alert(
        severity=Severity.WATCH,
        code=AlertCode.PAYLOAD_MISMATCH,
        message=(
            "Aircraft reports a different payload state than was briefed; the "
            "energy budget below assumes the reported state."
        ),
        briefed={"payload_attached": briefed_has_payload, "payload_id": payload.id},
        live={"payload_attached": snapshot.payload_attached},
        recommended_action=RecommendedAction.ADVISORY_ONLY,
    )


def evaluate_replan(
    *,
    aircraft: Aircraft,
    payload: Payload,
    snapshot: TelemetrySnapshot,
    briefed_margin_wh: float,
    reserve_percent: float,
    age_s: float,
) -> tuple[LiveEnergy, list[Alert]]:
    """Return the live energy picture and every alert it warrants.

    Alerts are returned in a stable order rather than collapsed to one, because
    an aircraft can be both low on energy and beyond its wind limit, and an
    operator needs to see both.
    """
    live: LiveEnergy = compute_live_energy(
        aircraft=aircraft,
        payload=payload,
        snapshot=snapshot,
        reserve_percent=reserve_percent,
    )
    candidates: list[Alert | None] = [
        _energy_alert(live, briefed_margin_wh),
        _wind_alert(aircraft, snapshot),
        _staleness_alert(snapshot, age_s),
        _payload_alert(payload, snapshot),
    ]
    return live, [alert for alert in candidates if alert is not None]
