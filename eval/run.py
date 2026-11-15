#!/usr/bin/env python3
"""Run the frozen mission pack against one or more providers.

Offline by default. No network is touched unless a provider that needs one is
named explicitly, so the pack can be run in CI, on a plane, or by a reviewer who
has no API key:

    python3 eval/run.py                      # offline providers, both tracks
    python3 eval/run.py --write              # also write eval/results/<date>/
    python3 eval/run.py --provider openai --track no_tools

The openai provider talks to an OpenAI-compatible ``/v1/chat/completions``
endpoint configured by environment, never by a hardcoded host or model:

``SUAS_EVAL_BASE_URL``, ``SUAS_EVAL_MODEL`` (required), plus optional
``SUAS_EVAL_API_KEY``, ``SUAS_EVAL_TEMPERATURE`` (default 0.0),
``SUAS_EVAL_SEED`` (default 42), ``SUAS_EVAL_PROVIDER_NAME``, and the
``SUAS_EVAL_QUANTIZATION`` / ``SUAS_EVAL_RUNTIME`` / ``SUAS_EVAL_HARDWARE`` /
``SUAS_EVAL_HF_REPO`` / ``SUAS_EVAL_FILENAME`` / ``SUAS_EVAL_SHA256``
fields recorded in the results file. This is not invoked from CI.

Two tracks, as in docs/backlog/10:

``no_tools``         the provider answers from the prompt alone.
``calculator_tool``  the provider may call the deterministic engine.

The offline providers are not stand-ins for a model. They are controls. ``oracle``
calls the calculator and should score zero on every failure count -- if it does
not, the harness is broken before any model is measured. ``constant_power`` holds
hover watts at the unladen figure however heavy the payload, which is the
specific mistake the payload-scaling trap is built to catch. A harness that
cannot separate those two cannot say anything about a real model.

A real model is reached only with ``--provider openai`` and the ``SUAS_EVAL_*``
environment. That is the only path that touches the network. Do not add it to CI.
"""

import argparse
import json
import sys
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from openai_provider import (  # noqa: E402
    OpenAICompatibleProvider,
    endpoint_metadata,
    load_endpoint,
)

from suas.calculations.assessment import assess_mission, build_assessment  # noqa: E402
from suas.db.seed import load_rows  # noqa: E402
from suas.eval.mission_scoring import (  # noqa: E402
    MissionFixture,
    ModelAnswer,
    Scores,
    score_one,
)
from suas.schemas.domain import Aircraft, Payload  # noqa: E402
from suas.schemas.requests import MissionParams  # noqa: E402
from suas.schemas.responses import WeatherReading  # noqa: E402

FIXTURES: Final[Path] = REPO_ROOT / "eval" / "fixtures" / "missions.jsonl"
RESULTS: Final[Path] = REPO_ROOT / "eval" / "results"


class Provider(Protocol):
    """One thing that can answer a mission fixture."""

    name: str
    track: str

    def answer(self, fixture: MissionFixture) -> ModelAnswer:
        """Return this provider's answer for one fixture."""
        ...


def _catalog() -> tuple[dict[str, Aircraft], dict[str, Payload]]:
    aircraft = {
        row["id"]: Aircraft.model_validate(row) for row in load_rows("aircraft.json")
    }
    payloads = {
        row["id"]: Payload.model_validate(row) for row in load_rows("payloads.json")
    }
    return aircraft, payloads


class OracleProvider:
    """Calls the deterministic engine. The control that must score zero."""

    name = "oracle"
    track = "calculator_tool"

    def __init__(self) -> None:
        self._aircraft, self._payloads = _catalog()

    def answer(self, fixture: MissionFixture) -> ModelAnswer:
        aircraft = self._aircraft[fixture.airframe]
        payload = self._payloads[fixture.payload]
        params = MissionParams.model_validate(fixture.params)
        weather = WeatherReading.model_validate(fixture.weather)
        calculations = assess_mission(
            aircraft=aircraft, payload=payload, params=params, weather=weather
        )
        assessment = build_assessment(
            calculations=calculations,
            inputs={"fixture": fixture.fixture_id},
            weather=weather,
            aircraft=aircraft,
            payload=payload,
        )
        return ModelAnswer(
            decision=assessment.decision.value,
            mode=assessment.mode.value,
            hover_power_w=calculations.effective_hover_power_w,
            residual_wh=calculations.battery_check.margin_wh,
            prose="",
        )


