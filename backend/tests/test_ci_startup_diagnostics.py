"""CI runs the startup-race tests on Postgres; the Compose smoke is local only.

The Postgres job must run the concurrent-startup tests (schema, seed,
checkpointer setup) against real Postgres.
The Compose quickstart job was removed from CI at the owner's request after
repeated startup failures; the stack, `scripts/compose_smoke.py`, and the
note on running it locally must stay.
"""

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CI = ROOT / ".github" / "workflows" / "ci.yml"


def _job(name: str) -> dict[str, Any]:
    jobs: dict[str, Any] = yaml.safe_load(CI.read_text())["jobs"]
    return jobs[name]


def test_postgres_job_runs_the_concurrent_startup_tests_on_postgres() -> None:
    steps = _job("postgres-integration")["steps"]
    runs = [s for s in steps if "test_startup_concurrency.py" in s.get("run", "")]
    assert len(runs) == 1
    assert runs[0]["env"]["SUAS_TEST_POSTGRES_URL"].startswith("postgresql://")


def test_compose_quickstart_is_local_only_not_a_ci_job() -> None:
    """The Compose job was removed from CI; the stack and its smoke stay runnable."""
    jobs: dict[str, Any] = yaml.safe_load(CI.read_text())["jobs"]
    assert "compose" not in jobs
    assert (ROOT / "scripts" / "compose_smoke.py").is_file()
    practices = (ROOT / "docs" / "engineering-practices.md").read_text()
    enforced, aspirational = practices.split("\n## Aspirational\n", 1)
    assert "`compose`" not in enforced
    assert "scripts/compose_smoke.py" in aspirational
