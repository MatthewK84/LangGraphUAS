#!/usr/bin/env python3
"""Fail when the oracle changed but its version did not.

CALCULATOR_VERSION is hand-maintained so it keeps meaning something. That only
works if forgetting to bump it is impossible rather than merely discouraged, so
this runs on every pull request that touches backend/suas/calculations/.

Usage:
    python3 backend/scripts/check_calculator_version.py --base origin/main
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from typing import Final

CALC_DIR: Final[str] = "backend/suas/calculations/"
VERSION_FILE: Final[str] = "backend/suas/calculations/assessment.py"
VERSION_PATTERN: Final[re.Pattern[str]] = re.compile(
    r'^CALCULATOR_VERSION:\s*str\s*=\s*"([^"]+)"', re.MULTILINE
)


def _repo_root() -> str:
    """Return the repository root, so paths resolve the same from any cwd."""
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return result.stdout.strip()


def _git(args: list[str]) -> str:
    """Run a git command against the repository root, returning stdout.

    Paths below are repository-relative, and git resolves a pathspec against the
    current directory. Anchoring to the root keeps the gate correct whether CI
    invokes it from backend/ or from the top level.
    """
    try:
        result = subprocess.run(
            ["git", "-C", _repo_root(), *args],
            capture_output=True,
            text=True,
            check=True,
            timeout=60,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("git not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"git timed out: {' '.join(args)}") from exc
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"git failed: {exc.stderr.strip()}") from exc
    return result.stdout


def changed_calculation_files(base: str) -> list[str]:
    """Return calculation files changed between the merge base and HEAD."""
    output: str = _git(["diff", "--name-only", f"{base}...HEAD", "--", CALC_DIR])
    return [line for line in output.splitlines() if line.strip()]


def version_at(ref: str) -> str:
    """Return CALCULATOR_VERSION as of a git ref, or '' when unreadable."""
    try:
        source: str = _git(["show", f"{ref}:{VERSION_FILE}"])
    except RuntimeError:
        return ""
    match = VERSION_PATTERN.search(source)
    return match.group(1) if match else ""


def main() -> int:
    """Compare the oracle's version across the diff and report the verdict."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="base ref to compare against")
    parsed = parser.parse_args()

    try:
        changed: list[str] = changed_calculation_files(parsed.base)
        base_version: str = version_at(parsed.base)
        head_version: str = version_at("HEAD")
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if not changed:
        print("No changes under calculations/. Nothing to check.")
        return 0
    if not head_version:
        print(f"error: could not read CALCULATOR_VERSION from {VERSION_FILE}", file=sys.stderr)
        return 2
    if not base_version:
        print(f"Base ref has no CALCULATOR_VERSION; treating {head_version} as the first.")
        return 0
    if base_version != head_version:
        print(f"CALCULATOR_VERSION bumped {base_version} -> {head_version}. OK.")
        return 0

    print(
        "error: files under calculations/ changed but CALCULATOR_VERSION is still "
        f"{head_version}.\n"
        "\nChanged:\n  " + "\n  ".join(changed) + "\n"
        f"\nBump CALCULATOR_VERSION in {VERSION_FILE} and regenerate any pinned\n"
        "expectations that depend on it. A documentation-only edit still needs a\n"
        "patch bump: the gate cannot tell prose from physics, and a version that is\n"
        "occasionally bumped for nothing is cheaper than one that is silently stale.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
