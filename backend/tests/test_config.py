"""Settings normalisation.

The database URL is the one setting a person pastes in from another system, so
it is the one most likely to arrive in a shape the application cannot use.
"""

import pytest
from pydantic import ValidationError

from suas.config import Settings, describe_database_url, normalise_database_url

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


# --- describe_database_url ---------------------------------------------------


def test_the_description_drops_credentials() -> None:
    """This string goes into logs, which get pasted into issues and screenshots."""
    described: str = describe_database_url(
        "postgresql+psycopg://suas:s3cret@containers.railway.app:5432/railway"
    )

    assert described == "postgresql+psycopg://containers.railway.app:5432/railway"
    assert "s3cret" not in described
    assert "suas:" not in described


def test_a_password_containing_an_at_sign_is_still_dropped() -> None:
    """Splitting on the first '@' would leak the tail of such a password."""
    described: str = describe_database_url("postgresql+psycopg://u:p@ss@host:5432/db")

    assert described == "postgresql+psycopg://host:5432/db"
    assert "p@ss" not in described


def test_a_url_without_credentials_is_preserved() -> None:
    assert describe_database_url("sqlite+aiosqlite:///./suas_local.db") == (
        "sqlite+aiosqlite:///./suas_local.db"
    )


def test_a_malformed_url_does_not_raise() -> None:
    """Logging runs before anything validates the URL, so it must not be the
    thing that crashes startup."""
    assert describe_database_url("notaurl") == "notaurl"
    assert describe_database_url("") == ""


# --- require_postgres and the DATABASE_URL fallback --------------------------


def test_the_container_refuses_to_start_on_sqlite() -> None:
    """The image sets SUAS_REQUIRE_POSTGRES=true, so this is the deployed path."""
    with pytest.raises(ValidationError) as caught:
        Settings(require_postgres=True, database_url="sqlite+aiosqlite:///./x.db")

    message = str(caught.value)
    assert "SUAS_DATABASE_URL" in message, "the error must name the missing variable"
    assert "Postgres" in message


def test_the_refusal_does_not_leak_the_password() -> None:
    with pytest.raises(ValidationError) as caught:
        Settings(require_postgres=True, database_url="mysql://u:s3cret@h/db")

    assert "s3cret" not in str(caught.value)


def test_postgres_satisfies_the_requirement() -> None:
    settings = Settings(require_postgres=True, database_url="postgresql://u:p@h/db")

    assert settings.uses_postgres
    assert settings.database_url.startswith("postgresql+psycopg://")


def test_sqlite_remains_fine_when_not_required() -> None:
    """Local development and this test suite depend on it."""
    assert not Settings().uses_postgres


def test_the_conventional_database_url_is_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """Railway and Heroku set DATABASE_URL, not SUAS_DATABASE_URL."""
    monkeypatch.delenv("SUAS_DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@rail:5432/railway")

    assert Settings().database_url == "postgresql+psycopg://u:p@rail:5432/railway"


def test_the_prefixed_name_wins_over_the_conventional_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Both are often present; ours is the one the operator set deliberately."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@conventional/db")
    monkeypatch.setenv("SUAS_DATABASE_URL", "postgresql://u:p@explicit/db")

    assert Settings().database_url == "postgresql+psycopg://u:p@explicit/db"
