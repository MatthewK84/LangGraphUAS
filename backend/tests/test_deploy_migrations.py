"""Migrations are an explicit deploy step, not a side effect of a restart (#87).

The image's entrypoint used to run ``alembic upgrade head`` before every
start. A rollback (``alembic downgrade`` to the revision the previous image
expects) was therefore undone by the next restart of the newer image, and N
replicas starting together ran N upgrades against one database at once. Now
the entrypoint migrates only when ``MIGRATE_ON_START=true`` or when told to
(``docker-entrypoint.sh migrate``); Compose runs a one-shot ``migrate`` service
first, and Railway a pre-deploy command. Alembic also holds the startup
advisory lock, so concurrent upgrades run one after another.

The Postgres cases need SUAS_TEST_POSTGRES_URL (an admin URL), as the
postgres-integration CI job sets.
"""

import json
import os
import subprocess
import sys
import uuid
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
import yaml
from sqlalchemy import inspect

from suas.config import Settings
from suas.db.engine import SchemaNotMigratedError, create_engine, prepare_schema
from suas.db.migrations import EXPECTED_REVISION
from suas.db.models import Base
from suas.main import _build_resources
from tests.conftest import stamp_revision

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
_ENTRYPOINT = _BACKEND / "scripts" / "docker-entrypoint.sh"
_ADMIN_URL = os.environ.get("SUAS_TEST_POSTGRES_URL", "")
_needs_postgres = pytest.mark.skipif(
    not _ADMIN_URL, reason="needs SUAS_TEST_POSTGRES_URL (real Postgres)"
)


def _fake(bin_dir: Path, name: str, log: Path, status: int = 0) -> None:
    script = bin_dir / name
    script.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\nexit {status}\n')
    script.chmod(0o755)


@pytest.fixture
def fakes(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    for name in ("alembic", "uvicorn"):
        _fake(bin_dir, name, log)
    return bin_dir, log


def _run(
    bin_dir: Path, *args: str, path_tail: str = "/usr/bin:/bin", **env: str
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_ENTRYPOINT), *args],
        env={"PATH": f"{bin_dir}:{path_tail}", **env},
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _calls(log: Path) -> list[str]:
    return [line.split()[0] + " " + " ".join(line.split()[1:3]) for line in _lines(log)]


