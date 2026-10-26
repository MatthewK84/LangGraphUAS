"""Smoke a running Compose stack the way the README quickstart leaves it.

Run after ``DEMO_MODE=true docker compose up --wait`` (#97). Everything goes
through the frontend's server-side proxy, the path the dashboard uses:

- the catalog must match the interfaces in ``frontend/src/lib/types.ts``, so a
  contract break between the containers fails the run (#116);
- the golden path is plan, read the pending thread, acknowledge, read it back.
  On fixture weather every plan must stay advisory;
- a second browser (its own cookie jar) can neither read nor sign the first
  browser's thread (#82).

Standard library only, so CI runs it with the runner's own ``python3``. Prints
each check and exits non-zero if any fails.
"""

import http.cookiejar
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Final

BACKEND: Final[str] = "http://localhost:8000"
FRONTEND: Final[str] = "http://localhost:3000"
READY_TIMEOUT_S: Final[float] = 120.0
FRONTEND_TYPES: Final[Path] = (
    Path(__file__).resolve().parent.parent / "frontend/src/lib/types.ts"
)

_FIELD: Final[re.Pattern[str]] = re.compile(
    r"^\s*(?:readonly\s+)?(\w+)\s*:\s*([^;]+);", re.MULTILINE
)
_JSON_TYPES: Final[dict[str, type | tuple[type, ...]]] = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
}

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


def new_browser() -> urllib.request.OpenerDirector:
    """Return an opener with its own cookie jar: one simulated browser (#82)."""
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


DASHBOARD: Final[urllib.request.OpenerDirector] = new_browser()


def build_request(
    url: str, body: dict[str, Any] | None = None
) -> urllib.request.Request:
    """Build a GET, or a JSON POST from the dashboard's origin when ``body`` is set."""
    if not url.startswith(("http://localhost:", "http://127.0.0.1:")):
        raise ValueError(f"compose smoke only calls the local stack, not {url!r}")
    headers = {"Content-Type": "application/json"}
    if body is not None:
        headers["Origin"] = FRONTEND  # the proxy refuses cross-origin POSTs (#82)
    data = None if body is None else json.dumps(body).encode()
    return urllib.request.Request(url, data=data, headers=headers)  # noqa: S310 (local http only, checked above)


def call(
    url: str,
    body: dict[str, Any] | None = None,
    browser: urllib.request.OpenerDirector = DASHBOARD,
) -> tuple[int, Any]:
    """Return (status, parsed JSON or None) for a GET, or a JSON POST when ``body`` is set."""
    request = build_request(url, body)
    try:
        with browser.open(request, timeout=60) as response:
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


def interface_fields(source: str, name: str) -> dict[str, str]:
    """Return the required fields of TypeScript ``interface name`` and their types."""
    match = re.search(rf"export interface {name} \{{(.*?)\n\}}", source, re.DOTALL)
    if match is None:
        raise ValueError(f"interface {name} not found")
    return {field: ts_type.strip() for field, ts_type in _FIELD.findall(match.group(1))}


def _type_problem(value: Any, ts_type: str) -> str | None:
    """Describe a JSON value that does not fit a primitive TypeScript type."""
    expected = _JSON_TYPES.get(ts_type)
    if expected is None:
        return None  # Unions and nested types: presence is checked, shape is not.
    fits = isinstance(value, expected) and (
        ts_type == "boolean" or not isinstance(value, bool)
    )
    return None if fits else f"is {type(value).__name__}, frontend expects {ts_type}"


def contract_breaks(
    label: str, items: list[dict[str, Any]], fields: dict[str, str]
) -> list[str]:
    """List every way ``items`` fails the frontend's declared ``fields``."""
    if not items:
        return [f"{label} empty"]
    breaks: list[str] = []
    for item in items:
        for field, ts_type in fields.items():
            where = f"{label}[{item.get('id')}].{field}"
            if field not in item:
                breaks.append(f"{where} missing")
                continue
            problem = _type_problem(item[field], ts_type)
            if problem is not None:
                breaks.append(f"{where} {problem}")
    return breaks


def stack_checks() -> list[tuple[str, bool]]:
    """The stack is up: backend ready with migrations applied, dashboard served."""
    ready_status, ready = wait_until_ready()
    page_status, _ = call(FRONTEND)
    return [
        ("backend /ready 200", ready_status == 200),
        ("migrations ok", (ready or {}).get("migrations") == "ok"),
        ("frontend page 200", page_status == 200),
    ]


def catalog_checks() -> list[tuple[str, bool]]:
    """Each catalog, read through the frontend, matches the frontend's interface."""
    source = FRONTEND_TYPES.read_text(encoding="utf-8")
    checks: list[tuple[str, bool]] = []
    for path, interface in (
        ("aircraft", "AircraftSummary"),
        ("payloads", "PayloadSummary"),
    ):
        status, items = call(f"{FRONTEND}/api/{path}")
        breaks = contract_breaks(
            path,
            items if isinstance(items, list) else [],
            interface_fields(source, interface),
        )
        for problem in breaks:
            print(f"  contract break: {problem}")
        checks.append(
            (
                f"{path} through the frontend matches {interface}",
                status == 200 and not breaks,
            )
        )
    return checks


def _is_advisory_on_fixture(body: Any) -> bool:
    assessment = (body or {}).get("assessment") or {}
    weather = (body or {}).get("weather") or {}
    return (
        weather.get("source") == "fixture"
        and assessment.get("mode") == "advisory"
        and "WEATHER_NOT_LIVE" in assessment.get("blockers", [])
    )


def golden_path_checks() -> list[tuple[str, bool]]:
    """Plan, read the pending thread, acknowledge, read it back: all via the frontend."""
    plan_status, plan = call(f"{FRONTEND}/api/plan", OPERATIONAL_PLAN)
    plan = plan or {}
    thread = f"{FRONTEND}/api/plan/{plan.get('thread_id', 'missing')}"
    pending_status, pending = call(thread)
    signature = {
        "action": "confirm",
        "actor": "compose-smoke",
        "inputs_hash": (plan.get("assessment") or {}).get("inputs_hash"),
    }
    stranger = new_browser()
    peek_status, peek = call(thread, browser=stranger)
    steal_status, _ = call(f"{thread}/ack", signature, browser=stranger)
    ack_status, acked = call(f"{thread}/ack", signature)
    final_status, final = call(thread)
    acked, final, pending = acked or {}, final or {}, pending or {}
    return [
        (
            "plan 200 and awaiting acknowledgement",
            plan_status == 200 and plan.get("awaiting_ack") is True,
        ),
        (
            "operational request came back advisory on fixture weather",
            _is_advisory_on_fixture(plan),
        ),
        (
            "pending thread readable",
            pending_status == 200 and pending.get("awaiting_ack") is True,
        ),
        (
            "another browser sees the thread as unknown",
            peek_status == 200 and (peek or {}).get("found") is False,
        ),
        ("another browser cannot sign it", steal_status == 404),
        (
            "acknowledgement accepted",
            ack_status == 200 and acked.get("awaiting_ack") is False,
        ),
        ("brief written after the signature", bool(acked.get("report"))),
        (
            "thread reads back signed",
            final_status == 200 and final.get("awaiting_ack") is False,
        ),
        ("signed plan still advisory", _is_advisory_on_fixture(final)),
    ]


def main() -> int:
    """Run every check and return the process exit code."""
    checks = stack_checks() + catalog_checks() + golden_path_checks()
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