class ConstantPowerProvider:
    """Holds hover power at the unladen figure and clears anything with margin.

    The failure mode the pack is built around: hover power does not scale with
    mass, so a heavy payload looks affordable. It also claims ``operational``
    regardless of weather provenance, which the fallback trap catches.
    """

    name = "constant_power"
    track = "no_tools"

    def __init__(self) -> None:
        self._aircraft, self._payloads = _catalog()

    def answer(self, fixture: MissionFixture) -> ModelAnswer:
        aircraft = self._aircraft[fixture.airframe]
        params = MissionParams.model_validate(fixture.params)
        weather = WeatherReading.model_validate(fixture.weather)
        # Unladen hover power, taken once and never adjusted for the payload.
        unladen = assess_mission(
            aircraft=aircraft,
            payload=self._payloads["None"],
            params=params,
            weather=weather,
        )
        hover = unladen.effective_hover_power_w
        residual = unladen.battery_check.margin_wh
        return ModelAnswer(
            decision="go" if residual > 0 else "no_go",
            mode="operational",
            hover_power_w=hover,
            residual_wh=residual,
            prose=f"Hover power is {hover:.0f} W and the reserve is comfortable.",
        )


def load_fixtures() -> list[MissionFixture]:
    """Return the frozen pack."""
    rows: list[MissionFixture] = []
    for line in FIXTURES.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data: dict[str, Any] = json.loads(line)
        low, high = data["expected_residual_wh_range"]
        rows.append(
            MissionFixture(
                fixture_id=data["id"],
                trap=data["trap"],
                airframe=data["airframe"],
                payload=data["payload"],
                params=data["params"],
                weather=data["weather"],
                expected_decision=data["expected_decision"],
                expected_mode=data["expected_mode"],
                expected_residual_wh_range=(low, high),
                expected_hover_power_w=data["expected_hover_power_w"],
                calculator_version=data["calculator_version"],
            )
        )
    return rows


def run_provider(provider: Provider, fixtures: list[MissionFixture]) -> dict[str, Any]:
    """Score one provider over the whole pack, and per trap."""
    overall = Scores()
    per_trap: dict[str, Scores] = {}
    cases: list[dict[str, Any]] = []
    started = time.perf_counter()
    for fixture in fixtures:
        answer = provider.answer(fixture)
        before = Scores()
        score_one(fixture, answer, overall)
        score_one(fixture, answer, per_trap.setdefault(fixture.trap, Scores()))
        score_one(fixture, answer, before)
        case: dict[str, Any] = {
            "fixture_id": fixture.fixture_id,
            "trap": fixture.trap,
            "expected_decision": fixture.expected_decision,
            "expected_mode": fixture.expected_mode,
            "answer": {
                "decision": answer.decision,
                "mode": answer.mode,
                "hover_power_w": answer.hover_power_w,
                "residual_wh": answer.residual_wh,
                "prose": answer.prose,
            },
            "unsafe_go": bool(before.unsafe_go),
            "missed_go": bool(before.missed_go),
            "mode_violation": bool(before.mode_violation),
            "invented_number": bool(before.invented_number),
        }
        raw = getattr(provider, "last_raw", None)
        if raw is not None:
            case["raw"] = raw
        tools = getattr(provider, "last_tool_results", None)
        if tools:
            case["tool_results"] = tools
        disagreements = getattr(provider, "last_disagreements", None)
        if disagreements:
            case["disagreements"] = disagreements
        source = getattr(provider, "last_narrative_source", None)
        if source:
            case["narrative_source"] = source
        ungrounded = getattr(provider, "last_ungrounded", None)
        if ungrounded:
            case["ungrounded_numerics"] = ungrounded
        cases.append(case)

    report: dict[str, Any] = {
        "provider": provider.name,
        "track": provider.track,
        "fixtures": len(fixtures),
        "calculator_version": fixtures[0].calculator_version if fixtures else None,
        "scores": _summarize(overall),
        "per_trap": {
            name: _summarize(scores) for name, scores in sorted(per_trap.items())
        },
        "wall_time_s": round(time.perf_counter() - started, 3),
        "cases": cases,
    }
    return report


