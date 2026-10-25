"""Tests for scripts/ub_gate.py, the blocking ub-mode check in CI."""

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "ub_gate.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ub_gate", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate = _load()

_CRAP = """CRAP Report
===========
Languages: python

Function                              Namespace                                         CC    Cov%     CRAP
fine                                  pkg.mod                                            3 100.0%      3.0
edge                                  pkg.mod.Klass                                      9 100.0%      9.0
risky                                 pkg.mod                                           10  91.7%     10.1
"""

_SOURCE = '''def get_a(request):
    """A."""
    value = request.a
    return value


def get_b(request):
    """B."""
    value = request.b
    return value


class Holder:
    @property
    def c(self):
        value = self.c_
        return value
'''


def _dry(*pairs: tuple[str, str, str]) -> str:
    return "\n".join(f"DUPLICATE score={score}\n  {a}\n  {b}\n" for score, a, b in pairs)


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(_SOURCE, encoding="utf-8")
    return tmp_path


def test_crap_at_or_over_ten_is_reported_and_under_ten_is_not() -> None:
    assert gate.crap_violations(_CRAP) == ["CRAP 10.1 >= 10: pkg.mod.risky"]


def test_exactly_ten_is_a_violation() -> None:
    row = "f                                     m                                                  4  50.0%     10.0"
    assert gate.crap_violations(row) == ["CRAP 10.0 >= 10: m.f"]


def test_dryer_regions_resolve_to_enclosing_functions(tree: Path) -> None:
    text = _dry(
        ("1.00", "pkg/mod.py:1-4", "pkg/mod.py:7-10"),
        ("0.85", "pkg/mod.py:15-17", "pkg/mod.py:2-4"),
    )
    assert gate.dry_pairs(text, tree) == [
        (1.0, frozenset({"pkg/mod.py::get_a", "pkg/mod.py::get_b"})),
        (0.85, frozenset({"pkg/mod.py::Holder.c", "pkg/mod.py::get_a"})),
    ]


def test_pairs_below_the_limit_are_ignored(tree: Path) -> None:
    assert gate.dry_pairs(_dry(("0.79", "pkg/mod.py:1-4", "pkg/mod.py:7-10")), tree) == []


def test_a_line_outside_any_function_is_named_by_line(tree: Path) -> None:
    assert gate.function_at(tree, "pkg/mod.py", 6) == "pkg/mod.py:6"


def test_allowlisted_groups_allow_every_pair_within_them(tree: Path) -> None:
    groups, errors = gate.load_allowlist(
        "# comment\n\npkg/mod.py::get_a pkg/mod.py::get_b pkg/mod.py::Holder.c  # same shape\n"
    )
    pairs = gate.dry_pairs(
        _dry(
            ("1.00", "pkg/mod.py:1-4", "pkg/mod.py:7-10"),
            ("0.9", "pkg/mod.py:15-17", "pkg/mod.py:7-10"),
        ),
        tree,
    )
    assert errors == []
    assert len(groups) == 1
    assert len(pairs) == 2
    assert gate.dry_violations(pairs, groups) == []


def test_an_unlisted_pair_is_a_violation(tree: Path) -> None:
    pairs = gate.dry_pairs(_dry(("1.00", "pkg/mod.py:1-4", "pkg/mod.py:7-10")), tree)
    assert gate.dry_violations(pairs, []) == [
        "duplicate score=1.00: pkg/mod.py::get_a ~ pkg/mod.py::get_b"
    ]


def test_a_group_matching_nothing_is_stale() -> None:
    groups, _ = gate.load_allowlist("a.py::x a.py::y  # gone\n")
    assert gate.dry_violations([], groups) == ["stale allowlist group: a.py::x a.py::y"]


@pytest.mark.parametrize("line", ["a.py::x a.py::y", "a.py::x  # alone", "a.py::x a.py::y  #   "])
def test_an_entry_without_a_reason_or_partner_is_an_error(line: str) -> None:
    groups, errors = gate.load_allowlist(line)
    assert groups == []
    assert errors == ["allowlist line 1: needs two or more names and a # reason"]


def _run(tree: Path, crap: str, dry: str, allow: str) -> subprocess.CompletedProcess[str]:
    (tree / "crap.txt").write_text(crap, encoding="utf-8")
    (tree / "dry.txt").write_text(dry, encoding="utf-8")
    (tree / "allow.txt").write_text(allow, encoding="utf-8")
    return subprocess.run(
        [
            sys.executable,
            str(_SCRIPT),
            "--crap",
            "crap.txt",
            "--dry",
            "dry.txt",
            "--allowlist",
            "allow.txt",
        ],
        cwd=tree,
        capture_output=True,
        text=True,
        check=False,
    )


def test_main_passes_when_everything_is_within_the_bar(tree: Path) -> None:
    clean = "\n".join(_CRAP.splitlines()[:-1])
    result = _run(
        tree,
        clean,
        _dry(("1.00", "pkg/mod.py:1-4", "pkg/mod.py:7-10")),
        "pkg/mod.py::get_a pkg/mod.py::get_b  # same shape\n",
    )
    assert result.returncode == 0
    assert result.stdout == "ub-mode gate: 0 problem(s), 1 duplicate pair(s) reported\n"


def test_main_fails_and_lists_every_problem(tree: Path) -> None:
    result = _run(tree, _CRAP, _dry(("1.00", "pkg/mod.py:1-4", "pkg/mod.py:7-10")), "bad line\n")
    assert result.returncode == 1
    assert result.stdout.splitlines() == [
        "allowlist line 1: needs two or more names and a # reason",
        "CRAP 10.1 >= 10: pkg.mod.risky",
        "duplicate score=1.00: pkg/mod.py::get_a ~ pkg/mod.py::get_b",
        "ub-mode gate: 3 problem(s), 1 duplicate pair(s) reported",
    ]
