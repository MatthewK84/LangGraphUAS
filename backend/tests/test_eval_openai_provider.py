"""The eval harness can talk to an OpenAI-compatible endpoint configured by env."""

from __future__ import annotations

import json

# eval/ sits next to backend/; tests import the runner the same way test_mission_eval does.
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

from suas.eval.mission_scoring import MissionFixture, unsafe_go

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "eval"))

from openai_provider import (  # noqa: E402
    EvalEndpoint,
    OpenAICompatibleProvider,
    default_seed,
    default_temperature,
    extract_json,
    load_endpoint,
    parse_model_answer,
)


def _endpoint(**overrides: Any) -> EvalEndpoint:
    base = {
        "base_url": "http://eval.test/v1",
        "model": "local-model",
        "api_key": "local",
        "temperature": 0.0,
        "seed": 42,
        "timeout_s": 5.0,
        "provider_name": "local-model",
    }
    base.update(overrides)
    return EvalEndpoint(**base)


def _fixture() -> MissionFixture:
    return MissionFixture(
        fixture_id="ps-01",
        trap="payload_scale",
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
            "temperature_c": 18.0,
            "wind_speed_mps": 3.0,
            "wind_gust_mps": 4.0,
            "wind_direction": 180.0,
            "humidity_percent": 45.0,
            "conditions": "clear",
            "source": "live",
            "fetched_at": "2026-01-01T00:00:00Z",
        },
        expected_decision="go",
        expected_mode="advisory",
        expected_residual_wh_range=(106.47, 108.47),
        expected_hover_power_w=1002.09,
        calculator_version="1.9.0",
    )


def test_the_harness_default_temperature_is_zero() -> None:
    assert default_temperature() == 0.0
    assert default_seed() == 42


def test_load_endpoint_refuses_to_guess_a_host_or_model() -> None:
    with pytest.raises(ValueError, match="SUAS_EVAL_BASE_URL"):
        load_endpoint({})
    with pytest.raises(ValueError, match="SUAS_EVAL_MODEL"):
        load_endpoint({"SUAS_EVAL_BASE_URL": "http://127.0.0.1:8080/v1"})


def test_load_endpoint_reads_the_endpoint_from_the_environment() -> None:
    endpoint = load_endpoint(
        {
            "SUAS_EVAL_BASE_URL": "http://127.0.0.1:8080/v1/",
            "SUAS_EVAL_MODEL": "Qwen2.5-7B-Instruct",
            "SUAS_EVAL_PROVIDER_NAME": "qwen2.5-7b-instruct",
            "SUAS_EVAL_QUANTIZATION": "Q4_K_M",
            "SUAS_EVAL_SEED": "7",
        }
    )
    assert endpoint.base_url == "http://127.0.0.1:8080/v1"
    assert endpoint.model == "Qwen2.5-7B-Instruct"
    assert endpoint.provider_name == "qwen2.5-7b-instruct"
    assert endpoint.quantization == "Q4_K_M"
    assert endpoint.temperature == 0.0
    assert endpoint.seed == 7


def test_extract_json_accepts_fenced_and_bare_objects() -> None:
    assert extract_json('{"decision": "go"}') == {"decision": "go"}
    assert extract_json('Sure.\n```json\n{"decision": "no_go"}\n```\n') == {"decision": "no_go"}
    assert extract_json("not json") is None


def test_parse_model_answer_keeps_the_prose_and_normalizes_the_decision() -> None:
    answer = parse_model_answer(
        '{"decision": "NO-GO", "mode": "Operational", "hover_power_w": 500, '
        '"residual_wh": null, "prose": "Too windy."}'
    )
    assert answer.decision == "no_go"
    assert answer.mode == "operational"
    assert answer.hover_power_w == 500.0
    assert answer.residual_wh is None
    assert answer.prose == "Too windy."


def test_unparseable_output_is_an_unknown_decision_not_a_guessed_go() -> None:
    answer = parse_model_answer("I think it is probably fine.")
    assert answer.decision == "unknown"
    assert answer.mode == "advisory"
    assert answer.prose == "I think it is probably fine."
    fixture = _fixture()
    fixture_no = MissionFixture(
        fixture_id=fixture.fixture_id,
        trap=fixture.trap,
        airframe=fixture.airframe,
        payload=fixture.payload,
        params=fixture.params,
        weather=fixture.weather,
        expected_decision="no_go",
        expected_mode=fixture.expected_mode,
        expected_residual_wh_range=fixture.expected_residual_wh_range,
        expected_hover_power_w=fixture.expected_hover_power_w,
        calculator_version=fixture.calculator_version,
    )
    assert not unsafe_go(fixture_no, answer)


