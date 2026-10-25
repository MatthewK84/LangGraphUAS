"""Fail when crapper or dryer output breaks the ub-mode thresholds.

Thresholds come from docs/skills/ub-mode/SKILL.md: every function's CRAP score
is below 10, and no two functions are duplicates at a dryer score of 0.8 or
more unless the pair is listed in the allowlist with a reason.

Usage (from backend/):
    python scripts/ub_gate.py --crap crap.txt --dry dry.txt \
        --allowlist ub-mode-allowlist.txt

Allowlist format: one group per line, two or more ``path::qualname`` names
separated by spaces, then ``#`` and the reason. Every pair within a group is
allowed. A line without a reason, or a group that matches no reported pair,
is an error, so the list cannot silently outlive the code it excuses.
"""

import argparse
import ast
import re
import sys
from itertools import combinations
from pathlib import Path

CRAP_LIMIT = 10.0
DRY_LIMIT = 0.8

_CRAP_ROW = re.compile(r"^(\S+)\s+(\S+)\s+\d+\s+[\d.]+%\s+([\d.]+)\s*$")
_DRY_SCORE = re.compile(r"^DUPLICATE score=([\d.]+)\s*$")
_DRY_REGION = re.compile(r"^\s+(\S+?):(\d+)-(\d+)\s*$")

Pair = frozenset[str]


def crap_violations(text: str) -> list[str]:
    """Return one message per function at or above the CRAP limit."""
    found = []
    for line in text.splitlines():
        match = _CRAP_ROW.match(line)
        if match and float(match.group(3)) >= CRAP_LIMIT:
            found.append(f"CRAP {match.group(3)} >= 10: {match.group(2)}.{match.group(1)}")
    return found


def _functions(source: str) -> list[tuple[int, int, str]]:
    """Return (first line, last line, qualname) for every function in a module."""
    spans: list[tuple[int, int, str]] = []

    def visit(node: ast.AST, prefix: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                visit(child, f"{prefix}{child.name}.")
            elif isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                first = min([child.lineno, *(d.lineno for d in child.decorator_list)])
                spans.append((first, child.end_lineno or child.lineno, prefix + child.name))
                visit(child, f"{prefix}{child.name}.")

    visit(ast.parse(source), "")
    return spans


def function_at(root: Path, path: str, line: int) -> str:
    """Name the innermost function containing ``line``, as ``path::qualname``."""
    spans = _functions((root / path).read_text(encoding="utf-8"))
    containing = [span for span in spans if span[0] <= line <= span[1]]
    if not containing:
        return f"{path}:{line}"
    innermost = max(containing, key=lambda span: span[0])
    return f"{path}::{innermost[2]}"


def dry_pairs(text: str, root: Path) -> list[tuple[float, Pair]]:
    """Return (score, pair of function names) for each pair at or above the limit."""
    pairs: list[tuple[float, Pair]] = []
    score: float | None = None
    regions: list[str] = []
    for line in [*text.splitlines(), ""]:
        if (match := _DRY_SCORE.match(line)) is not None:
            score, regions = float(match.group(1)), []
        elif score is not None and (region := _DRY_REGION.match(line)) is not None:
            regions.append(function_at(root, region.group(1), int(region.group(2))))
            if len(regions) == 2:
                if score >= DRY_LIMIT:
                    pairs.append((score, frozenset(regions)))
                score = None
    return pairs


def load_allowlist(text: str) -> tuple[list[frozenset[Pair]], list[str]]:
    """Parse allowlist groups into the pairs each allows, plus format errors."""
    groups: list[frozenset[Pair]] = []
    errors: list[str] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        names, _, reason = line.partition("#")
        members = names.split()
        if not reason.strip() or len(members) < 2:
            errors.append(f"allowlist line {number}: needs two or more names and a # reason")
            continue
        groups.append(frozenset(frozenset(pair) for pair in combinations(members, 2)))
    return groups, errors


def dry_violations(pairs: list[tuple[float, Pair]], groups: list[frozenset[Pair]]) -> list[str]:
    """Return messages for pairs not allowlisted and for groups matching nothing."""
    allowed = frozenset().union(*groups) if groups else frozenset()
    reported = {pair for _, pair in pairs}
    found = [
        f"duplicate score={score:.2f}: {' ~ '.join(sorted(pair))}"
        for score, pair in pairs
        if pair not in allowed
    ]
    found.extend(
        f"stale allowlist group: {' '.join(sorted(set().union(*group)))}"
        for group in groups
        if not group & reported
    )
    return found


def main(argv: list[str] | None = None) -> int:
    """Print every violation and return 1 if there were any."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--crap", type=Path, required=True)
    parser.add_argument("--dry", type=Path, required=True)
    parser.add_argument("--allowlist", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path())
    args = parser.parse_args(argv)

    groups, errors = load_allowlist(args.allowlist.read_text(encoding="utf-8"))
    pairs = dry_pairs(args.dry.read_text(encoding="utf-8"), args.root)
    problems = [
        *errors,
        *crap_violations(args.crap.read_text(encoding="utf-8")),
        *dry_violations(pairs, groups),
    ]
    for problem in problems:
        print(problem)
    print(f"ub-mode gate: {len(problems)} problem(s), {len(pairs)} duplicate pair(s) reported")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