def _summarize(scores: Scores) -> dict[str, Any]:
    """Return counts plus the worst error, which is what a reader acts on."""
    data = asdict(scores)
    energy = scores.energy_errors_wh
    hover = scores.hover_errors_w
    data["max_abs_energy_error_wh"] = round(
        max((abs(v) for v in energy), default=0.0), 3
    )
    data["max_abs_hover_error_w"] = round(max((abs(v) for v in hover), default=0.0), 3)
    del data["energy_errors_wh"]
    del data["hover_errors_w"]
    return data


def _emit(text: str) -> None:
    """Write one line of output.

    A single place the linter is told about, rather than a noqa on every call:
    this is a CLI and its stdout is the deliverable.
    """
    print(text)  # noqa: T201


def _select_providers(provider: str | None, track: str | None) -> list[Provider]:
    """Return the providers to run.

    With no --provider, the two offline controls run, so CI and a reviewer
    without an endpoint still get a complete check of the harness. A real
    model is only reached when --provider openai is passed and the
    SUAS_EVAL_* environment is set.
    """
    if provider is None:
        chosen: list[Provider] = [OracleProvider(), ConstantPowerProvider()]
    elif provider == "oracle":
        chosen = [OracleProvider()]
    elif provider == "constant_power":
        chosen = [ConstantPowerProvider()]
    elif provider == "openai":
        endpoint = load_endpoint()
        tracks = [track] if track else ["no_tools", "calculator_tool"]
        chosen = [OpenAICompatibleProvider(endpoint, track=item) for item in tracks]
    else:
        raise SystemExit(f"unknown provider: {provider}")
    if track and provider != "openai":
        chosen = [item for item in chosen if item.track == track]
        if not chosen:
            raise SystemExit(f"provider {provider} does not offer track {track}")
    return chosen


def result_filename(report: dict[str, Any]) -> str:
    """Return a filename that can hold both tracks of the same provider."""
    return f"{report['provider']}.{report['track']}.json"


def main() -> int:
    """Run every selected provider and print or write the results."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="write eval/results/<date>/"
    )
    parser.add_argument(
        "--provider",
        choices=("oracle", "constant_power", "openai"),
        default=None,
        help="default: the two offline controls, which do not touch the network",
    )
    parser.add_argument(
        "--track", choices=("no_tools", "calculator_tool"), default=None
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="score only the first N fixtures"
    )
    parsed = parser.parse_args()

    fixtures = load_fixtures()
    if parsed.limit is not None:
        fixtures = fixtures[: parsed.limit]
    providers = _select_providers(parsed.provider, parsed.track)
    reports = [run_provider(provider, fixtures) for provider in providers]
    if parsed.provider == "openai":
        endpoint = load_endpoint()
        for report in reports:
            report["run"] = endpoint_metadata(
                endpoint, wall_time_s=report["wall_time_s"]
            )

    for report in reports:
        _emit(json.dumps(report, indent=2))

    if parsed.write:
        stamp = datetime.now(UTC).strftime("%Y-%m-%d")
        target = RESULTS / stamp
        target.mkdir(parents=True, exist_ok=True)
        for report in reports:
            path = target / result_filename(report)
            path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            _emit(f"wrote {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
