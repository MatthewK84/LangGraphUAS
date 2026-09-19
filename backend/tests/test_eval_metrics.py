"""Metrics as pure functions, tested over synthetic sets.

Synthetic on purpose: a metric verified against real retrieval output tests the
retriever and the metric at once, and when it moves you cannot tell which. These
sets are constructed so the expected value is arithmetic.
"""

import pytest

from suas.eval.citation_checks import (
    CitedSpan,
    citation_belongs_to_config,
    citation_resolves,
    quote_verbatim,
    sealed_contamination,
    unsupported_numeric_rate,
    url_allowlisted,
)
from suas.eval.retrieval_metrics import (
    Fixture,
    RetrievedChunk,
    abstained,
    false_confirm,
    field_path_purity,
    hard_negative_above_positive,
    precision_at_k,
    recall_at_k,
    reciprocal_rank,
    wrong_config_leak,
)
from suas.eval.stats import mcnemar, wilson

CONFIG = "Freefly_Astro_Max"


def _hit(chunk_id: str, config: str = CONFIG, field_path: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(chunk_id=chunk_id, airframe_config_id=config, field_path=field_path)


def _fixture(**overrides: object) -> Fixture:
    base: dict[str, object] = {
        "qid": "q-1",
        "question": "What is the wind limit?",
        "airframe_config_id": CONFIG,
        "relevant_chunk_ids": ["good"],
    }
    base.update(overrides)
    return Fixture(**base)  # type: ignore[arg-type]


# --- recall / rank ------------------------------------------------------------


def test_recall_finds_a_relevant_chunk_inside_k() -> None:
    assert recall_at_k([_hit("a"), _hit("b"), _hit("good")], _fixture())


def test_recall_ignores_a_relevant_chunk_beyond_k() -> None:
    """Rank 5 with k=4 is a miss, because the model is only shown four spans."""
    retrieved = [_hit("a"), _hit("b"), _hit("c"), _hit("d"), _hit("good")]

    assert not recall_at_k(retrieved, _fixture(), k=4)


def test_recall_is_false_when_the_fixture_has_no_relevant_chunk() -> None:
    assert not recall_at_k([_hit("a")], _fixture(relevant_chunk_ids=[]))


@pytest.mark.parametrize(("position", "expected"), [(1, 1.0), (2, 0.5), (4, 0.25)])
def test_reciprocal_rank_is_one_over_the_first_hit(position: int, expected: float) -> None:
    retrieved = [_hit(f"miss-{i}") for i in range(position - 1)] + [_hit("good")]

    assert reciprocal_rank(retrieved, _fixture()) == expected


def test_reciprocal_rank_is_zero_when_nothing_relevant_returns() -> None:
    assert reciprocal_rank([_hit("a"), _hit("b")], _fixture()) == 0.0


def test_precision_counts_only_the_top_k() -> None:
    retrieved = [_hit("good"), _hit("a"), _hit("b"), _hit("c"), _hit("also")]

    assert precision_at_k(retrieved, _fixture(relevant_chunk_ids=["good", "also"]), k=4) == 0.25


def test_precision_of_nothing_is_zero_not_an_error() -> None:
    assert precision_at_k([], _fixture()) == 0.0


# --- the zero-tolerance three -------------------------------------------------


def test_a_hard_negative_ranked_above_the_positive_is_caught() -> None:
    """The Astro case: airframe minimum returned for a pack question."""
    retrieved = [_hit("airframe_min"), _hit("good")]
    fixture = _fixture(hard_negatives=["airframe_min"])

    assert hard_negative_above_positive(retrieved, fixture)


def test_a_hard_negative_ranked_below_the_positive_is_fine() -> None:
    retrieved = [_hit("good"), _hit("airframe_min")]

    assert not hard_negative_above_positive(retrieved, _fixture(hard_negatives=["airframe_min"]))


def test_a_hard_negative_that_never_appears_is_fine() -> None:
    assert not hard_negative_above_positive([_hit("good")], _fixture(hard_negatives=["x"]))


def test_a_chunk_from_another_airframe_is_a_leak() -> None:
    retrieved = [_hit("good"), _hit("other", config="Parrot_ANAFI_USA")]

    assert wrong_config_leak(retrieved, _fixture())


def test_no_leak_when_every_chunk_matches_the_configuration() -> None:
    assert not wrong_config_leak([_hit("good"), _hit("b")], _fixture())


def test_returning_anything_for_an_unanswerable_question_is_a_false_confirm() -> None:
    assert false_confirm([_hit("a")], _fixture(answerable=False, relevant_chunk_ids=[]))


def test_returning_nothing_for_an_unanswerable_question_is_correct() -> None:
    assert not false_confirm([], _fixture(answerable=False, relevant_chunk_ids=[]))


def test_an_answerable_question_returning_nothing_is_an_abstention() -> None:
    assert abstained([], _fixture())
    assert not abstained([_hit("good")], _fixture())


# --- field_path purity --------------------------------------------------------


def test_purity_is_none_when_no_field_path_was_requested() -> None:
    """None, not zero. Averaging an unasked question as zero invents a failure."""
    assert field_path_purity([_hit("good")], _fixture()) is None


def test_purity_is_the_matching_fraction() -> None:
    retrieved = [_hit("a", field_path="max_wind_mps"), _hit("b", field_path="battery_wh")]

    assert field_path_purity(retrieved, _fixture(field_path="max_wind_mps")) == 0.5


# --- citation checks ----------------------------------------------------------


def test_a_verbatim_quote_passes_across_a_line_break() -> None:
    span = CitedSpan(chunk_id="c1", quote="do not launch below 10 C")

    assert quote_verbatim(span, "Procedure:\ndo not launch  below 10 C at takeoff.")


def test_a_paraphrase_fails_even_though_it_sounds_right() -> None:
    span = CitedSpan(chunk_id="c1", quote="avoid cold starts")

    assert not quote_verbatim(span, "Do not launch below 10 C at takeoff.")


def test_an_unknown_chunk_id_does_not_resolve() -> None:
    assert not citation_resolves(CitedSpan("nope", "x"), {"c1": "text"})
    assert citation_resolves(CitedSpan("c1", "x"), {"c1": "text"})


def test_a_citation_from_another_configuration_is_rejected() -> None:
    """A resolvable id from the wrong airframe is a filter failure, not a
    hallucination, which is why it is a separate check."""
    by_chunk = {"c1": "Parrot_ANAFI_USA"}

    assert not citation_belongs_to_config(CitedSpan("c1", "x"), by_chunk, CONFIG)


def test_only_urls_from_the_documents_table_are_allowed() -> None:
    allowed = {"https://docs.freeflysystems.com/astro/limits"}

    assert url_allowlisted("https://docs.freeflysystems.com/astro/limits", allowed)
    assert not url_allowlisted("https://evil.example/collect", allowed)


def test_sealed_contamination_delegates_to_the_live_control() -> None:
    supporting = '{"hover_power_w": 119.94}'

    assert sealed_contamination("Hover power is 903 W.", supporting) == ["903 W"]
    assert sealed_contamination("Hover power is 120 W.", supporting) == []


def test_the_rate_is_per_brief_not_per_number() -> None:
    """One brief with three invented figures is one bad brief."""
    supporting = '{"hover_power_w": 119.94}'
    briefs = [
        ("903 W and 904 W and 905 W.", supporting),
        ("Hover power is 120 W.", supporting),
    ]

    assert unsupported_numeric_rate(briefs) == 0.5


def test_the_rate_of_nothing_is_zero() -> None:
    assert unsupported_numeric_rate([]) == 0.0


# --- statistics ---------------------------------------------------------------


def test_a_perfect_zero_still_carries_an_interval() -> None:
    """Forty observations do not buy certainty, and the report should not imply it."""
    interval = wilson(0, 40)

    assert interval.rate == 0.0
    assert interval.low == 0.0
    assert 0.08 < interval.high < 0.09


def test_a_known_interval_matches_the_published_value() -> None:
    interval = wilson(36, 40)

    assert interval.rate == 0.9
    assert round(interval.low, 3) == 0.769
    assert round(interval.high, 3) == 0.960


def test_an_empty_sample_does_not_divide_by_zero() -> None:
    assert wilson(0, 0).n == 0


def test_impossible_counts_are_rejected() -> None:
    with pytest.raises(ValueError, match="outside"):
        wilson(5, 4)


def test_mcnemar_ignores_pairs_both_configurations_agree_on() -> None:
    """Twenty agreements carry no information about which retriever is better."""
    agree = [True] * 20
    result = mcnemar([*agree, True, False], [*agree, False, True])

    assert result.discordant == 2
    assert result.only_a == 1
    assert result.only_b == 1


def test_mcnemar_reports_no_difference_when_outcomes_are_identical() -> None:
    assert mcnemar([True, False, True], [True, False, True]).p_value == 1.0


def test_mcnemar_rejects_unpaired_inputs() -> None:
    with pytest.raises(ValueError, match="equal-length"):
        mcnemar([True], [True, False])