def _lines(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


# --- the entrypoint -------------------------------------------------------------


def test_a_plain_start_serves_without_migrating(fakes: tuple[Path, Path]) -> None:
    bin_dir, log = fakes

    assert _run(bin_dir).returncode == 0

    assert [line.split()[0] for line in _lines(log)] == ["uvicorn"]


@pytest.mark.parametrize("value", ["false", "0", "", "yes", "TRUE "])
def test_only_true_turns_migrate_on_start_on(fakes: tuple[Path, Path], value: str) -> None:
    bin_dir, log = fakes

    assert _run(bin_dir, MIGRATE_ON_START=value).returncode == 0

    assert [line.split()[0] for line in _lines(log)] == ["uvicorn"]


def test_migrate_on_start_upgrades_then_serves(fakes: tuple[Path, Path]) -> None:
    bin_dir, log = fakes

    assert _run(bin_dir, MIGRATE_ON_START="true").returncode == 0

    assert _calls(log) == ["alembic upgrade head", "uvicorn suas.main:app --host"]


def test_a_failed_migration_on_start_does_not_serve(fakes: tuple[Path, Path]) -> None:
    bin_dir, log = fakes
    _fake(bin_dir, "alembic", log, status=1)

    assert _run(bin_dir, MIGRATE_ON_START="true").returncode != 0

    assert [line.split()[0] for line in _lines(log)] == ["alembic"]


def test_the_migrate_command_upgrades_and_exits(fakes: tuple[Path, Path]) -> None:
    bin_dir, log = fakes

    assert _run(bin_dir, "migrate").returncode == 0

    assert _calls(log) == ["alembic upgrade head"]


def test_another_command_runs_in_place_of_the_server(fakes: tuple[Path, Path]) -> None:
    # How a platform's one-off or pre-deploy command reaches the image.
    bin_dir, log = fakes

    assert _run(bin_dir, "alembic", "current").returncode == 0

    assert _calls(log) == ["alembic current"]


# --- what each deploy path runs ---------------------------------------------------


def _compose() -> dict[str, dict[str, object]]:
    services: dict[str, dict[str, object]] = yaml.safe_load(
        (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    )["services"]
    return services


def test_compose_migrates_once_before_the_backend_starts() -> None:
    services = _compose()
    migrate = services["migrate"]
    assert migrate["command"] == ["migrate"]
    assert migrate["restart"] == "no"
    assert migrate["depends_on"] == {"db": {"condition": "service_healthy"}}
    backend_env = services["backend"]["environment"]
    assert migrate["environment"] == {"SUAS_DATABASE_URL": backend_env["SUAS_DATABASE_URL"]}  # type: ignore[index]
    assert services["backend"]["depends_on"]["migrate"] == {  # type: ignore[index]
        "condition": "service_completed_successfully"
    }
    assert "MIGRATE_ON_START" not in backend_env  # type: ignore[operator]


def test_railway_migrates_in_a_pre_deploy_step() -> None:
    railway = json.loads((_ROOT / "railway.json").read_text(encoding="utf-8"))
    assert railway["deploy"]["preDeployCommand"] == ["alembic upgrade head"]
    assert "startCommand" not in railway["deploy"]


def test_the_image_does_not_turn_migrate_on_start_on() -> None:
    assert "MIGRATE_ON_START" not in (_BACKEND / "Dockerfile").read_text(encoding="utf-8")


def _text(relative: str) -> str:
    return " ".join((_ROOT / relative).read_text(encoding="utf-8").split())


def test_the_docs_describe_the_deploy_step() -> None:
    for doc in ("README.md", "docs/ops.md", "docs/railway.md"):
        text = _text(doc)
        assert "MIGRATE_ON_START" in text, doc
        assert "docker-entrypoint.sh migrate" in text or "preDeployCommand" in text, doc
    assert "The container migrates before it serves" not in _text("README.md")
    assert "Deployed containers run `alembic upgrade head` in `docker-entrypoint.sh`" not in (
        _text("docs/ops.md")
    )
    assert "## Migrations" in _text("docs/ops.md")


def test_ci_runs_the_postgres_migration_cases() -> None:
    workflow = yaml.safe_load((_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["postgres-integration"]["steps"]
    runs = " ".join(str(step.get("run", "")) for step in steps)
    assert "tests/test_deploy_migrations.py" in runs


# --- against Postgres -------------------------------------------------------------


@pytest.fixture
def fresh_url() -> Iterator[str]:
    name = f"migrate_{uuid.uuid4().hex[:12]}"
    with psycopg.connect(_ADMIN_URL, autocommit=True) as admin:
        admin.execute(f'CREATE DATABASE "{name}"')
    base = _ADMIN_URL.rsplit("/", 1)[0]
    try:
        yield f"{base}/{name}"
    finally:
        with psycopg.connect(_ADMIN_URL, autocommit=True) as admin:
            admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _alembic(url: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(Path(sys.executable).parent / "alembic"), *args],
        cwd=_BACKEND,
        env={**_clean_env(), "SUAS_DATABASE_URL": _async(url)},
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if not k.startswith("SUAS_")}


def _async(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _stamped(url: str) -> str:
    with psycopg.connect(url) as connection:
        row = connection.execute("SELECT version_num FROM alembic_version").fetchone()
    assert row is not None
    return str(row[0])


@_needs_postgres
def test_a_restart_after_a_rollback_keeps_the_rolled_back_schema(
    fresh_url: str, tmp_path: Path
) -> None:
    # The test that would have failed before: the old entrypoint re-upgraded.
    assert _alembic(fresh_url, "upgrade", "head").returncode == 0
    assert _alembic(fresh_url, "downgrade", "-1").returncode == 0
    rolled_back = _stamped(fresh_url)
    assert rolled_back != EXPECTED_REVISION
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake(bin_dir, "uvicorn", tmp_path / "calls.log")
    alembic_dir = str(Path(sys.executable).parent)
    env = {"SUAS_DATABASE_URL": _async(fresh_url)}

    _run(bin_dir, path_tail=f"{alembic_dir}:/usr/bin:/bin", **env)
    assert _stamped(fresh_url) == rolled_back

    started = _run(
        bin_dir, path_tail=f"{alembic_dir}:/usr/bin:/bin", MIGRATE_ON_START="true", **env
    )
    assert started.returncode == 0, started.stderr
    assert _stamped(fresh_url) == EXPECTED_REVISION


@_needs_postgres
def test_replicas_upgrading_at_once_all_succeed(fresh_url: str) -> None:
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: _alembic(fresh_url, "upgrade", "head"), range(4)))

    assert [r.returncode for r in results] == [0, 0, 0, 0], [r.stderr[-500:] for r in results]
    assert _stamped(fresh_url) == EXPECTED_REVISION


# --- who owns the schema ------------------------------------------------------------
# The app's create_all used to run on every start. A backend that started before
# the migrate step on a fresh database built the tables itself, with no
# alembic_version row, and the migration that creates them then failed. Where
# Postgres is required (the image), alembic alone owns the schema now.


async def test_where_alembic_owns_the_schema_an_unmigrated_database_is_refused(
    tmp_path: Path,
) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh.db'}")
    try:
        with pytest.raises(SchemaNotMigratedError, match="alembic upgrade head"):
            await prepare_schema(engine, alembic_owns_schema=True)
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    finally:
        await engine.dispose()
    assert tables == []


async def test_where_alembic_owns_the_schema_a_migrated_database_starts(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'migrated.db'}")
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await stamp_revision(connection, EXPECTED_REVISION)
        await prepare_schema(engine, alembic_owns_schema=True)
    finally:
        await engine.dispose()


async def test_local_development_still_builds_its_own_schema(tmp_path: Path) -> None:
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'dev.db'}")
    try:
        await prepare_schema(engine, alembic_owns_schema=False)
        async with engine.connect() as connection:
            tables = await connection.run_sync(lambda sync: inspect(sync).get_table_names())
    finally:
        await engine.dispose()
    assert {"aircraft", "payloads", "mission_threads"} <= set(tables)


@_needs_postgres
async def test_a_backend_started_before_the_migrate_step_leaves_the_database_to_it(
    fresh_url: str,
) -> None:
    # The test that would have failed before: create_all ran, then upgrade failed.
    settings = Settings(require_postgres=True, database_url=_async(fresh_url))
    with pytest.raises(SchemaNotMigratedError):
        await _build_resources(settings)

    upgraded = _alembic(fresh_url, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr[-800:]
    assert _stamped(fresh_url) == EXPECTED_REVISION
