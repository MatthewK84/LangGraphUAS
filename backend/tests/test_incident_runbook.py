"""The incident playbooks name signals that exist (#114).

Four failures are foreseeable: the weather provider goes down, the seal starts
rejecting briefs, a corpus chunk is quarantined, a key leaks. Each playbook in
docs/ops.md names the metric or log line that signals it, and a playbook that
names a metric ``/metrics`` never emits, or a log line no code writes, sends an
operator looking for something that will never appear. So every backticked
``suas_*`` metric must be one the exporter renders, with the label it is shown
with, and every backticked ``"..."`` log line must be written by the code.
"""

import re
from pathlib import Path

import pytest

from suas.api.observability import MetricsRegistry

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
_PLAYBOOKS = (
    "Weather provider down",
    "Seal-violation spike",
    "Quarantined corpus",
    "Leaked key",
)
_METRIC = re.compile(r"`(suas_[a-z_]+)(?:\{([a-z_]+)=[^`]*\})?`")
_LOG_LINE = re.compile(r'`"([^"`]+)"`')


def _playbook(title: str) -> str:
    ops = (_ROOT / "docs/ops.md").read_text()
    section = ops.split("## Incident playbooks", 1)[1].split("\n## ", 1)[0]
    return section.split(f"### {title}\n", 1)[1].split("\n### ", 1)[0]


def _signal(title: str) -> str:
    body = _playbook(title)
    assert "**Signal.**" in body, title
    return body.split("**Signal.**", 1)[1].split("\n\n", 1)[0]


def _code() -> str:
    sources = [*(_BACKEND / "suas").rglob("*.py"), *(_BACKEND / "scripts").glob("*.py")]
    return "\n".join(path.read_text() for path in sources)


def _exporter() -> str:
    """Return /metrics as rendered after one event of every kind."""
    metrics = MetricsRegistry()
    metrics.record_request("GET", "/api/plan", 401, 0.01)
    metrics.record_plan(is_viable=True, mode="advisory", weather_source="fallback")
    metrics.record_seal_violations(1)
    metrics.record_brief_suppressed("contradiction")
    metrics.record_hallucinated_citations(1)
    metrics.set_quarantine_open(1)
    return metrics.render()


@pytest.mark.parametrize("title", _PLAYBOOKS)
def test_each_playbook_is_short_and_names_its_signal_and_response(title: str) -> None:
    body = _playbook(title)
    signal = _signal(title)
    assert _METRIC.search(signal) or _LOG_LINE.search(signal), title
    assert "**Response.**" in body, title
    assert len(body.split()) <= 260, f"{title} is {len(body.split())} words; keep it short"


@pytest.mark.parametrize("title", _PLAYBOOKS)
def test_every_metric_a_playbook_names_is_exported_with_that_label(title: str) -> None:
    exporter = _exporter()
    for name, label in _METRIC.findall(_playbook(title)):
        assert f"# TYPE {name} " in exporter, name
        if label:
            labelled = re.search(rf"^{name}\{{[^}}]*\b{label}=", exporter, re.MULTILINE)
            assert labelled, f"{name} has no {label} label"


@pytest.mark.parametrize("title", _PLAYBOOKS)
def test_every_log_line_a_playbook_names_is_written_by_the_code(title: str) -> None:
    code = _code()
    for line in _LOG_LINE.findall(_playbook(title)):
        assert line in code, line


def test_the_seal_violation_spike_has_a_written_response() -> None:
    # The test that would have failed before: there was no written response.
    response = _playbook("Seal-violation spike").split("**Response.**", 1)[1]
    assert "SUAS_OPENAI_API_KEY" in response
    assert "acknowledgement" in response
