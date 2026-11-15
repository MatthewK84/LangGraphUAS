"""One published failure trace must be reproducible from committed results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TRACE_STEM = "pp-01-qwen2.5-7b-instruct.no_tools.2026-11-14"
TRACE_JSON = ROOT / "eval" / "traces" / f"{TRACE_STEM}.json"
TRACE_MD = ROOT / "eval" / "traces" / f"{TRACE_STEM}.md"
RESULTS_14 = ROOT / "eval" / "results" / "2026-11-14" / "qwen2.5-7b-instruct.no_tools.json"
RESULTS_15 = ROOT / "eval" / "results" / "2026-11-15" / "qwen2.5-7b-instruct.no_tools.json"
README = ROOT / "README.md"
FIXTURE_ID = "pp-01"


def _case(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    cases = payload.get("cases", [payload])
    for case in cases:
        if case["fixture_id"] == FIXTURE_ID:
            return case
    raise AssertionError(f"{FIXTURE_ID} missing from {path}")


def test_the_published_json_is_the_unedited_2026_11_14_case() -> None:
    published = json.loads(TRACE_JSON.read_text(encoding="utf-8"))
    assert published == _case(RESULTS_14)


def test_the_writeup_quotes_the_committed_2026_11_14_numbers() -> None:
    case = _case(RESULTS_14)
    text = TRACE_MD.read_text(encoding="utf-8")
    answer = case["answer"]
    assert "eval/results/2026-11-14/qwen2.5-7b-instruct.no_tools.json" in text
    assert case["expected_decision"] in text
    assert case["expected_mode"] in text
    assert f'"{answer["decision"]}"' in text or f"{answer['decision']}" in text
    assert answer["mode"] in text
    assert "225.7" in text
    assert "unsafe_go" in text
    # The structured invention was not flagged: the prose has no 225.7.
    assert "invented_number" in text


def test_the_writeup_shows_the_2026_11_15_override_from_committed_results() -> None:
    case = _case(RESULTS_15)
    text = TRACE_MD.read_text(encoding="utf-8")
    answer = case["answer"]
    assert "eval/results/2026-11-15/qwen2.5-7b-instruct.no_tools.json" in text
    assert answer["decision"] in text
    assert answer["mode"] in text
    assert "477.08" in text
    assert "123.57" in text
    assert case["narrative_source"] in text


def test_published_artifacts_do_not_include_fixture_coordinates() -> None:
    blob = TRACE_JSON.read_text(encoding="utf-8") + TRACE_MD.read_text(encoding="utf-8")
    assert "39.7392" not in blob
    assert "-104.9903" not in blob
    assert "latitude" not in blob
    assert "longitude" not in blob


def test_readme_links_the_failure_trace() -> None:
    text = README.read_text(encoding="utf-8")
    relative = f"eval/traces/{TRACE_STEM}.md"
    assert relative in text
    opening = text.split("\n## Contents\n", 1)[0]
    assert relative in opening