def _handler(payloads: list[dict[str, Any]]) -> httpx.MockTransport:
    def on_request(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content.decode("utf-8"))
        payloads.append(body)
        if body.get("tools") and len(payloads) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {"name": "assess_mission", "arguments": "{}"},
                                    }
                                ],
                            }
                        }
                    ]
                },
            )
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
                                    "mode": "advisory",
                                    "hover_power_w": 1002.09,
                                    "residual_wh": 159.8,
                                    "prose": "Calculator residual is inside the reserve.",
                                }
                            ),
                        }
                    }
                ]
            },
        )

    return httpx.MockTransport(on_request)


def test_no_tools_track_posts_json_and_does_not_advertise_the_calculator() -> None:
    posted: list[dict[str, Any]] = []
    client = httpx.Client(transport=_handler(posted))
    provider = OpenAICompatibleProvider(_endpoint(), track="no_tools", client=client)
    answer = provider.answer(_fixture())
    assert answer.decision == "go"
    assert "tools" not in posted[0]
    assert posted[0]["temperature"] == 0.0
    assert posted[0]["seed"] == 42
    assert posted[0]["model"] == "local-model"
    assert posted[0]["messages"][0]["role"] == "system"
    # The prompt describes the mission, not the expected decision.
    user = posted[0]["messages"][1]["content"]
    assert "Freefly_Astro_Max" in user
    assert "expected_decision" not in user
    assert "106.47" not in user


def test_calculator_tool_track_runs_the_deterministic_engine_when_called() -> None:
    posted: list[dict[str, Any]] = []
    client = httpx.Client(transport=_handler(posted))
    provider = OpenAICompatibleProvider(_endpoint(), track="calculator_tool", client=client)
    answer = provider.answer(_fixture())
    assert len(posted) == 2
    assert posted[0]["tools"][0]["function"]["name"] == "assess_mission"
    assert provider.last_tool_results
    tool = provider.last_tool_results[0]
    assert tool["decision"] in {"go", "no_go"}
    assert tool["mode"] == "advisory"
    assert isinstance(tool["hover_power_w"], float)
    assert posted[1]["messages"][-1]["role"] == "tool"
    assert answer.decision == "go"
    assert answer.hover_power_w == 1002.09


def test_the_request_goes_to_the_configured_base_url() -> None:
    seen: list[str] = []

    def on_request(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": '{"decision":"no_go","mode":"advisory"}',
                        }
                    }
                ]
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(on_request))
    provider = OpenAICompatibleProvider(
        _endpoint(base_url="http://127.0.0.1:8080/v1"), track="no_tools", client=client
    )
    provider.answer(_fixture())
    assert seen == ["http://127.0.0.1:8080/v1/chat/completions"]


def test_default_selection_is_the_offline_controls() -> None:
    import run as runner

    names = [provider.name for provider in runner._select_providers(None, None)]
    assert names == ["oracle", "constant_power"]


def test_result_filename_keeps_two_tracks_of_one_provider_apart() -> None:
    import run as runner

    assert (
        runner.result_filename({"provider": "qwen", "track": "no_tools"}) == "qwen.no_tools.json"
    )
    assert (
        runner.result_filename({"provider": "qwen", "track": "calculator_tool"})
        == "qwen.calculator_tool.json"
    )


def test_the_leaderboard_does_not_claim_no_model_once_a_real_row_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import build_leaderboard as board

    day = tmp_path / "2026-11-14"
    day.mkdir()
    control = {
        "provider": "oracle",
        "track": "calculator_tool",
        "fixtures": 30,
        "scores": {
            "unsafe_go": 0,
            "missed_go": 0,
            "mode_violation": 0,
            "invented_number": 0,
            "max_abs_hover_error_w": 0.0,
        },
    }
    real = dict(control)
    real["provider"] = "qwen2.5-7b-instruct"
    real["track"] = "no_tools"
    (day / "oracle.calculator_tool.json").write_text(json.dumps(control), encoding="utf-8")
    (day / "qwen.no_tools.json").write_text(json.dumps(real), encoding="utf-8")
    monkeypatch.setattr(board, "RESULTS", tmp_path)
    rendered = board.render()
    assert "No real language model has been measured here." not in rendered
    assert "qwen2.5-7b-instruct" in rendered
    assert "real language model" in rendered
