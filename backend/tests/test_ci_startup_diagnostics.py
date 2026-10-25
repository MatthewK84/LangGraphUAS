"""CI must run the seed-race test on Postgres and leave a diagnosable trail.

Main went red once with only "container langgraphuas-backend-1 is unhealthy"
in the failing step. These pin that the Postgres job runs the concurrent-seed
test against real Postgres, and that a failed Compose job prints the
container states, the backend's own log and its healthcheck history.
"""

from pathlib import Path
from typing import Any

import yaml

CI = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"


def _job(name: str) -> dict[str, Any]:
    jobs: dict[str, Any] = yaml.safe_load(CI.read_text())["jobs"]
    return jobs[name]


def test_postgres_job_runs_the_concurrent_seed_test_on_postgres() -> None:
    steps = _job("postgres-integration")["steps"]
    runs = [s for s in steps if "test_seed_concurrency.py" in s.get("run", "")]
    assert len(runs) == 1
    assert runs[0]["env"]["SUAS_TEST_POSTGRES_URL"].startswith("postgresql://")


def test_failed_compose_job_dumps_backend_state_and_logs() -> None:
    steps = _job("compose")["steps"]
    on_failure = "\n".join(s["run"] for s in steps if s.get("if") == "failure()")
    assert "docker compose ps --all" in on_failure
    assert "docker compose logs --no-color --timestamps backend" in on_failure
    assert ".State.Health" in on_failure
