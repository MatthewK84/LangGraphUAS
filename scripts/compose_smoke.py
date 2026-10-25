"""Smoke a running Compose stack the way the README quickstart leaves it.

Run after ``DEMO_MODE=true docker compose up --wait`` (#97). Standard library
only, so CI runs it with the runner's own ``python3``. Prints each check and
exits non-zero if any fails.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Final

BACKEND: Final[str] = "http://localhost:8000"
FRONTEND: Final[str] = "http://localhost:3000"
READY_TIMEOUT_S: Final[float] = 120.0

OPERATIONAL_PLAN: Final[dict[str, Any]] = {
    "aircraft_id": "Skydio_X10D",
    "payload_id": "None",
    "assessment_mode": "operational",
    "mission_params": {
        "distance_m": 2000.0,
        "hover_time_s": 120.0,
        "target_altitude_m": 120.0,
        "elevation_m": 0.0,
        "latitude": 34.0,
        "longitude": -80.0,
    },
}


def call(url: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    """Return (status, parsed JSON or None) for a GET, or a JSON POST when ``body`` is set."""
    if not url.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise ValueError(f"compose smoke only calls the local stack, not {url!r}")
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(  # noqa: S310 (local http only, checked above)
        url, data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310 (fixed localhost URLs)
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, None


def wait_until_ready() -> tuple[int, Any]:
    """Poll backend /ready until 200 or the timeout, returning the last answer."""
    deadline = time.monotonic() + READY_TIMEOUT_S
    while True:
        try:
            status, body = call(f"{BACKEND}/ready")
        except OSError:
            status, body = 0, None
        if status == 200 or time.monotonic() > deadline:
            return status, body
        time.sleep(2)


def main() -> int:
    """Run every check and return the process exit code."""
    ready_status, ready = wait_until_ready()
    page_status, _ = call(FRONTEND)
    aircraft_status, aircraft = call(f"{FRONTEND}/api/aircraft")
    plan_status, plan = call(f"{FRONTEND}/api/plan", OPERATIONAL_PLAN)
    assessment = (plan or {}).get("assessment") or {}
    checks = [
        ("backend /ready 200", ready_status == 200),
        ("migrations ok", (ready or {}).get("migrations") == "ok"),
        ("frontend page 200", page_status == 200),
        ("catalog through the frontend", aircraft_status == 200 and bool(aircraft)),
        ("plan through the frontend 200", plan_status == 200),
        (
            "weather is the demo fixture",
            ((plan or {}).get("weather") or {}).get("source") == "fixture",
        ),
        (
            "operational request came back advisory",
            assessment.get("mode") == "advisory",
        ),
        (
            "blocked by WEATHER_NOT_LIVE",
            "WEATHER_NOT_LIVE" in assessment.get("blockers", []),
        ),
    ]
    for name, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    failed = [name for name, passed in checks if not passed]
    if failed:
        print(f"Compose smoke failed: {', '.join(failed)}")
        return 1
    print("Compose smoke passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
