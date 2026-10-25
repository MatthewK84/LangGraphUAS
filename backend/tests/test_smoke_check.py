"""The startup smoke check must catch a not-ready container in both directions (#111)."""

import importlib.util
from pathlib import Path
from types import ModuleType

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "smoke_check.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("smoke_check", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_READY = {"ready": True, "database": "ok", "migrations": "ok", "checkpointer": "ok"}
_UNMIGRATED = {**_READY, "ready": False, "migrations": "pending"}


def _failed(checks: list[tuple[str, bool]]) -> list[str]:
    return [name for name, passed in checks if not passed]


def test_a_migrated_app_passes_the_ready_checks() -> None:
    assert _failed(_load().ready_checks(200, _READY, expect_unmigrated=False)) == []


def test_an_unmigrated_app_that_still_says_ready_fails_the_smoke() -> None:
    """The old /ready answered 200 with no migrations field on an unmigrated schema."""
    old_answer = {"ready": True, "database": "ok", "checkpointer": "ok"}
    assert _failed(_load().ready_checks(200, old_answer, expect_unmigrated=True)) != []


def test_an_unmigrated_app_reporting_pending_passes_the_negative_smoke() -> None:
    assert _failed(_load().ready_checks(503, _UNMIGRATED, expect_unmigrated=True)) == []


def test_a_pending_schema_fails_the_normal_smoke() -> None:
    assert "ready migrations ok" in _failed(
        _load().ready_checks(503, _UNMIGRATED, expect_unmigrated=False)
    )


def test_a_broken_checkpointer_fails_the_normal_smoke() -> None:
    broken = {**_READY, "ready": False, "checkpointer": "unavailable"}
    assert "ready checkpointer ok" in _failed(
        _load().ready_checks(503, broken, expect_unmigrated=False)
    )
