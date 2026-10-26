"""Backup and restore keep every signature verifiable (#113).

An acknowledgement is a signature on one assessment: ``mission_threads`` holds
the ``inputs_hash`` the operator signed, and the checkpoint holds the sealed
assessment it was signed against. A restore that brings back one without the
other, or the two from different moments, keeps the signature in appearance
only. So the backup is one ``pg_dump`` of the one database both live in, and
``scripts/verify_restore.py`` checks every stored ack against its checkpoint.

The Postgres case runs the exact procedure ``docs/ops.md`` gives: back up a
live database, restore into an empty one, verify, then serve from it and sign
the plan that was still waiting. Set SUAS_TEST_POSTGRES_URL to run it, as the
postgres-integration CI job does.
"""

import os
import re
import subprocess
import sys
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import httpx
import psycopg
import pytest
from fastapi import FastAPI
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from suas.db.restore_check import verify_acknowledgements

from suas.config import get_settings
from suas.db.models import MissionThreadRow
from suas.db.retention import record_acknowledgement, record_thread
from tests.test_ack import _BODY

_BACKEND = Path(__file__).resolve().parents[1]
_ROOT = _BACKEND.parent
_SCRIPTS = _BACKEND / "scripts"
_ADMIN_URL = os.environ.get("SUAS_TEST_POSTGRES_URL", "")
_needs_postgres = pytest.mark.skipif(not _ADMIN_URL, reason="needs SUAS_TEST_POSTGRES_URL")


def _client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")


def _confirm(inputs_hash: str) -> dict[str, Any]:
    return {"action": "confirm", "actor": "dispatcher-1", "inputs_hash": inputs_hash}


async def _plan(client: httpx.AsyncClient) -> dict[str, Any]:
    created = await client.post("/api/plan", json=_BODY)
    assert created.status_code == 200, created.text
    body: dict[str, Any] = created.json()
    assert body["awaiting_ack"] is True
    return body


async def _plan_and_sign(client: httpx.AsyncClient) -> str:
    plan = await _plan(client)
    signed = await client.post(
        f"/api/plan/{plan['thread_id']}/ack", json=_confirm(plan["assessment"]["inputs_hash"])
    )
    assert signed.status_code == 200, signed.text
    return str(plan["thread_id"])


# --- the check itself ---------------------------------------------------------


