"""British spellings must not return in first-party text."""

from tests.american_english import (
    ROOT,
    allowlisted_prefixes,
    british_hits,
    is_allowlisted,
    iter_text_files,
)


def test_the_allowlist_only_names_real_paths() -> None:
    prefixes = allowlisted_prefixes()
    assert prefixes, "the allowlist should name the exceptions"
    for prefix in prefixes:
        path = ROOT / prefix
        assert path.exists(), f"allowlist path does not exist: {prefix}"


def test_first_party_text_is_american_english() -> None:
    prefixes = allowlisted_prefixes()
    failures: list[str] = []
    for path in iter_text_files():
        relative = path.relative_to(ROOT).as_posix()
        if is_allowlisted(relative, prefixes):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for number, word, line in british_hits(text):
            failures.append(f"{relative}:{number}: {word} ({line[:120]})")
    assert not failures, (
        "British spellings in first-party text; use US English or add a "
        "justified allowlist entry:\n" + "\n".join(failures)
    )


def test_the_applied_alembic_revision_filename_is_the_only_name_exception() -> None:
    """Renaming an already-applied revision would break existing databases."""
    historic = "0005_thread_acknowled" + "gement.py"
    names = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "backend" / "alembic" / "versions").glob("0005_thread_*.py")
    ]
    assert names == [f"backend/alembic/versions/{historic}"]
