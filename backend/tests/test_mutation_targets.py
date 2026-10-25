"""Tests for scripts/mutation_targets.py, which picks what the mutation job mutates."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

_BACKEND = Path(__file__).resolve().parent.parent
_SCRIPT = _BACKEND / "scripts" / "mutation_targets.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mutation_targets", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


targets = _load()


def test_a_pull_request_mutates_only_the_backend_source_it_changed() -> None:
    changed = [
        "backend/suas/calculations/battery.py",
        "backend/suas/api/routes.py",
        "backend/tests/test_battery.py",
        "backend/scripts/ub_gate.py",
        "frontend/src/lib/geo.ts",
        "docs/engineering-practices.md",
        "backend/suas/calculations/__init__.py",
    ]
    assert targets.select(changed, _BACKEND) == [
        "suas/api/routes.py",
        "suas/calculations/battery.py",
    ]


def test_a_deleted_file_is_not_a_target() -> None:
    assert targets.select(["backend/suas/no_such_module.py"], _BACKEND) == []


def test_changing_the_selector_itself_mutates_the_safety_core() -> None:
    """So the pull request that edits the job proves the job, not an empty run."""
    selected = targets.select(["backend/scripts/mutation_targets.py"], _BACKEND)
    assert selected == targets.safety_core(_BACKEND)


def test_the_safety_core_is_the_calculators_the_seal_and_the_screener() -> None:
    core = targets.safety_core(_BACKEND)
    assert "suas/calculations/assessment.py" in core
    assert "suas/calculations/gate.py" in core
    assert "suas/graph/seal.py" in core
    assert "suas/rag/screening.py" in core
    assert all(path.endswith(".py") and not path.endswith("__init__.py") for path in core)
    assert all((_BACKEND / path).is_file() for path in core)


def test_the_cli_reads_changed_paths_and_prints_one_target_per_line(tmp_path: Path) -> None:
    changed = tmp_path / "changed.txt"
    changed.write_text("backend/suas/graph/seal.py\nREADME.md\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(_SCRIPT), "--changed", str(changed)],
        capture_output=True,
        text=True,
        check=True,
        cwd=_BACKEND,
    )
    assert result.stdout == "suas/graph/seal.py\n"


def test_the_cli_without_a_change_list_prints_the_safety_core() -> None:
    result = subprocess.run(
        [sys.executable, str(_SCRIPT)], capture_output=True, text=True, check=True, cwd=_BACKEND
    )
    assert result.stdout.splitlines() == targets.safety_core(_BACKEND)