async def test_a_signed_plan_verifies_and_a_pending_one_is_not_counted(
    app_with_graph: FastAPI,
    graph: CompiledStateGraph,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(app_with_graph) as client:
        await _plan_and_sign(client)
        await _plan(client)

    check = await verify_acknowledgements(session_factory, graph.checkpointer)

    assert check.checked == 1
    assert check.broken == []


async def test_a_signature_that_no_longer_matches_its_checkpoint_is_named(
    app_with_graph: FastAPI,
    graph: CompiledStateGraph,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _client(app_with_graph) as client:
        thread_id = await _plan_and_sign(client)
    async with session_factory() as session:
        row = await session.get(MissionThreadRow, thread_id)
        assert row is not None
        row.ack_inputs_hash = "f" * 64
        await session.commit()

    check = await verify_acknowledgements(session_factory, graph.checkpointer)

    assert check.checked == 1
    assert len(check.broken) == 1
    assert check.broken[0].startswith(f"{thread_id}: signed {'f' * 64}, checkpoint has ")


async def test_a_signature_whose_checkpoint_is_missing_is_named(
    graph: CompiledStateGraph, session_factory: async_sessionmaker[AsyncSession]
) -> None:
    async with session_factory() as session:
        await record_thread(session, "lost")
    async with session_factory() as session:
        await record_acknowledgement(
            session,
            thread_id="lost",
            actor="dispatcher-1",
            action="confirm",
            inputs_hash="abc",
            calculator_version="1",
        )

    check = await verify_acknowledgements(session_factory, graph.checkpointer)

    assert check.broken == ["lost: signed abc, checkpoint has nothing"]


# --- the scripts --------------------------------------------------------------


def _fake(bin_dir: Path, name: str, log: Path) -> None:
    path = bin_dir / name
    path.write_text(f'#!/bin/sh\necho "{name} $*" >> "{log}"\n')
    path.chmod(0o755)


def _script(name: str, *args: str, path: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(_SCRIPTS / name), *args],
        env={"PATH": path, **env},
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.fixture
def fakes(tmp_path: Path) -> tuple[Path, Path]:
    bin_dir, log = tmp_path / "bin", tmp_path / "calls.log"
    bin_dir.mkdir()
    for name in ("pg_dump", "pg_restore"):
        _fake(bin_dir, name, log)
    return bin_dir, log


_SA_URL = "postgresql+psycopg://suas:pw@db:5432/suas"


def test_backup_dumps_the_whole_database_in_one_snapshot(
    fakes: tuple[Path, Path], tmp_path: Path
) -> None:
    bin_dir, log = fakes
    done = _script(
        "backup.sh",
        str(tmp_path / "x.dump"),
        path=f"{bin_dir}:/usr/bin:/bin",
        SUAS_DATABASE_URL=_SA_URL,
    )
    assert done.returncode == 0, done.stderr
    assert log.read_text().split() == [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        f"--file={tmp_path / 'x.dump'}",
        "--dbname=postgresql://suas:pw@db:5432/suas",
    ]


def test_restore_is_all_or_nothing_into_the_target(
    fakes: tuple[Path, Path], tmp_path: Path
) -> None:
    bin_dir, log = fakes
    dump = tmp_path / "x.dump"
    dump.write_bytes(b"PGDMP")
    done = _script(
        "restore.sh", str(dump), path=f"{bin_dir}:/usr/bin:/bin", SUAS_DATABASE_URL=_SA_URL
    )
    assert done.returncode == 0, done.stderr
    assert log.read_text().split() == [
        "pg_restore",
        "--exit-on-error",
        "--single-transaction",
        "--no-owner",
        "--no-privileges",
        "--dbname=postgresql://suas:pw@db:5432/suas",
        str(dump),
    ]


@pytest.mark.parametrize("name", ["backup.sh", "restore.sh"])
def test_the_scripts_refuse_to_guess(fakes: tuple[Path, Path], name: str) -> None:
    bin_dir, log = fakes
    path = f"{bin_dir}:/usr/bin:/bin"
    no_file = _script(name, path=path, SUAS_DATABASE_URL=_SA_URL)
    no_url = _script(name, "x.dump", path=path)
    assert no_file.returncode == 2
    assert "usage" in no_file.stderr
    assert no_url.returncode == 2
    assert "SUAS_DATABASE_URL" in no_url.stderr
    assert not log.exists()


def test_restore_refuses_a_missing_dump(fakes: tuple[Path, Path], tmp_path: Path) -> None:
    bin_dir, log = fakes
    done = _script(
        "restore.sh",
        str(tmp_path / "nope.dump"),
        path=f"{bin_dir}:/usr/bin:/bin",
        SUAS_DATABASE_URL=_SA_URL,
    )
    assert done.returncode == 2
    assert "nope.dump" in done.stderr
    assert not log.exists()


# --- the procedure, on Postgres -----------------------------------------------


@pytest.fixture
def databases() -> Iterator[tuple[str, str]]:
    """Yield a source and an empty target database, as plain libpq URLs."""
    names = [f"backup_{uuid.uuid4().hex[:12]}" for _ in range(2)]
    with psycopg.connect(_ADMIN_URL, autocommit=True) as admin:
        for name in names:
            admin.execute(f'CREATE DATABASE "{name}"')
    base = _ADMIN_URL.rsplit("/", 1)[0]
    try:
        yield f"{base}/{names[0]}", f"{base}/{names[1]}"
    finally:
        with psycopg.connect(_ADMIN_URL, autocommit=True) as admin:
            for name in names:
                admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')


def _sa(url: str) -> str:
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _env(url: str) -> dict[str, str]:
    clean = {k: v for k, v in os.environ.items() if not k.startswith("SUAS_")}
    return {**clean, "SUAS_DATABASE_URL": _sa(url)}


def _run(*argv: str, url: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        cwd=_BACKEND,
        env=_env(url),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def _verify(url: str) -> subprocess.CompletedProcess[str]:
    return _run(sys.executable, "scripts/verify_restore.py", url=url)


@pytest.fixture
def serve(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Return a context that runs the real app, lifespan included, on a database."""

    @asynccontextmanager
    async def _serve(url: str) -> AsyncIterator[httpx.AsyncClient]:
        from suas.main import create_app

        for key in [k for k in os.environ if k.startswith("SUAS_")]:
            monkeypatch.delenv(key)
        monkeypatch.setenv("SUAS_DATABASE_URL", _sa(url))
        monkeypatch.setenv("SUAS_DEMO_MODE", "true")
        get_settings.cache_clear()
        try:
            app = create_app()
            async with app.router.lifespan_context(app), _client(app) as client:
                yield client
        finally:
            get_settings.cache_clear()

    return _serve


def _sign_here(url: str, thread_id: str) -> str:
    with psycopg.connect(url) as connection:
        row = connection.execute(
            "SELECT ack_inputs_hash FROM mission_threads WHERE thread_id = %s", (thread_id,)
        ).fetchone()
    assert row is not None
    return str(row[0])


@_needs_postgres
async def test_the_runbook_restores_signatures_that_still_verify(
    databases: tuple[str, str], tmp_path: Path, serve: Any
) -> None:
    source, target = databases
    assert (
        _run(
            str(Path(sys.executable).parent / "alembic"), "upgrade", "head", url=source
        ).returncode
        == 0
    )
    async with serve(source) as client:
        signed_id = await _plan_and_sign(client)
        pending = await _plan(client)

    dump = tmp_path / "suas.dump"
    backup = _run("scripts/backup.sh", str(dump), url=source)
    assert backup.returncode == 0, backup.stderr
    restore = _run("scripts/restore.sh", str(dump), url=target)
    assert restore.returncode == 0, restore.stderr

    verified = _verify(target)
    assert verified.returncode == 0, verified.stdout + verified.stderr
    assert "1 acknowledgement(s) verified" in verified.stdout

    async with serve(target) as client:
        ready = await client.get("/ready")
        assert ready.json()["migrations"] == "ok"
        read = (await client.get(f"/api/plan/{signed_id}")).json()
        assert read["found"] is True
        assert read["assessment"]["inputs_hash"] == _sign_here(target, signed_id)
        thread = f"/api/plan/{pending['thread_id']}"
        stale = await client.post(f"{thread}/ack", json=_confirm("stale-hash"))
        assert stale.status_code == 409
        signed = await client.post(
            f"{thread}/ack", json=_confirm(pending["assessment"]["inputs_hash"])
        )
        assert signed.status_code == 200, signed.text

    again = _verify(target)
    assert again.returncode == 0
    assert "2 acknowledgement(s) verified" in again.stdout


@_needs_postgres
async def test_verify_fails_a_restore_whose_signature_lost_its_assessment(
    databases: tuple[str, str], serve: Any
) -> None:
    source, _ = databases
    assert (
        _run(
            str(Path(sys.executable).parent / "alembic"), "upgrade", "head", url=source
        ).returncode
        == 0
    )
    async with serve(source) as client:
        signed_id = await _plan_and_sign(client)
    with psycopg.connect(source) as connection:
        connection.execute("DELETE FROM checkpoints WHERE thread_id = %s", (signed_id,))

    failed = _verify(source)

    assert failed.returncode == 1
    assert f"{signed_id}: signed " in failed.stdout
    assert "checkpoint has nothing" in failed.stdout


def test_verify_refuses_a_database_without_checkpoints(tmp_path: Path) -> None:
    done = _run(sys.executable, "scripts/verify_restore.py", url="sqlite+aiosqlite:///x.db")
    assert done.returncode == 2
    assert "Postgres" in done.stderr


# --- docs and CI --------------------------------------------------------------


def _text(relative: str) -> str:
    return re.sub(r"\s+", " ", (_ROOT / relative).read_text())


def test_ops_gives_the_tested_procedure() -> None:
    ops = (_ROOT / "docs/ops.md").read_text()
    section = ops.split("## Backup and restore", 1)[1].split("\n## ", 1)[0]
    for step in (
        "scripts/backup.sh",
        "scripts/restore.sh",
        "scripts/verify_restore.py",
        "tests/test_backup_restore.py",
        "inputs_hash",
    ):
        assert step in section, step
    assert section.index("restore.sh") < section.index("verify_restore.py")


def test_ci_runs_the_procedure_on_postgres() -> None:
    assert "tests/test_backup_restore.py" in _text(".github/workflows/ci.yml")
