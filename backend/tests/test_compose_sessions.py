"""Default Compose gives every browser its own operator, with no setup (#82).

The backend and the frontend proxy must share one session secret. Out of the
box that is a public, demo-only value: the backend warns on it at startup, so
it must be exactly the constant the warning knows.
"""

import re
from pathlib import Path

from suas.config import DEMO_SESSION_KEY_SECRET

_ROOT = Path(__file__).resolve().parents[2]
_COMPOSE = (_ROOT / "docker-compose.yml").read_text(encoding="utf-8")


def _default(variable: str) -> str:
    match = re.search(rf"^\s*{variable}: \$\{{SESSION_KEY_SECRET:-([^}}]*)\}}$", _COMPOSE, re.M)
    assert match is not None, f"{variable} is not wired to SESSION_KEY_SECRET"
    return match.group(1)


def test_backend_and_proxy_share_the_demo_secret_by_default() -> None:
    assert _default("SUAS_SESSION_KEY_SECRET") == DEMO_SESSION_KEY_SECRET
    assert _default("BACKEND_SESSION_SECRET") == DEMO_SESSION_KEY_SECRET


def test_the_demo_secret_is_labelled_wherever_it_ships() -> None:
    for path in ("docker-compose.yml", ".env.example", "docs/ops.md", "docs/threat-model.md"):
        text = (_ROOT / path).read_text(encoding="utf-8")
        assert "demo-only" in text.lower(), path
        assert "SESSION_KEY_SECRET" in text, path


def test_ops_warns_that_clearing_cookies_loses_threads() -> None:
    ops = (_ROOT / "docs" / "ops.md").read_text(encoding="utf-8").lower()
    assert "clearing cookies" in ops
