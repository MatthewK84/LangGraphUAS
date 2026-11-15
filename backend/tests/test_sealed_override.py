"""The sealed calculator result, not the model, owns decision, mode, and numbers."""

from __future__ import annotations

import json
import sys

import httpx
import pytest

from suas.calculations.assessment import assess_mission, build_assessment
from suas.eval.mission_scoring import ModelAnswer, unsafe_go
from suas.graph.override import apply_sealed_override
from suas.schemas.assessment import AssessmentMode
from suas.schemas.brief import brief_response_format
from suas.schemas.requests import MissionParams
from suas.schemas.responses import WeatherReading
from tests.test_eval_openai_provider import (  # reuse the eval fixture and endpoint
    REPO_ROOT,
    _endpoint,
)

sys.path.insert(0, str(REPO_ROOT / "eval"))
from openai_provider import OpenAICompatibleProvider, load_endpoint


def _catalog_row(kind: str, ident: str):
    from suas.db.seed import load_rows
    from suas.schemas.domain import Aircraft as Air
    from suas.schemas.domain import Payload as Pay

    cls = Air if kind == "aircraft" else Pay
    filename = "aircraft.json" if kind == "aircraft" else "payloads.json"
    for row in load_rows(filename):
        if row["id"] == ident:
            return cls.model_validate(row)
    raise LookupError(ident)


def _pp01_sealed() -> tuple:
    aircraft = _catalog_row("aircraft", "Freefly_Astro_Max")
    payload = _catalog_row("payload", "None")
    params = MissionParams(
        distance_m=3000.0,
        hover_time_s=300.0,
        target_altitude_m=100.0,
        elevation_m=0.0,
        latitude=39.7392,
        longitude=-104.9903,
    )
    weather = WeatherReading(
        temperature_c=5.0,
        wind_speed_mps=3.0,
        wind_gust_mps=4.0,
        wind_direction=180.0,
        humidity_percent=45.0,
        conditions="clear",
        source="live",
        fetched_at="2026-01-01T00:00:00Z",
    )
    calculations = assess_mission(
        aircraft=aircraft, payload=payload, params=params, weather=weather
    )
    assessment = build_assessment(
        calculations=calculations,
        requested_mode=AssessmentMode.ADVISORY,
        weather=weather,
        aircraft=aircraft,
        payload=payload,
        inputs={"fixture": "pp-01"},
    )
    return assessment, calculations


def test_a_model_go_cannot_override_a_sealed_no_go() -> None:
    assessment, calculations = _pp01_sealed()
    assert assessment.decision.value == "no_go"
    model = ModelAnswer(
        decision="go",
        mode="operational",
        hover_power_w=1.0,
        residual_wh=225.7,
        prose="Within temperature and wind limits, residual 225.7 Wh.",
    )
    result = apply_sealed_override(assessment, calculations, model)
    assert result.answer.decision == "no_go"
    assert result.answer.mode == assessment.mode.value
    assert result.answer.hover_power_w == calculations.effective_hover_power_w
    assert result.answer.residual_wh == calculations.battery_check.margin_wh
    assert result.answer.prose == model.prose
    fields = {item["field"] for item in result.disagreements}
    assert fields == {"decision", "mode", "hover_power_w", "residual_wh"}
    assert not unsafe_go(
        __import__("suas.eval.mission_scoring", fromlist=["MissionFixture"]).MissionFixture(
            fixture_id="pp-01",
            trap="pack_procedure",
            airframe="Freefly_Astro_Max",
            payload="None",
            params={},
            weather={},
            expected_decision="no_go",
            expected_mode="advisory",
            expected_residual_wh_range=(71.39, 73.39),
            expected_hover_power_w=979.71,
            calculator_version="1.9.0",
        ),
        result.answer,
    )


def test_omitted_numerics_are_not_recorded_as_disagreements() -> None:
    assessment, calculations = _pp01_sealed()
    model = ModelAnswer(decision="unknown", mode="advisory", prose="A brief.")
    result = apply_sealed_override(assessment, calculations, model)
    fields = {item["field"] for item in result.disagreements}
    assert "hover_power_w" not in fields
    assert "residual_wh" not in fields
    assert "decision" in fields
    assert result.answer.hover_power_w == calculations.effective_hover_power_w


