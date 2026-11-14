"""The pinned Blue UAS snapshot.

Clearance enters the system only as a hashed, time-stamped file fetched
out-of-band. The operational gate reads this snapshot and nothing else; a
request-path scrape never decides whether a configuration is current. See
ADR-002.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, Final

from suas.reference_data import DATA_DIR

# ADR-002. Exposed so Settings and docs share one default; the gate itself
# takes the configured value rather than this number.
DEFAULT_BLUE_LIST_MAX_AGE_S: Final[float] = 7 * 24 * 3600

DEFAULT_SNAPSHOT_PATH: Final[Path] = DATA_DIR / "blue_list_snapshot.json"

_HASH_PREFIX: Final[str] = "sha256:"


def compute_items_hash(items: list[dict[str, Any]] | tuple[dict[str, Any], ...]) -> str:
    """Return a stable sha256 of the snapshot items, prefixed for display."""
    encoded = json.dumps(list(items), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{_HASH_PREFIX}{sha256(encoded).hexdigest()}"


def snapshot_fetched_at(payload: dict[str, Any]) -> datetime | None:
    """Return the snapshot's timestamp, or None when it cannot be aged honestly."""
    raw = payload.get("fetched_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        fetched_at = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if fetched_at.tzinfo is None:
        return None
    return fetched_at.astimezone(UTC)


@dataclass(frozen=True)
class BlueListSnapshot:
    """A hashed, time-stamped Blue UAS snapshot as stored on disk."""

    fetched_at: datetime | None
    source_url: str
    content_hash: str
    items: tuple[dict[str, Any], ...]
    hash_matches: bool

    @property
    def usable_fetched_at(self) -> datetime | None:
        """Return the timestamp only when the hash checks out and the date is known."""
        if not self.hash_matches:
            return None
        return self.fetched_at


def load_snapshot(path: Path) -> BlueListSnapshot | None:
    """Return the snapshot at path, or None when the file is missing or unreadable."""
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    items = payload.get("items", [])
    if not isinstance(items, list):
        return None
    recorded = payload.get("content_hash")
    computed = compute_items_hash(items)
    source = payload.get("source_url")
    return BlueListSnapshot(
        fetched_at=snapshot_fetched_at(payload),
        source_url=source if isinstance(source, str) else "",
        content_hash=computed if not isinstance(recorded, str) else recorded,
        items=tuple(item for item in items if isinstance(item, dict)),
        hash_matches=isinstance(recorded, str) and recorded == computed,
    )


def write_snapshot(
    path: Path,
    *,
    items: list[dict[str, Any]],
    source_url: str,
    fetched_at: datetime,
) -> BlueListSnapshot:
    """Write a hashed snapshot and return what was stored."""
    content_hash = compute_items_hash(items)
    payload = {
        "fetched_at": fetched_at.astimezone(UTC).isoformat().replace("+00:00", "Z"),
        "source_url": source_url,
        "content_hash": content_hash,
        "items": items,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return BlueListSnapshot(
        fetched_at=fetched_at.astimezone(UTC),
        source_url=source_url,
        content_hash=content_hash,
        items=tuple(items),
        hash_matches=True,
    )


def refresh_from_file(source: Path, dest: Path, *, fetched_at: datetime) -> BlueListSnapshot:
    """Build a pinned snapshot from a local public JSON file. Ingest is deliberate."""
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Blue-list source must be a JSON object with an items list")
    items = payload.get("items")
    if not isinstance(items, list):
        raise ValueError("Blue-list source must include an items list")
    source_url = payload.get("source_url")
    if not isinstance(source_url, str) or not source_url:
        source_url = f"file:{source}"
    clean_items = [item for item in items if isinstance(item, dict)]
    return write_snapshot(dest, items=clean_items, source_url=source_url, fetched_at=fetched_at)


def configured_snapshot_path(explicit: str) -> Path:
    """Return the configured snapshot path, or the default under the data dir."""
    if explicit:
        return Path(explicit)
    return DEFAULT_SNAPSHOT_PATH
