#!/usr/bin/env python3
"""Generate eval/LEADERBOARD.md from the committed results.

Generated, never hand-edited. A leaderboard someone can type into is a
leaderboard that will eventually disagree with the results it claims to
summarise, and the disagreement will be found by whoever trusts it most.

    python3 eval/build_leaderboard.py --write
"""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
RESULTS: Final[Path] = REPO_ROOT / "eval" / "results"
LEADERBOARD: Final[Path] = REPO_ROOT / "eval" / "LEADERBOARD.md"
RETRIEVAL_BASELINE: Final[Path] = REPO_ROOT / "eval" / "baselines" / "retrieval.json"


def _latest_run() -> tuple[str, list[dict[str, Any]]]:
    """Return the most recent results directory and everything in it."""
    days = sorted((path for path in RESULTS.iterdir() if path.is_dir()), reverse=True)
    if not days:
        raise SystemExit("no results; run eval/run.py --write first")
    newest = days[0]
    reports = [
        json.loads(path.read_text(encoding="utf-8")) for path in sorted(newest.glob("*.json"))
    ]
    return newest.name, reports


def _emit(text: str) -> None:
    """Write one line of output."""
    print(text)  # noqa: T201


def render() -> str:
    """Return the leaderboard as markdown."""
    day, reports = _latest_run()
    retrieval = json.loads(RETRIEVAL_BASELINE.read_text(encoding="utf-8"))
    generated = datetime.now(UTC).strftime("%Y-%m-%d")

    lines: list[str] = [
        "# Leaderboard",
        "",
        f"Generated {generated} from `eval/results/{day}/`. Do not edit by hand --",
        "run `python3 eval/build_leaderboard.py --write`.",
        "",
        "## Mission decisions",
        "",
        "`unsafe_go` is cleared for flight when the calculator refused, and is the",
        "only column that describes a hazard. `missed_go` costs a sortie. They are",
        "separate so a provider cannot buy one with the other.",
        "",
        "| provider | track | fixtures | unsafe_go | missed_go | mode_violation |"
        " invented_number | max hover error (W) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for report in sorted(reports, key=lambda item: (item["track"], item["provider"])):
        scores = report["scores"]
        lines.append(
            f"| `{report['provider']}` | {report['track']} | {report['fixtures']} "
            f"| {scores['unsafe_go']} | {scores['missed_go']} "
            f"| {scores['mode_violation']} | {scores['invented_number']} "
            f"| {scores['max_abs_hover_error_w']} |"
        )

    gated = retrieval["gated"]
    lines += [
        "",
        "## Retrieval",
        "",
        f"From `eval/baselines/retrieval.json`, retriever `{retrieval['retriever_version']}`,",
        f"embedder `{retrieval['embedder']}`. Rates carry 95% Wilson intervals.",
        "",
        "| metric | rate | 95% CI | n |",
        "|---|---|---|---|",
    ]
    for name in (
        "wrong_config_leak",
        "false_confirm_rate",
        "hard_negative_above_positive",
        "recall_at_4",
    ):
        entry = gated[name]
        low, high = entry["ci95"]
        lines.append(f"| `{name}` | {entry['rate']} | [{low}, {high}] | {entry['n']} |")
    lines.append(f"| `mrr` | {gated['mrr']} | - | - |")

    lines += [
        "",
        "## What these numbers are not",
        "",
        "No real language model has been measured here. `oracle` and",
        "`constant_power` are controls: the first calls the deterministic engine",
        "and must score zero, the second holds hover power constant as payload",
        "mass rises. They demonstrate that the harness separates a correct answer",
        "from the specific mistake the pack is built to catch. A row for a real",
        "model appears only when someone runs the pack against one.",
        "",
        "Retrieval figures are measured with a lexical projection, not an",
        "embedding model, because CI cannot run one. They are a regression floor",
        "for retrieval logic and not a claim about retrieval quality.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    """Render the leaderboard and print or write it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write eval/LEADERBOARD.md")
    parsed = parser.parse_args()

    rendered = render()
    if parsed.write:
        LEADERBOARD.write_text(rendered, encoding="utf-8")
        _emit(f"wrote {LEADERBOARD}")
    else:
        _emit(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
