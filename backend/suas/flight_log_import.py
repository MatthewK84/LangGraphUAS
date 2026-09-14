"""Parsing an uploaded flight log.

An uploaded file is untrusted input, and a CSV is a particularly soft one: its
header row is attacker-controlled text and its cells are arbitrary. This module
is the boundary. Only the columns below are read, every value is coerced to a
number or an enum, and anything else in the file is ignored rather than carried
forward. See docs/injection-defense.md.

Rows that cannot be parsed are counted and reported rather than silently
dropped: a log that is half unreadable should tell its uploader so, not quietly
produce an estimate from the half that survived.
"""

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from pydantic import ValidationError

from suas.errors import FlightLogError
from suas.schemas.flight_log import FlightLogSample, FlightPhase

# Bounds on what will be accepted at all. A log larger than this is a different
# problem than the one this endpoint solves.
MAX_BYTES: Final[int] = 5 * 1024 * 1024
MAX_ROWS: Final[int] = 100_000

# The only columns read. Everything else in the file is ignored.
NUMERIC_COLUMNS: Final[frozenset[str]] = frozenset(
    {
        "alt_m",
        "power_w",
        "voltage_v",
        "current_a",
        "tas_mps",
        "groundspeed_mps",
        "wind_mps",
        "outside_temp_c",
    }
)


@dataclass(frozen=True)
class ParsedLog:
    """A parsed flight log and what was discarded getting there."""

    samples: list[FlightLogSample]
    rejected_rows: int
    sha256: str

    @property
    def total_rows(self) -> int:
        """Return how many data rows the file contained."""
        return len(self.samples) + self.rejected_rows


def _coerce_number(raw: str) -> float | None:
    """Return a float, or None when the cell is blank or not a number."""
    text: str = raw.strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_phase(raw: str | None) -> FlightPhase:
    """Return the declared phase, defaulting to unknown for anything unrecognised."""
    if raw is None:
        return FlightPhase.UNKNOWN
    try:
        return FlightPhase(raw.strip().lower())
    except ValueError:
        return FlightPhase.UNKNOWN


def _build_row(row: dict[str, str]) -> dict[str, Any]:
    """Return the allowlisted fields of one CSV row, coerced to their types."""
    built: dict[str, Any] = {}
    for column in NUMERIC_COLUMNS:
        value = row.get(column)
        if value is not None:
            built[column] = _coerce_number(value)
    built["phase"] = _coerce_phase(row.get("phase"))
    payload_id = (row.get("payload_id") or "").strip()
    # Bounded, so a crafted cell cannot become an unbounded string on the record.
    built["payload_id"] = payload_id[:100] or None
    built["timestamp"] = (row.get("timestamp") or "").strip()
    return built


def parse_flight_log(content: str) -> ParsedLog:
    """Return the samples in a CSV flight log.

    Raises:
        FlightLogError: when the file is too large, has no usable header, or
            contains no parsable rows at all.
    """
    encoded: bytes = content.encode("utf-8")
    if len(encoded) > MAX_BYTES:
        raise FlightLogError(f"Flight log exceeds {MAX_BYTES} bytes")

    reader = csv.DictReader(io.StringIO(content))
    if reader.fieldnames is None:
        raise FlightLogError("Flight log has no header row")
    if "timestamp" not in reader.fieldnames or "alt_m" not in reader.fieldnames:
        raise FlightLogError("Flight log must have at least timestamp and alt_m columns")

    samples: list[FlightLogSample] = []
    rejected: int = 0
    for index, row in enumerate(reader):
        if index >= MAX_ROWS:
            raise FlightLogError(f"Flight log exceeds {MAX_ROWS} rows")
        try:
            samples.append(FlightLogSample.model_validate(_build_row(row)))
        except (ValidationError, ValueError):
            rejected += 1

    if not samples:
        raise FlightLogError("Flight log contained no parsable rows")

    samples.sort(key=_sample_time)
    return ParsedLog(
        samples=samples,
        rejected_rows=rejected,
        sha256=hashlib.sha256(encoded).hexdigest(),
    )


def _sample_time(sample: FlightLogSample) -> datetime:
    """Return a sample's timestamp, for ordering."""
    return sample.timestamp
