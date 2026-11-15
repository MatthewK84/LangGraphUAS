"""An OpenAI-compatible provider for the mission eval pack.

The endpoint, model, temperature and seed come from the environment
(``SUAS_EVAL_*``), never from hardcoded hosts or model names. This is how a
local llama.cpp or Ollama server is wired in, and how a remote OpenAI-compatible
API would be too.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Final

import httpx

from suas.calculations.assessment import assess_mission, build_assessment
from suas.db.seed import load_rows
from suas.eval.mission_scoring import MissionFixture, ModelAnswer
from suas.graph.override import apply_sealed_override
from suas.graph.seal import ground_narrative
from suas.schemas.assessment import AssessmentMode, DeterministicAssessment
from suas.schemas.brief import brief_response_format
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import Calculations, WeatherReading

_DEFAULT_TEMPERATURE: Final[float] = 0.0
_DEFAULT_SEED: Final[int] = 42
_DEFAULT_TIMEOUT_S: Final[float] = 180.0
_JSON_FENCE: Final[re.Pattern[str]] = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_FIRST_OBJECT: Final[re.Pattern[str]] = re.compile(r"\{.*\}", re.DOTALL)

ASSESS_TOOL: Final[dict[str, Any]] = {
    "type": "function",
    "function": {
        "name": "assess_mission",
        "description": (
            "Run the deterministic mission calculator on the current fixture "
            "and return the sealed assessment (decision, mode, blockers, "
            "hover power, residual energy). Figures from this tool are "
            "authoritative."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
}

_SYSTEM_NO_TOOLS: Final[str] = (
    "You are writing a short safety-officer narrative for a small UAS mission. "
    "The deterministic calculator has already run; its sealed decision, mode, "
    "and figures are authoritative and will be used as the scored answer "
    "regardless of what you write. Do not invent a live weather feed or a "
    "Blue UAS clearance. Reply with a single JSON object with keys "
    "brief_markdown (the only free-text field), suggested_contingencies "
    "(a list of short strings), and cited_chunk_ids (a list of strings). "
    "No other keys. No other text."
)

_SYSTEM_CALCULATOR: Final[str] = (
    "You are writing a short safety-officer narrative for a small UAS mission. "
    "The deterministic calculator has already run in code; its sealed "
    "decision, mode, and figures are authoritative and will be used as the "
    "scored answer regardless of what you write. You may call the "
    "assess_mission tool to inspect that sealed result. After any tool "
    "result, reply with a single JSON object with keys brief_markdown "
    "(the only free-text field), suggested_contingencies (a list of short "
    "strings), and cited_chunk_ids (a list of strings). Do not invent "
    "numbers that are not in the tool result or the prompt. No other keys. "
    "No other text."
)


@dataclass(frozen=True)
class EvalEndpoint:
    """How to reach an OpenAI-compatible chat endpoint."""

    base_url: str
    model: str
    api_key: str
    temperature: float
    seed: int
    timeout_s: float
    provider_name: str
    quantization: str = ""
    runtime: str = ""
    hardware: str = ""
    hf_repo: str = ""
    filename: str = ""
    sha256: str = ""


def load_endpoint(env: dict[str, str] | None = None) -> EvalEndpoint:
    """Return the configured endpoint, or raise if the required values are missing."""
    source = env if env is not None else os.environ
    base = source.get("SUAS_EVAL_BASE_URL", "").strip().rstrip("/")
    model = source.get("SUAS_EVAL_MODEL", "").strip()
    if not base or not model:
        raise ValueError(
            "SUAS_EVAL_BASE_URL and SUAS_EVAL_MODEL must be set to run an "
            "OpenAI-compatible provider (for example a local llama.cpp server)."
        )
    # Temperature is pinned at 0. A non-zero env value is ignored rather
    # than negotiated, because sampling is not part of this measurement.
    temperature = _DEFAULT_TEMPERATURE
    seed = int(source.get("SUAS_EVAL_SEED", str(_DEFAULT_SEED)))
    timeout_s = float(source.get("SUAS_EVAL_TIMEOUT_S", str(_DEFAULT_TIMEOUT_S)))
    name = source.get("SUAS_EVAL_PROVIDER_NAME", "").strip() or _slug(model)
    return EvalEndpoint(
        base_url=base,
        model=model,
        api_key=source.get("SUAS_EVAL_API_KEY", "").strip() or "local",
        temperature=temperature,
        seed=seed,
        timeout_s=timeout_s,
        provider_name=name,
        quantization=source.get("SUAS_EVAL_QUANTIZATION", "").strip(),
        runtime=source.get("SUAS_EVAL_RUNTIME", "").strip(),
        hardware=source.get("SUAS_EVAL_HARDWARE", "").strip(),
        hf_repo=source.get("SUAS_EVAL_HF_REPO", "").strip(),
        filename=source.get("SUAS_EVAL_FILENAME", "").strip(),
        sha256=source.get("SUAS_EVAL_SHA256", "").strip(),
    )


def default_temperature() -> float:
    """Return the harness default temperature."""
    return _DEFAULT_TEMPERATURE


def default_seed() -> int:
    """Return the harness default sampling seed."""
    return _DEFAULT_SEED


def _slug(model: str) -> str:
    text = model.rsplit("/", 1)[-1].lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-") or "openai"


def extract_json(text: str) -> dict[str, Any] | None:
    """Return the first JSON object in text, or None if none can be parsed."""
    if not text or not text.strip():
        return None
    stripped = text.strip()
    for candidate in (stripped,):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    fenced = _JSON_FENCE.search(stripped)
    if fenced:
        try:
            parsed = json.loads(fenced.group(1))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    bare = _FIRST_OBJECT.search(stripped)
    if bare:
        try:
            parsed = json.loads(bare.group(0))
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return None


def parse_model_answer(text: str) -> ModelAnswer:
    """Turn a model completion into a ModelAnswer, keeping the raw prose."""
    payload = extract_json(text)
    if payload is None:
        return ModelAnswer(decision="unknown", mode="advisory", prose=text)
    decision = _normalise_decision(payload.get("decision"))
    mode = _normalise_mode(payload.get("mode"))
    return ModelAnswer(
        decision=decision,
        mode=mode,
        hover_power_w=_optional_float(payload.get("hover_power_w")),
        residual_wh=_optional_float(payload.get("residual_wh")),
        prose=_narrative(payload, text),
    )


def _narrative(payload: dict[str, Any], fallback: str) -> str:
    """Return the model's free-text field, preferring the structured brief key."""
    for key in ("brief_markdown", "prose", "narrative"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return fallback


def _normalise_decision(raw: object) -> str:
    text = str(raw or "unknown").strip().lower().replace("-", "_").replace(" ", "_")
    if text in {"go"}:
        return "go"
    if text in {"no_go", "nogo", "no"}:
        return "no_go"
    return "unknown"


def _normalise_mode(raw: object) -> str:
    text = str(raw or "advisory").strip().lower()
    if text == "operational":
        return "operational"
    return "advisory"


def _optional_float(raw: object) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def mission_prompt(fixture: MissionFixture, aircraft: Aircraft, payload: Payload) -> str:
    """Return the user prompt describing one fixture, without expected answers."""
    return (
        f"Fixture: {fixture.fixture_id}. Trap type (for your information, not "
        f"a hint about the answer): {fixture.trap}.\n"
        f"Airframe: {aircraft.id} ({aircraft.name}). "
        f"weight_kg={aircraft.weight_kg}, max_payload_kg={aircraft.max_payload_kg}, "
        f"battery_wh={aircraft.battery_wh}, hover_power_w={aircraft.hover_power_w}, "
        f"cruise_power_w={aircraft.cruise_power_w}, "
        f"cruise_speed_mps={aircraft.cruise_speed_mps}, "
        f"max_wind_mps={aircraft.max_wind_mps}, "
        f"min_temp_c={aircraft.min_temp_c}, max_temp_c={aircraft.max_temp_c}, "
        f"pack_min_takeoff_c={aircraft.pack_min_takeoff_c}.\n"
        f"Payload: {payload.id} ({payload.name}). "
        f"weight_kg={payload.weight_kg}, power_draw_w={payload.power_draw_w}.\n"
        f"Mission: {json.dumps(fixture.params)}.\n"
        f"Weather: {json.dumps(fixture.weather)}.\n"
        "The hover_power_w and cruise_power_w figures above are the reference "
        "values stored for this airframe."
    )


def sealed_prompt_block(assessment: DeterministicAssessment, calculations: Calculations) -> str:
    """Return the already-computed sealed figures the narrative may use."""
    return (
        "The deterministic calculator has already run. Its sealed result is "
        "authoritative and will be used as the scored decision, mode, and "
        "figures, regardless of what you write.\n"
        f"decision={assessment.decision.value}, mode={assessment.mode.value}, "
        f"hover_power_w={calculations.effective_hover_power_w}, "
        f"residual_wh={calculations.battery_check.margin_wh}."
    )


class OpenAICompatibleProvider:
    """A real-model provider talking to an OpenAI-compatible /chat/completions API."""

    def __init__(
        self,
        endpoint: EvalEndpoint,
        *,
        track: str,
        client: httpx.Client | None = None,
    ) -> None:
        if track not in {"no_tools", "calculator_tool"}:
            raise ValueError(f"unsupported track: {track}")
        self.name = endpoint.provider_name
        self.track = track
        self.endpoint = endpoint
        self._client = client
        aircraft = {row["id"]: Aircraft.model_validate(row) for row in load_rows("aircraft.json")}
        payloads = {row["id"]: Payload.model_validate(row) for row in load_rows("payloads.json")}
        self._aircraft = aircraft
        self._payloads = payloads
        self.last_raw: str = ""
        self.last_tool_results: list[dict[str, Any]] = []
        self.last_disagreements: list[dict[str, Any]] = []
        self.last_ungrounded: list[str] = []
        self.last_narrative_source: str = "model"
        self.last_sealed_decision: str = ""
        self._sealed: tuple[DeterministicAssessment, Calculations] | None = None

    def _assess(self, fixture: MissionFixture) -> tuple[DeterministicAssessment, Calculations]:
        """Run the deterministic calculator before any model call."""
        aircraft = self._aircraft[fixture.airframe]
        payload = self._payloads[fixture.payload]
        params = MissionParams.model_validate(fixture.params)
        weather = WeatherReading.model_validate(fixture.weather)
        calculations = assess_mission(
            aircraft=aircraft, payload=payload, params=params, weather=weather
        )
        assessment = build_assessment(
            calculations=calculations,
            requested_mode=AssessmentMode.ADVISORY,
            weather=weather,
            aircraft=aircraft,
            payload=payload,
            inputs={"fixture": fixture.fixture_id},
        )
        return assessment, calculations

    def answer(self, fixture: MissionFixture) -> ModelAnswer:
        """Return the sealed answer, with the model's narrative attached.

        The calculator always runs first. The model's JSON may propose a
        decision, mode, or figures; those are logged as disagreements and
        overwritten. Only brief_markdown (or legacy prose) is kept as prose.
        """
        aircraft = self._aircraft[fixture.airframe]
        payload = self._payloads[fixture.payload]
        assessment, calculations = self._assess(fixture)
        self._sealed = (assessment, calculations)
        self.last_sealed_decision = assessment.decision.value
        user = (
            mission_prompt(fixture, aircraft, payload)
            + "\n"
            + sealed_prompt_block(assessment, calculations)
        )
        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": _SYSTEM_CALCULATOR
                if self.track == "calculator_tool"
                else _SYSTEM_NO_TOOLS,
            },
            {"role": "user", "content": user},
        ]
        self.last_tool_results = []
        raw = self._complete(messages, fixture)
        self.last_raw = raw
        parsed = parse_model_answer(raw)
        result = apply_sealed_override(assessment, calculations, parsed, narrative=parsed.prose)
        self.last_disagreements = list(result.disagreements)
        published, invented = ground_narrative(result.answer.prose, assessment, calculations)
        self.last_ungrounded = invented
        self.last_narrative_source = "deterministic" if invented else "model"
        if not invented:
            return result.answer
        return ModelAnswer(
            decision=result.answer.decision,
            mode=result.answer.mode,
            hover_power_w=result.answer.hover_power_w,
            residual_wh=result.answer.residual_wh,
            prose=published,
        )

    def _complete(self, messages: list[dict[str, Any]], fixture: MissionFixture) -> str:
        """Run the chat loop, dispatching tool calls when the track allows them."""
        client = self._client or httpx.Client(timeout=self.endpoint.timeout_s)
        owns = self._client is None
        try:
            for _ in range(4):
                body: dict[str, Any] = {
                    "model": self.endpoint.model,
                    "messages": messages,
                    "temperature": self.endpoint.temperature,
                    "seed": self.endpoint.seed,
                    "response_format": brief_response_format(),
                }
                if self.track == "calculator_tool":
                    body["tools"] = [ASSESS_TOOL]
                response = client.post(
                    self._chat_url(),
                    headers={
                        "Authorization": f"Bearer {self.endpoint.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
                response.raise_for_status()
                message = response.json()["choices"][0]["message"]
                tool_calls = message.get("tool_calls") or []
                if tool_calls and self.track == "calculator_tool":
                    messages.append(
                        {
                            "role": "assistant",
                            "content": message.get("content") or "",
                            "tool_calls": tool_calls,
                        }
                    )
                    for call in tool_calls:
                        result = self._run_tool(call, fixture)
                        self.last_tool_results.append(result)
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call.get("id", ""),
                                "content": json.dumps(result),
                            }
                        )
                    continue
                return str(message.get("content") or "")
            return ""
        finally:
            if owns:
                client.close()

    def _chat_url(self) -> str:
        base = self.endpoint.base_url
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _run_tool(self, call: dict[str, Any], fixture: MissionFixture) -> dict[str, Any]:
        name = (call.get("function") or {}).get("name", "")
        if name != "assess_mission":
            return {"error": f"unknown tool: {name}"}
        if self._sealed is None:
            self._sealed = self._assess(fixture)
        assessment, calculations = self._sealed
        return {
            "decision": assessment.decision.value,
            "mode": assessment.mode.value,
            "blockers": [blocker.value for blocker in assessment.blockers],
            "hover_power_w": calculations.effective_hover_power_w,
            "residual_wh": calculations.battery_check.margin_wh,
        }


def endpoint_metadata(endpoint: EvalEndpoint, *, wall_time_s: float) -> dict[str, Any]:
    """Return the run metadata that should be stored with a results file."""
    return {
        "model": endpoint.model,
        "hf_repo": endpoint.hf_repo,
        "filename": endpoint.filename,
        "sha256": endpoint.sha256,
        "quantization": endpoint.quantization,
        "runtime": endpoint.runtime,
        "hardware": endpoint.hardware,
        "temperature": endpoint.temperature,
        "seed": endpoint.seed,
        "base_url_configured": True,
        "wall_time_s": round(wall_time_s, 3),
    }
