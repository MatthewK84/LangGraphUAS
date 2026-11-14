"""Restore SQL from a newer pg_dump must still apply to Postgres 16.

pg_dump 17+ emits ``SET transaction_timeout = 0;``. Postgres 16, which this
project runs in Compose and CI, rejects that parameter, and ``restore.sh``
stopped at the first error. The filter drops only those newer session SETs
so a dump still lands in one transaction or not at all.
"""

import subprocess
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_FILTER = _SCRIPTS / "filter_restore_sql.py"
_RESTORE = _SCRIPTS / "restore.sh"

PREAMBLE = """\
SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SELECT 1;
"""


def test_the_filter_drops_transaction_timeout_and_keeps_the_rest() -> None:
    done = subprocess.run(
        [sys.executable, str(_FILTER)],
        input=PREAMBLE,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "transaction_timeout" not in done.stdout
    assert "SET statement_timeout = 0;" in done.stdout
    assert "SET lock_timeout = 0;" in done.stdout
    assert "SET idle_in_transaction_session_timeout = 0;" in done.stdout
    assert "SET client_encoding = 'UTF8';" in done.stdout
    assert "SELECT 1;" in done.stdout


def test_the_filter_does_not_drop_the_word_from_copy_data() -> None:
    """A row that merely mentions the parameter is still data."""
    body = "COPY public.notes (body) FROM stdin;\nSET transaction_timeout = 0;\n\\.\n"
    done = subprocess.run(
        [sys.executable, str(_FILTER)],
        input=body,
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert body == done.stdout


def test_restore_sh_runs_the_dump_through_the_filter() -> None:
    text = _RESTORE.read_text(encoding="utf-8")
    assert "filter_restore_sql.py" in text
    assert "psql" in text
