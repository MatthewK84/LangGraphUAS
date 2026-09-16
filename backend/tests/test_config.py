"""Settings normalisation.

The database URL is the one setting a person pastes in from another system, so
it is the one most likely to arrive in a shape the application cannot use.
"""

import pytest

from suas.config import Settings, normalise_database_url

# What Railway's ${{Postgres.DATABASE_URL}} and Heroku-style providers hand out,
# against what SQLAlchemy needs to reach an async psycopg3 driver.
PROVIDER_URLS: list[tuple[str, str]] = [
    (
        "postgresql://suas:pw@containers.railway.app:5432/railway",
        "postgresql+psycopg://suas:pw@containers.railway.app:5432/railway",
    ),
    (
        "postgres://suas:pw@containers.railway.app:5432/railway",
        "postgresql+psycopg://suas:pw@containers.railway.app:5432/railway",
    ),
]


@pytest.mark.parametrize(("provided", "expected"), PROVIDER_URLS)
def test_a_provider_url_gains_the_async_driver(provided: str, expected: str) -> None:
    assert normalise_database_url(provided) == expected


def test_normalisation_is_idempotent() -> None:
    """Re-pasting an already-corrected URL must not corrupt it."""
    once: str = normalise_database_url(PROVIDER_URLS[0][0])
    assert normalise_database_url(once) == once


def test_a_url_that_already_names_a_driver_is_untouched() -> None:
    url = "postgresql+asyncpg://u:p@h/db"
    assert normalise_database_url(url) == url


def test_sqlite_is_untouched() -> None:
    url = "sqlite+aiosqlite:///./suas_local.db"
    assert normalise_database_url(url) == url


def test_the_password_is_not_mangled() -> None:
    """Only the scheme is rewritten; a password containing '//' survives."""
    provided = "postgresql://u:pa//ss@h:5432/db"
    assert normalise_database_url(provided) == "postgresql+psycopg://u:pa//ss@h:5432/db"


def test_settings_applies_the_normalisation() -> None:
    settings = Settings(database_url="postgresql://u:p@h:5432/db")

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.uses_postgres


def test_a_bare_postgres_scheme_is_recognised_as_postgres() -> None:
    """`postgres://` previously read as not-Postgres, silently skipping the
    Postgres-only code paths (checkpointer, pool settings)."""
    assert Settings(database_url="postgres://u:p@h/db").uses_postgres
