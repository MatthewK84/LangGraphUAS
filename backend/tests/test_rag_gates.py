"""Retrieval gates. A failure here is a build break, not a report.

Each gated failure hands a human a plausible wrong limit, which is worse than
handing them nothing: a citation makes a wrong number look checked.

Two kinds of gate, and the difference matters.

**Absolute zeros** are properties of the retrieval *logic*, not of the embedding
model. A configuration leak means a WHERE clause went missing from a fusion leg;
a false confirm means the relevance floor stopped working. Neither depends on
how good the embedder is, so both are enforced at zero on every PR.

**Floors** are the metrics the embedder governs. CI runs HashingEmbedder, a
deterministic lexical projection, because it cannot run sentence-transformers.
Two of the targets in docs/backlog/16 are not reachable that way -- they need
semantic matching, and the misses are named below rather than hidden. Those are
enforced as "no worse than the committed baseline", which still catches the
regression the gate exists for, and should be tightened to the spec targets once
a real embedding model is serving.
"""

from typing import Any, Final

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from suas.eval.harness import (
    SAFETY_LIMIT_CLASSES,
    load_baseline,
    measure,
    retriever_version,
)
from suas.graph.seal import unsupported_numerics

# From docs/backlog/16. Reachable with the CI embedder.
RECALL_GATE: Final[float] = 0.90
MRR_GATE: Final[float] = 0.80

# From docs/backlog/16, NOT reachable with the CI embedder. Recorded so the
# target does not quietly become whatever we happen to measure.
SAFETY_RECALL_TARGET: Final[float] = 0.95
HARD_NEGATIVE_TARGET: Final[float] = 0.0


@pytest.fixture(scope="module")
def baseline() -> dict[str, Any]:
    return load_baseline()


@pytest.fixture
async def report(session_factory: async_sessionmaker[AsyncSession]) -> dict[str, Any]:
    """Measure with the same harness the reporting script uses."""
    return await measure(session_factory)


def _safety_recall(report: dict[str, Any]) -> tuple[int, int]:
    """Return (hits, n) over the classes where a wrong answer is a wrong limit."""
    hits = 0
    total = 0
    for name, data in report["per_class_recall"].items():
        if name in SAFETY_LIMIT_CLASSES:
            hits += data["recall"]
            total += data["n"]
    return hits, total


# --- absolute zeros -----------------------------------------------------------


async def test_no_chunk_leaks_from_another_configuration(report: dict[str, Any]) -> None:
    """Zero, always. One airframe's limits presented as another's, with a citation."""
    assert report["gated"]["wrong_config_leak"]["rate"] == 0.0


async def test_no_unanswerable_question_returns_evidence(report: dict[str, Any]) -> None:
    """Zero, always. A fabricated limit wearing a citation is the worst output
    this system can produce -- worse than admitting the corpus is silent."""
    assert report["gated"]["false_confirm_rate"]["rate"] == 0.0


async def test_a_brief_quoting_retrieved_text_contaminates_nothing() -> None:
    """sealed_contamination at zero: a number quoted from evidence is supported."""
    evidence = "Sustained wind of 12 m/s is the published limit for the airframe."

    assert unsupported_numerics("The wind limit is 12 m/s.", evidence) == []


async def test_a_brief_inventing_a_number_is_still_caught() -> None:
    """The negative control. A contamination check that never fires is not a check."""
    evidence = "Sustained wind of 12 m/s is the published limit for the airframe."

    assert unsupported_numerics("Hover power is 903 W.", evidence) == ["903 W"]


# --- reachable spec gates ------------------------------------------------------


async def test_recall_clears_the_gate(report: dict[str, Any]) -> None:
    assert report["gated"]["recall_at_4"]["rate"] >= RECALL_GATE


async def test_mrr_clears_the_gate(report: dict[str, Any]) -> None:
    assert report["gated"]["mrr"] >= MRR_GATE


# --- regression floors ---------------------------------------------------------


async def test_the_measurement_is_comparable_to_the_baseline(
    report: dict[str, Any], baseline: dict[str, Any]
) -> None:
    """Refuse to compare across retriever versions.

    A recall number from one embedder held against another's is not a regression
    test, it is two unrelated measurements plotted on one axis. When this fails,
    the fix is to re-measure and commit a new baseline with a reason -- not to
    relax a threshold.
    """
    assert report["retriever_version"] == retriever_version(report["embedder"])
    assert report["retriever_version"] == baseline["retriever_version"], (
        "retriever changed; re-run scripts/run_retrieval_eval.py --write and say why"
    )


async def test_no_gated_rate_regresses_past_the_baseline_interval(
    report: dict[str, Any], baseline: dict[str, Any]
) -> None:
    """The regression rule from docs/backlog/16.

    Fail only when the point estimate falls outside the baseline's interval.
    Anything tighter makes CI a coin flip on 40 fixtures, and a gate people
    learn to ignore is worse than no gate.
    """
    for name in ("recall_at_4",):
        measured = report["gated"][name]["rate"]
        floor = baseline["gated"][name]["ci95"][0]
        assert measured >= floor, f"{name} {measured} below baseline lower bound {floor}"


async def test_hard_negatives_do_not_get_worse(
    report: dict[str, Any], baseline: dict[str, Any]
) -> None:
    """Target is zero; the CI embedder cannot reach it.

    One fixture fails: tm-05, "What is the gross weight limit?", which ranks the
    payload paragraph above the gross-mass paragraph. Resolving it needs
    weight/mass synonymy -- a lexical projection cannot do it and a real
    embedding model can. Enforced as "no worse than baseline" so the regression
    is still caught, and left failing rather than fixed by editing the corpus,
    because tuning documents until a metric reads zero measures the corpus.
    """
    measured = report["gated"]["hard_negative_above_positive"]["rate"]
    recorded = baseline["gated"]["hard_negative_above_positive"]["rate"]

    assert measured <= recorded
    assert HARD_NEGATIVE_TARGET == 0.0, "the target stays zero even while unmet"


async def test_safety_limit_recall_does_not_get_worse(report: dict[str, Any]) -> None:
    """Target is 0.95; the CI embedder reaches 0.875.

    One fixture fails: ot-02, "How cold can the aircraft itself be flown?",
    which needs "cold" matched to "-20 C". Purely semantic, and exactly what the
    hashing fallback cannot do. The floor is the measured value, so a drop still
    breaks the build.
    """
    hits, total = _safety_recall(report)
    measured = hits / total

    assert total >= 20, "safety-limit classes should dominate the fixture set"
    assert measured >= 0.875
    assert SAFETY_RECALL_TARGET == 0.95, "the target stays 0.95 even while unmet"
