"""Confidence intervals and paired comparison.

A rate reported without an interval invites reading noise as movement. Forty
fixtures is a small sample: recall of 0.90 over 40 rows has a 95% interval of
roughly 0.77 to 0.96, and a "regression" from 0.90 to 0.85 sits well inside it.
The interval is what stops the eval generating false alarms.

The backlog entry for this work anticipated a numpy dependency. It is not
needed. The whole module is a square root, an exponential, and binomial
coefficients, and ``math.comb`` computes those exactly with integers where numpy
would have gone through floating-point log-gamma. A safety-critical project does
not take a dependency to reach ``sqrt``.
"""

from dataclasses import dataclass
from math import comb, sqrt
from typing import Final

# Two-sided normal quantile for 95%. Fixed rather than configurable: a report
# whose confidence level moves between runs is not a time series.
Z_95: Final[float] = 1.959963984540054


@dataclass(frozen=True)
class Interval:
    """A rate with its Wilson score interval."""

    rate: float
    low: float
    high: float
    n: int

    def render(self) -> str:
        """Return the form used in reports: ``0.900 [0.774, 0.962] n=40``."""
        return f"{self.rate:.3f} [{self.low:.3f}, {self.high:.3f}] n={self.n}"


def wilson(successes: int, total: int, z: float = Z_95) -> Interval:
    """Return the Wilson score interval for a binomial rate.

    Wilson rather than the normal approximation because the rates that matter
    here sit at the boundary. A hard-fail metric is expected to read 0/40, and
    the normal approximation gives that a zero-width interval -- perfect
    certainty from forty observations, which is not what forty observations buy.
    Wilson gives roughly [0, 0.087]: passing, and honestly bounded.
    """
    if total < 0:
        raise ValueError("total must not be negative")
    if not 0 <= successes <= total:
        raise ValueError(f"successes {successes} outside 0..{total}")
    if total == 0:
        return Interval(rate=0.0, low=0.0, high=0.0, n=0)

    n = float(total)
    p = successes / n
    denominator = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denominator
    spread = (z / denominator) * sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n))
    return Interval(
        rate=p,
        low=max(0.0, centre - spread),
        high=min(1.0, centre + spread),
        n=total,
    )


@dataclass(frozen=True)
class McNemarResult:
    """Discordant pairs between two configurations, and whether they differ."""

    only_a: int
    only_b: int
    p_value: float

    @property
    def discordant(self) -> int:
        """Return the number of fixtures the two configurations disagree on."""
        return self.only_a + self.only_b


def mcnemar(outcomes_a: list[bool], outcomes_b: list[bool]) -> McNemarResult:
    """Compare two retrievers over the same fixtures, pairwise.

    Paired because the fixtures are the same. Comparing two independent rates
    discards the pairing and needs a far larger sample to detect the same
    difference. Only discordant pairs carry information: a row both
    configurations answered correctly says nothing about which is better.

    Exact binomial rather than the chi-square approximation, which is unreliable
    below roughly 25 discordant pairs -- and 40 fixtures will rarely produce
    that many.
    """
    if len(outcomes_a) != len(outcomes_b):
        raise ValueError("paired comparison needs equal-length outcome lists")

    pairs = list(zip(outcomes_a, outcomes_b, strict=True))
    only_a = sum(1 for a, b in pairs if a and not b)
    only_b = sum(1 for a, b in pairs if b and not a)
    discordant = only_a + only_b
    if discordant == 0:
        return McNemarResult(only_a=0, only_b=0, p_value=1.0)

    tail = sum(comb(discordant, k) for k in range(min(only_a, only_b) + 1))
    p_value = min(1.0, 2.0 * tail / (2.0**discordant))
    return McNemarResult(only_a=only_a, only_b=only_b, p_value=p_value)
