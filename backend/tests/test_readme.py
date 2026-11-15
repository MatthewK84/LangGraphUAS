"""The README may be restyled, but it must stay true to the repository.

It is the page most people read and the one least often re-checked. These
tests pin the claims it makes that can drift: relative links resolve, the CI
badge is ci.yml on main, the Python badge is the CI matrix, the quality-gates
section names every ci.yml job, the architecture diagram names every graph
node, and the safety language is still there.
"""

import re
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
CI: dict[str, Any] = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())
WORKFLOW = (ROOT / "backend/suas/graph/workflow.py").read_text(encoding="utf-8")


def _section(heading: str) -> str:
    start = README.index(f"\n## {heading}\n")
    end = README.find("\n## ", start + 1)
    return README[start : end if end != -1 else len(README)]


def _relative_targets() -> list[str]:
    markdown = re.findall(r"\]\(([^)\s]+)\)", README)
    html = re.findall(r'(?:src|href)="([^"]+)"', README)
    return [
        t for t in markdown + html if not t.startswith(("http://", "https://", "#", "mailto:"))
    ]


def test_every_relative_link_resolves() -> None:
    targets = _relative_targets()
    assert targets, "expected relative links to docs/"
    missing = [t for t in targets if not (ROOT / t.split("#")[0]).exists()]
    assert missing == []


def test_ci_badge_is_ci_yml_on_main() -> None:
    assert "MatthewK84/LangGraphUAS/ci.yml?branch=main" in README
    assert "actions/workflows/ci.yml?query=branch%3Amain" in README


def test_python_badge_is_the_ci_matrix() -> None:
    versions = CI["jobs"]["backend"]["strategy"]["matrix"]["python-version"]
    badge = re.search(r"img\.shields\.io/badge/python-([^?-]+)-", README)
    assert badge is not None
    assert badge.group(1) == "%20%7C%20".join(versions)


def test_quality_gates_name_every_ci_job() -> None:
    gates = _section("Quality gates")
    missing = [job for job in CI["jobs"] if f"`{job}`" not in gates]
    assert missing == []
    report_only = [line for line in gates.splitlines() if "`mutation`" in line]
    assert any("report-only" in line.lower() for line in report_only)


def test_architecture_diagram_names_every_graph_node() -> None:
    nodes = re.findall(r'add_node\("(\w+)"', WORKFLOW)
    diagram = re.search(r"```mermaid\n(.*?)```", README, re.DOTALL)
    assert diagram is not None
    assert nodes and [n for n in nodes if n not in diagram.group(1)] == []


def test_safety_language_is_kept() -> None:
    for phrase in (
        "not an airspace, NOTAM, or regulatory clearance tool",
        "Never fly on a demo plan",
        "operational mode is unreachable",
        "written by `suas/calculations/` and never by the language model",
    ):
        assert phrase in README


def _opening() -> str:
    return README.split("\n## Contents\n", 1)[0]


def test_the_opening_states_what_it_is_what_it_is_not_and_links_the_eval() -> None:
    """Three equally marked lines decide whether anyone opens the repository."""
    opening = _opening()
    lines = re.findall(
        r'<p align="center"><b>(What it is|What it is not|Eval)\.</b>.*?</p>',
        opening,
        flags=re.DOTALL,
    )
    assert lines == ["What it is", "What it is not", "Eval"], lines
    assert "eval/LEADERBOARD.md" in opening


def test_the_opening_links_a_real_demo_recording() -> None:
    """The README may only link a recording of this app, not a placeholder (#99)."""
    opening = _opening()
    assert "not yet recorded" not in opening
    assert "v0.4.0-eval-demo.webm" in opening


def test_the_opening_avoids_tactics_frequencies_and_procedures() -> None:
    opening = _opening()
    for term in ("MHz", "GHz", "kHz", "frequency", "frequencies", "tactic", "tactics"):
        assert term not in opening, term


def test_the_license_section_disclaims_endorsement_and_authorization() -> None:
    """Programs named in the seed data are reference data, not a clearance."""
    section = re.sub(r"\s+", " ", _section("License")).lower()
    assert "[mit](license)" in section
    assert "not an endorsement" in section or "not endorsement" in section
    assert "flight authorization" in section or "flight authorization" in section
    assert "reference data" in section


def _performance_model() -> str:
    return _section("The performance model")


def test_provenance_links_the_open_durable_ticket_not_a_closed_issue() -> None:
    """The field inventory needs a live home; issue 39 was closed in September 2026."""
    section = _performance_model()
    assert "issues/74" in section
    assert "issues/39" not in section
    assert "CITATIONS.md" in section
    collapsed = re.sub(r"\s+", " ", section).lower()
    assert "durable" in collapsed


def test_the_next_eslint_plugin_stays_enabled_on_next_15() -> None:
    """The plugin stays on; the app itself is now Next 15 and React 19."""
    limitations = _section("Operations and limitations")
    assert "Next.js ESLint plugin is disabled" not in limitations
    collapsed = re.sub(r"\s+", " ", README)
    assert "@next/eslint-plugin-next" in collapsed
    assert "Next.js 15" in collapsed
    assert "React 19" in collapsed
    assert "stays on 14" not in collapsed.lower()
    config = (ROOT / "frontend" / "eslint.config.mjs").read_text(encoding="utf-8")
    assert 'from "@next/eslint-plugin-next"' in config
    assert "recommended" in config
    assert "core-web-vitals" in config
