"""Every module that can call out of the process has a threat-model row (#90).

A processor (LangSmith, object storage, an embedder API) moves data across a
trust boundary, and that analysis is worth nothing once the client is already
calling out. So any module in ``suas`` that imports a network client must be
registered here against the STRIDE row in ``docs/threat-model.md`` that covers
it; a new one fails until both exist.
"""

import ast
from pathlib import Path
from typing import Final

BACKEND: Final[Path] = Path(__file__).resolve().parent.parent
REPO: Final[Path] = BACKEND.parent
THREAT_MODEL: Final[Path] = REPO / "docs" / "threat-model.md"

# Imports that can open a connection to somewhere else.
EGRESS: Final[frozenset[str]] = frozenset(
    {
        "aiohttp",
        "boto3",
        "botocore",
        "ftplib",
        "http.client",
        "httpx",
        "langchain_openai",
        "langsmith",
        "openai",
        "requests",
        "smtplib",
        "socket",
        "urllib.request",
        "urllib3",
    }
)

# Module -> the start of the threat-model row that covers its destination.
PROCESSORS: Final[dict[str, str]] = {
    "suas/services/weather.py": 'Forged "live" weather',
    "suas/services/llm.py": "Advisory flipped to operational by the model",
    "suas/rag/embedding.py": "Mass plan requests with model and embedding calls",
    "suas/rag/provider.py": "Mass plan requests with model and embedding calls",
    "suas/tracing.py": "Mission coordinates and raw briefs sent to LangSmith",
}
# Modules that import a client without a destination of their own.
NO_DESTINATION: Final[dict[str, str]] = {
    "suas/main.py": "builds the one httpx client weather and the embedder share",
}

RULE: Final[str] = (
    "add a STRIDE row to docs/threat-model.md for the new destination and "
    "register the module in tests/test_processor_rows.py in the same PR"
)


def _imports(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def _is_egress(name: str) -> bool:
    return any(name == e or name.startswith(f"{e}.") for e in EGRESS)


def egress_modules(root: Path) -> set[str]:
    """Every module under ``root/suas`` that imports a network client."""
    return {
        path.relative_to(root).as_posix()
        for path in sorted((root / "suas").rglob("*.py"))
        if any(_is_egress(name) for name in _imports(path.read_text(encoding="utf-8")))
    }


def _row_starts() -> list[str]:
    return [
        line.removeprefix("|").strip()
        for line in THREAT_MODEL.read_text(encoding="utf-8").splitlines()
        if line.startswith("| ")
    ]


def test_every_module_that_calls_out_is_registered() -> None:
    unregistered = egress_modules(BACKEND) - PROCESSORS.keys() - NO_DESTINATION.keys()

    assert not unregistered, f"{sorted(unregistered)} can call out: {RULE}"


def test_every_registered_processor_still_calls_out() -> None:
    """A stale entry would hide that the registry no longer matches the code."""
    stale = (PROCESSORS.keys() | NO_DESTINATION.keys()) - egress_modules(BACKEND)

    assert not stale


def test_every_processor_points_at_a_real_threat_model_row() -> None:
    rows = _row_starts()

    missing = {
        module: threat
        for module, threat in PROCESSORS.items()
        if not any(row.startswith(threat) for row in rows)
    }

    assert not missing, f"no threat-model row starts with {missing}"


def test_a_new_client_import_is_caught(tmp_path: Path) -> None:
    (tmp_path / "suas" / "storage").mkdir(parents=True)
    (tmp_path / "suas" / "storage" / "s3.py").write_text("import boto3\n")
    (tmp_path / "suas" / "parse.py").write_text("from urllib.parse import urlparse\n")
    (tmp_path / "suas" / "fetch.py").write_text("from httpx import AsyncClient\n")

    assert egress_modules(tmp_path) == {"suas/storage/s3.py", "suas/fetch.py"}


def test_the_rule_is_written_where_reviewers_read() -> None:
    practices = (REPO / "docs" / "engineering-practices.md").read_text(encoding="utf-8")
    threat_model = THREAT_MODEL.read_text(encoding="utf-8")

    for text in (practices, threat_model):
        assert "tests/test_processor_rows.py" in text
