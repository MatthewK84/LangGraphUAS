"""The corpus allowlist.

Nothing enters the corpus because it happens to be on disk. A file is ingested
only if the manifest names it, its bytes hash to what the manifest recorded, and
its stated origin is a host we are willing to treat as a source. The manifest is
reviewed like code, which is the point: adding a document to this system is a
commit somebody signs off, not a file copy.
"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final
from urllib.parse import urlparse

from suas.errors import SuasError

# Hosts whose documents may become corpus entries. Manufacturer domains for the
# airframes in the reference pack, plus the two authorities for clearance.
ALLOWED_HOSTS: Final[frozenset[str]] = frozenset(
    {
        "bluelist.dcma.mil",
        "diu.mil",
        "docs.freeflysystems.com",
        "freeflysystems.com",
        "docs.inspiredflight.com",
        "shop.inspiredflight.com",
        "www.parrot.com",
        "parrot.com",
        "support.skydio.com",
        "www.skydio.com",
        "skydio.com",
        "tealdrones.com",
        "www.tealdrones.com",
    }
)

DOCUMENT_KINDS: Final[frozenset[str]] = frozenset(
    {"datasheet", "blue_list", "procedure", "eval_trap"}
)

# Never ingested by the production path, whatever the manifest says. Trap
# documents exist to be retrieved in the evaluation harness and nowhere else.
PRODUCTION_FORBIDDEN_KINDS: Final[frozenset[str]] = frozenset({"eval_trap"})


class ManifestError(SuasError):
    """Raised when a corpus file is not one the manifest vouches for."""


@dataclass(frozen=True)
class ManifestEntry:
    """One document the manifest permits."""

    path: str
    sha256: str
    source_url: str
    retrieved_at: str
    kind: str
    airframe_config_id: str | None = None
    license: str = ""

    @property
    def host(self) -> str:
        """Return the host of the stated origin."""
        return urlparse(self.source_url).netloc.lower()


def load_manifest(manifest_path: Path) -> dict[str, ManifestEntry]:
    """Return the manifest keyed by path, or raise ManifestError."""
    try:
        raw: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"Cannot read corpus manifest at {manifest_path}") from exc

    entries: dict[str, ManifestEntry] = {}
    for item in raw.get("documents", []):
        entry = ManifestEntry(**item)
        if entry.kind not in DOCUMENT_KINDS:
            raise ManifestError(f"{entry.path}: unknown kind {entry.kind!r}")
        if entry.host not in ALLOWED_HOSTS:
            raise ManifestError(f"{entry.path}: source host {entry.host!r} is not allowed")
        entries[entry.path] = entry
    return entries


def verify(entry: ManifestEntry, content: bytes, *, production: bool) -> None:
    """Check one file against its manifest entry.

    Raises:
        ManifestError: when the bytes do not match the recorded hash, or the
            document's kind is one production must never ingest.
    """
    if production and entry.kind in PRODUCTION_FORBIDDEN_KINDS:
        raise ManifestError(f"{entry.path}: kind {entry.kind!r} is eval-only")
    digest: str = hashlib.sha256(content).hexdigest()
    if digest != entry.sha256:
        raise ManifestError(
            f"{entry.path}: content hash {digest[:16]} does not match the manifest"
        )


def resolve(entries: dict[str, ManifestEntry], path: str) -> ManifestEntry:
    """Return the entry for a path, or raise ManifestError if it is not listed."""
    entry = entries.get(path)
    if entry is None:
        raise ManifestError(f"{path} is not in the corpus manifest")
    return entry
