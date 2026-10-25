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
