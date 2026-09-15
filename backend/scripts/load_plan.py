#!/usr/bin/env python3
"""Drive concurrent planning requests and report what broke first.

Costs nothing in model tokens. A plan now stops at the human acknowledgement
before any brief is generated, so the plan path never reaches the model -- the
``?brief=false`` flag the plan originally called for would have been a no-op.
Pass ``--ack`` to additionally acknowledge each plan, which is the path that does
call the model, and keep that run small.

Usage:
    python3 backend/scripts/load_plan.py --requests 100 --concurrency 100
    python3 backend/scripts/load_plan.py --requests 10 --concurrency 10 --ack
"""

from __future__ import annotations

import argparse
import asyncio
import statistics
import sys
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

_BODY: Final[dict[str, Any]] = {
    "aircraft_id": "Skydio_X10D",
    "payload_id": "None",
    "mission_params": {
        "distance_m": 2000.0,
        "hover_time_s": 120.0,
        "target_altitude_m": 120.0,
        "elevation_m": 0.0,
        "latitude": 34.0,
        "longitude": -80.0,
    },
}


@dataclass
class Outcome:
    """What one request did."""

    status: int
    seconds: float
    thread_id: str | None = None
    error: str | None = None


@dataclass
class Report:
    """Aggregated results of a run."""

    outcomes: list[Outcome] = field(default_factory=list)

    @property
    def latencies(self) -> list[float]:
        return sorted(outcome.seconds for outcome in self.outcomes)

    @property
    def server_errors(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status >= 500)

    @property
    def rate_limited(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == 429)

    @property
    def succeeded(self) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status == 200)

    def percentile(self, fraction: float) -> float:
        """Return the latency at a percentile, or 0.0 with no data."""
        values = self.latencies
        if not values:
            return 0.0
        index = min(len(values) - 1, round(fraction * (len(values) - 1)))
        return values[index]


async def _plan_once(client: httpx.AsyncClient, ack: bool) -> Outcome:
    """Issue one plan, optionally acknowledging it, and time the whole thing."""
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        response = await client.post("/api/plan", json=_BODY)
        thread_id: str | None = None
        if response.status_code == 200:
            thread_id = str(response.json().get("thread_id"))
            if ack and thread_id:
                await client.post(
                    f"/api/plan/{thread_id}/ack",
                    json={"action": "confirm", "actor": "load-test"},
                )
        return Outcome(
            status=response.status_code,
            seconds=loop.time() - started,
            thread_id=thread_id,
        )
    except httpx.HTTPError as exc:
        return Outcome(status=0, seconds=loop.time() - started, error=str(exc))


async def run(base_url: str, requests: int, concurrency: int, ack: bool, api_key: str) -> Report:
    """Run the load and return the report."""
    report = Report()
    limiter = asyncio.Semaphore(concurrency)
    headers = {"X-API-Key": api_key} if api_key else {}

    async with httpx.AsyncClient(base_url=base_url, timeout=60.0, headers=headers) as client:

        async def one() -> None:
            async with limiter:
                report.outcomes.append(await _plan_once(client, ack))

        await asyncio.gather(*(one() for _ in range(requests)))
    return report


def _print_report(report: Report, requests: int, concurrency: int, ack: bool) -> None:
    """Print the results in a form worth pasting into an ops document."""
    print(f"requests={requests} concurrency={concurrency} ack={ack}")
    print(f"  200:          {report.succeeded}")
    print(f"  429:          {report.rate_limited}")
    print(f"  5xx:          {report.server_errors}")
    print(f"  transport:    {sum(1 for o in report.outcomes if o.status == 0)}")
    if report.latencies:
        print(f"  p50:          {report.percentile(0.50):.3f}s")
        print(f"  p95:          {report.percentile(0.95):.3f}s")
        print(f"  max:          {max(report.latencies):.3f}s")
        print(f"  mean:         {statistics.fmean(report.latencies):.3f}s")
    threads = {o.thread_id for o in report.outcomes if o.thread_id}
    print(f"  unique threads: {len(threads)}")


def main() -> int:
    """Parse arguments, run the load, and report a pass or fail."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--requests", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--ack", action="store_true", help="also acknowledge each plan")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--p95-budget", type=float, default=2.0)
    parsed = parser.parse_args()

    report = asyncio.run(
        run(
            parsed.base_url,
            parsed.requests,
            parsed.concurrency,
            parsed.ack,
            parsed.api_key,
        )
    )
    _print_report(report, parsed.requests, parsed.concurrency, parsed.ack)

    failures: list[str] = []
    if report.server_errors:
        failures.append(f"{report.server_errors} server errors")
    if report.percentile(0.95) > parsed.p95_budget:
        failures.append(f"p95 {report.percentile(0.95):.3f}s over {parsed.p95_budget}s")
    if report.succeeded + report.rate_limited != parsed.requests:
        failures.append("some requests neither succeeded nor were rate limited")

    if failures:
        print("\nFAIL: " + "; ".join(failures), file=sys.stderr)
        return 1
    print("\nPASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
