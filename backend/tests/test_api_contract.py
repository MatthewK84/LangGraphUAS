"""The public API's shape is frozen, so a removed field fails CI (#115).

``test_api.py`` covers behaviour, not shape: removing a field from the
assessment broke the dashboard and passed. ``tests/fixtures/api_contract.json``
records, for ``/api/plan``, ``/api/plan/{thread_id}/ack`` and ``/api/replan``,
every response field and its types and every request field and which are
required, all from the app's own OpenAPI document. A change breaks the contract
when a response field disappears or can take a new type (null included), or a
request gains a required field or loses one. Adding an optional field does not.
"""

import copy
import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

from suas.main import create_app

_BACKEND = Path(__file__).resolve().parents[1]
_SCRIPT = _BACKEND / "scripts" / "api_contract.py"
_FROZEN = _BACKEND / "tests" / "fixtures" / "api_contract.json"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("api_contract", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract = _load()


@pytest.fixture
def spec() -> dict[str, Any]:
    return copy.deepcopy(create_app().openapi())


def _frozen() -> dict[str, Any]:
    return dict(json.loads(_FROZEN.read_text()))


def _schemas(spec: dict[str, Any]) -> dict[str, Any]:
    return dict(spec["components"]["schemas"])


def test_the_api_keeps_its_frozen_contract(spec: dict[str, Any]) -> None:
    breaks = contract.breaking_changes(_frozen(), contract.extract(spec))
    assert breaks == [], "\n".join(breaks)


def test_the_contract_covers_the_three_planning_endpoints() -> None:
    assert set(_frozen()) == {
        "POST /api/plan",
        "POST /api/plan/{thread_id}/ack",
        "POST /api/replan",
    }
    response = _frozen()["POST /api/plan"]["response"]
    assert "assessment.decision" in response
    assert "assessment.blockers[]" in response


def test_removing_a_field_from_the_assessment_breaks_it(spec: dict[str, Any]) -> None:
    del _schemas(spec)["DeterministicAssessment"]["properties"]["decision"]

    breaks = contract.breaking_changes(_frozen(), contract.extract(spec))

    assert "POST /api/plan response: assessment.decision was removed" in breaks
    assert "POST /api/plan/{thread_id}/ack response: assessment.decision was removed" in breaks


def test_adding_an_optional_field_does_not(spec: dict[str, Any]) -> None:
    _schemas(spec)["DeterministicAssessment"]["properties"]["note"] = {"type": "string"}
    _schemas(spec)["MissionRequest"]["properties"]["tag"] = {"type": "string"}

    assert contract.breaking_changes(_frozen(), contract.extract(spec)) == []


def test_a_response_field_that_can_now_be_null_breaks_it(spec: dict[str, Any]) -> None:
    schema = _schemas(spec)["PlanResponse"]["properties"]
    schema["thread_id"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}

    breaks = contract.breaking_changes(_frozen(), contract.extract(spec))

    assert "POST /api/plan response: thread_id can now be null" in breaks


def test_a_new_required_request_field_breaks_it(spec: dict[str, Any]) -> None:
    request = _schemas(spec)["MissionRequest"]
    request["properties"]["operator_note"] = {"type": "string"}
    request["required"] = [*request.get("required", []), "operator_note"]

    breaks = contract.breaking_changes(_frozen(), contract.extract(spec))

    assert "POST /api/plan request: operator_note is newly required" in breaks


def test_a_removed_request_field_breaks_it(spec: dict[str, Any]) -> None:
    del _schemas(spec)["MissionRequest"]["properties"]["payload_id"]

    breaks = contract.breaking_changes(_frozen(), contract.extract(spec))

    assert "POST /api/plan request: payload_id was removed" in breaks


def test_the_failure_names_the_regeneration_command(spec: dict[str, Any]) -> None:
    del _schemas(spec)["PlanResponse"]["properties"]["report"]
    message = contract.report(contract.breaking_changes(_frozen(), contract.extract(spec)))
    assert "python scripts/api_contract.py --write" in message
