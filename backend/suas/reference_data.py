"""Loading the bundled reference data.

The JSON files are the source of truth and are written in the provenance shape:
every numeric field is an object carrying its value, unit, and where it came
from. Runtime code wants plain floats, so this module is the one place that
flattens the two apart -- values for the calculator, provenance for the gate and
the citation inventory.

Parsing is strict. ``FieldProvenance`` forbids unknown keys and requires a unit
and a source, so a hand-edited file that drops provenance fails here rather than
silently seeding a number nobody can account for.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from pydantic import ValidationError

from suas.errors import SeedDataError
from suas.schemas.provenance import FieldProvenance

DATA_DIR: Final[Path] = Path(__file__).resolve().parent / "data"
AIRCRAFT_FILE: Final[str] = "aircraft.json"
PAYLOAD_FILE: Final[str] = "payloads.json"

_IDENTITY_FIELDS: Final[frozenset[str]] = frozenset({"id", "name"})


@dataclass(frozen=True)
class ReferenceEntry:
    """One airframe or payload, with its numbers and their provenance."""

    id: str
    name: str
    values: dict[str, float]
    provenance: dict[str, FieldProvenance]

    def as_row(self) -> dict[str, Any]:
        """Return the flat mapping used to build an ORM row."""
        return {
            "id": self.id,
            "name": self.name,
            **self.values,
            "provenance": {
                field: record.model_dump(mode="json") for field, record in self.provenance.items()
            },
        }


def _parse_entry(key: str, raw: dict[str, Any]) -> ReferenceEntry:
    """Return one parsed entry, or raise SeedDataError naming the bad field."""
    values: dict[str, float] = {}
    provenance: dict[str, FieldProvenance] = {}
    for field, cell in raw.items():
        if field in _IDENTITY_FIELDS:
            continue
        if not isinstance(cell, dict):
            raise SeedDataError(
                f"{key}.{field} is a bare value. Every number carries provenance; "
                "see suas/schemas/provenance.py."
            )
        try:
            record = FieldProvenance.model_validate(cell)
        except ValidationError as exc:
            raise SeedDataError(f"{key}.{field} has invalid provenance: {exc}") from exc
        values[field] = record.value
        provenance[field] = record
    return ReferenceEntry(
        id=str(raw["id"]), name=str(raw["name"]), values=values, provenance=provenance
    )


def load_entries(filename: str) -> list[ReferenceEntry]:
    """Return every entry in a bundled reference file."""
    path: Path = DATA_DIR / filename
    try:
        raw: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SeedDataError(f"Cannot load reference file {filename}") from exc
    return [_parse_entry(key, entry) for key, entry in raw.items()]


def load_rows(filename: str) -> list[dict[str, Any]]:
    """Return reference entries flattened into ORM row mappings."""
    return [entry.as_row() for entry in load_entries(filename)]