def test_the_brief_schema_has_no_decision_mode_or_numeric_field() -> None:
    payload = brief_response_format()
    schema = payload["json_schema"]["schema"]
    properties = schema["properties"]
    assert set(properties) == {
        "brief_markdown",
        "suggested_contingencies",
        "cited_chunk_ids",
    }
    assert schema.get("additionalProperties") is False
    banned = {
        "decision",
        "mode",
        "hover_power_w",
        "residual_wh",
        "is_viable",
        "energy_required_wh",
    }
    assert banned.isdisjoint(properties)


def _hostile_no_tools_handler(payloads: list[dict]) -> httpx.MockTransport:
    def on_request(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        payloads.append(body)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "decision": "go",
                                    "mode": "operational",
                                    "hover_power_w": 1.0,
                                    "residual_wh": 225.7,
                                    "brief_markdown": "Within limits; residual 225.7 Wh.",
                                }
                            ),
                        }
                    }
                ]
            },
        )

    return httpx.MockTransport(on_request)


def _pp01_fixture():
    from suas.eval.mission_scoring import MissionFixture

    return MissionFixture(
        fixture_id="pp-01",
        trap="pack_procedure",
        airframe="Freefly_Astro_Max",
        payload="None",
        params={
            "distance_m": 3000.0,
            "hover_time_s": 300.0,
            "target_altitude_m": 100.0,
            "elevation_m": 0.0,
            "latitude": 39.7392,
            "longitude": -104.9903,
        },
        weather={
            "temperature_c": 5.0,
            "wind_speed_mps": 3.0,
            "wind_gust_mps": 4.0,
            "wind_direction": 180.0,
            "humidity_percent": 45.0,
            "conditions": "clear",
            "source": "live",
            "fetched_at": "2026-01-01T00:00:00Z",
        },
        expected_decision="no_go",
        expected_mode="advisory",
        expected_residual_wh_range=(71.39, 73.39),
        expected_hover_power_w=979.71,
        calculator_version="1.9.0",
    )


@pytest.mark.parametrize("track", ["no_tools", "calculator_tool"])
def test_eval_provider_overrides_a_hostile_go_on_both_tracks(track: str) -> None:
    posted: list[dict] = []
    client = httpx.Client(transport=_hostile_no_tools_handler(posted))
    provider = OpenAICompatibleProvider(_endpoint(), track=track, client=client)
    answer = provider.answer(_pp01_fixture())
    assert answer.decision == "no_go"
    assert answer.mode == "advisory"
    assert answer.residual_wh != 225.7
    assert not unsafe_go(_pp01_fixture(), answer)
    assert provider.last_disagreements
    assert any(item["field"] == "decision" for item in provider.last_disagreements)
    body = posted[0]
    assert body["temperature"] == 0.0
    assert body["seed"] == 42
    assert body.get("response_format", {}).get("type") == "json_schema"
    if track == "no_tools":
        assert "tools" not in body
    else:
        # First request may be the tool call or the schema-constrained brief;
        # the calculator has already run in code either way.
        assert provider.last_sealed_decision == "no_go"


def test_load_endpoint_pins_temperature_to_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUAS_EVAL_BASE_URL", "http://127.0.0.1:8080/v1")
    monkeypatch.setenv("SUAS_EVAL_MODEL", "local")
    monkeypatch.setenv("SUAS_EVAL_TEMPERATURE", "0.8")
    monkeypatch.setenv("SUAS_EVAL_SEED", "42")
    monkeypatch.setenv("SUAS_EVAL_SHA256", "abc123")
    endpoint = load_endpoint()
    assert endpoint.temperature == 0.0
    assert endpoint.seed == 42
    assert endpoint.sha256 == "abc123"


def test_report_service_pins_temperature_seed_and_optional_base_url() -> None:
    from suas.config import Settings
    from suas.services.llm import ReportService

    service = ReportService(
        Settings(
            openai_api_key="sk-test",
            openai_base_url="http://127.0.0.1:8080/v1",
            llm_seed=42,
            llm_model_sha256="abc123",
        )
    )
    model = service._build_model()
    assert model is not None
    # langchain stores some constructor args on the model; temperature is always 0.
    assert float(model.temperature) == 0.0
    assert int(model.seed) == 42
    assert "127.0.0.1:8080" in str(model.openai_api_base or model.base_url)
