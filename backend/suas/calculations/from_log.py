"""Power estimates from recorded flight telemetry.

Pure functions: samples in, numbers out, no I/O. This is the only path by which a
measured figure can reach the reference data, so it is held to the same standard
as the rest of the calculator -- and it reports how much the estimate should be
trusted rather than returning a bare number.

The selection rules matter more than the statistics. A "hover" sample taken while
the aircraft was climbing is not a hover sample, and averaging it in biases hover
power downward, which biases the energy budget toward GO. Windows are therefore
rejected on measured climb rate rather than on the label in the file.
"""

from dataclasses import dataclass
from itertools import pairwise
from statistics import median
from typing import Final

from suas.schemas.flight_log import FlightLogSample, FlightPhase
from suas.schemas.provenance import Confidence

# A hover sample may drift this much vertically. Above it the aircraft is
# climbing or descending, and the power reading belongs to that phase.
MAX_HOVER_CLIMB_RATE_MPS: Final[float] = 0.5

# Level flight for the purposes of a cruise sample.
MAX_CRUISE_CLIMB_RATE_MPS: Final[float] = 1.0

# Below this the aircraft is not cruising, whatever the file says.
MIN_CRUISE_SPEED_MPS: Final[float] = 3.0

# A hover sample should not be moving laterally either.
MAX_HOVER_SPEED_MPS: Final[float] = 1.5

# Sample counts and spread at which an estimate earns each confidence level.
_HIGH_MIN_SAMPLES: Final[int] = 30
_HIGH_MAX_SPREAD: Final[float] = 0.15
_MEDIUM_MIN_SAMPLES: Final[int] = 15
_MEDIUM_MAX_SPREAD: Final[float] = 0.30


@dataclass(frozen=True)
class PowerEstimate:
    """A measured power figure and how much to trust it."""

    median_w: float
    sample_count: int
    iqr_w: float
    confidence: Confidence

    @property
    def relative_spread(self) -> float:
        """Return the interquartile range as a fraction of the median."""
        if self.median_w <= 0.0:
            return 1.0
        return self.iqr_w / self.median_w


def climb_rates_mps(samples: list[FlightLogSample]) -> list[float]:
    """Return the vertical rate at each sample, computed from the one before it.

    The first sample has no predecessor and is reported as zero, which makes it
    eligible for selection. That is deliberate: one sample either way cannot move
    a median, and discarding it would complicate every caller. An empty log
    yields an empty list, so the result always matches the input length and
    callers can zip the two strictly.
    """
    if not samples:
        return []
    rates: list[float] = [0.0]
    for previous, current in pairwise(samples):
        seconds: float = (current.timestamp - previous.timestamp).total_seconds()
        if seconds <= 0.0:
            rates.append(0.0)
            continue
        rates.append((current.alt_m - previous.alt_m) / seconds)
    return rates


def _is_stationary(sample: FlightLogSample, limit: float) -> bool:
    """Return whether the sample is slower than the limit, or has no speed logged."""
    speed = sample.speed_mps
    return speed is None or speed <= limit


def select_hover_samples(samples: list[FlightLogSample]) -> list[FlightLogSample]:
    """Return the samples that are genuinely in a hover.

    A row labelled ``climb`` or ``descent`` is excluded outright. Everything else
    is tested against its measured vertical rate and lateral speed, so a
    mislabelled row cannot smuggle climb power into a hover figure.
    """
    rates: list[float] = climb_rates_mps(samples)
    return [
        sample
        for sample, rate in zip(samples, rates, strict=True)
        if sample.phase not in {FlightPhase.CLIMB, FlightPhase.DESCENT, FlightPhase.CRUISE}
        and abs(rate) <= MAX_HOVER_CLIMB_RATE_MPS
        and _is_stationary(sample, MAX_HOVER_SPEED_MPS)
    ]


def select_cruise_samples(samples: list[FlightLogSample]) -> list[FlightLogSample]:
    """Return the samples in level forward flight."""
    rates: list[float] = climb_rates_mps(samples)
    selected: list[FlightLogSample] = []
    for sample, rate in zip(samples, rates, strict=True):
        if sample.phase in {FlightPhase.CLIMB, FlightPhase.DESCENT, FlightPhase.HOVER}:
            continue
        speed = sample.speed_mps
        if speed is None or speed < MIN_CRUISE_SPEED_MPS:
            continue
        if abs(rate) <= MAX_CRUISE_CLIMB_RATE_MPS:
            selected.append(sample)
    return selected


def _interquartile_range(values: list[float]) -> float:
    """Return the interquartile range, or 0.0 when there is too little data."""
    if len(values) < 4:
        return 0.0
    ordered: list[float] = sorted(values)
    midpoint: int = len(ordered) // 2
    lower: float = median(ordered[:midpoint])
    upper: float = median(ordered[-midpoint:])
    return upper - lower


def _confidence_for(sample_count: int, spread: float) -> Confidence:
    """Return how much to trust an estimate of this size and spread."""
    if sample_count >= _HIGH_MIN_SAMPLES and spread <= _HIGH_MAX_SPREAD:
        return Confidence.HIGH
    if sample_count >= _MEDIUM_MIN_SAMPLES and spread <= _MEDIUM_MAX_SPREAD:
        return Confidence.MEDIUM
    return Confidence.LOW


def estimate_power(samples: list[FlightLogSample]) -> PowerEstimate | None:
    """Return the power estimate for a set of selected samples, or None if empty.

    The median is used rather than the mean because a log routinely contains
    brief spikes -- a gust correction, a payload switching on -- and a mean lets
    one of them move the figure the energy budget is built on.
    """
    if not samples:
        return None
    values: list[float] = [sample.effective_power_w for sample in samples]
    centre: float = median(values)
    iqr: float = _interquartile_range(values)
    spread: float = iqr / centre if centre > 0.0 else 1.0
    return PowerEstimate(
        median_w=round(centre, 2),
        sample_count=len(values),
        iqr_w=round(iqr, 2),
        confidence=_confidence_for(len(values), spread),
    )


def estimate_hover_power(samples: list[FlightLogSample]) -> PowerEstimate | None:
    """Return the hover power estimate for a whole log."""
    return estimate_power(select_hover_samples(samples))


def estimate_cruise_power(samples: list[FlightLogSample]) -> PowerEstimate | None:
    """Return the cruise power estimate for a whole log."""
    return estimate_power(select_cruise_samples(samples))
