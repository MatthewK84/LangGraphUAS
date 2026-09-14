"""Storing flight logs and applying what they measured.

Ingesting a log and changing the numbers a plan is built on are two different
acts, and this module keeps them separate. Uploading always stores and
estimates; writing a measured figure into an airframe's reference row happens
only when asked for explicitly and only when the estimate clears a sample-count
bar. A measured number is the strongest evidence this system accepts, which is
exactly why it should not arrive as a side effect of a file upload.
"""

import logging
from datetime import UTC, date, datetime
from typing import Any, Final
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from suas.calculations.from_log import (
    PowerEstimate,
    estimate_cruise_power,
    estimate_hover_power,
)
from suas.db.models import AircraftRow, FlightLogRow, FlightLogSampleRow
from suas.errors import FlightLogError
from suas.flight_log_import import ParsedLog, parse_flight_log
from suas.schemas.provenance import Confidence, FieldProvenance, FieldSource

logger: Final[logging.Logger] = logging.getLogger(__name__)

# Below this, an estimate is recorded but never written into reference data.
# Thirty is the bar the plan set for a usable hover figure; anything less is a
# demonstration, not a measurement.
MIN_APPLY_SAMPLES: Final[int] = 30


async def store_flight_log(
    session: AsyncSession,
    *,
    airframe_id: str,
    content: str,
) -> FlightLogRow:
    """Parse, estimate, and persist one uploaded log.

    Raises:
        FlightLogError: when the file cannot be parsed, or an identical file has
            already been ingested.
    """
    parsed: ParsedLog = parse_flight_log(content)
    existing = await _find_by_hash(session, parsed.sha256)
    if existing is not None:
        raise FlightLogError(f"This log was already ingested as {existing.log_id}")

    hover: PowerEstimate | None = estimate_hover_power(parsed.samples)
    cruise: PowerEstimate | None = estimate_cruise_power(parsed.samples)

    row = FlightLogRow(
        log_id=str(uuid4()),
        airframe_id=airframe_id,
        uploaded_at=datetime.now(UTC),
        sha256=parsed.sha256,
        raw_csv=content,
        row_count=parsed.total_rows,
        rejected_rows=parsed.rejected_rows,
        hover_median_w=hover.median_w if hover else None,
        hover_samples=hover.sample_count if hover else None,
        hover_confidence=hover.confidence.value if hover else None,
        cruise_median_w=cruise.median_w if cruise else None,
        cruise_samples=cruise.sample_count if cruise else None,
        cruise_confidence=cruise.confidence.value if cruise else None,
        applied=False,
    )
    session.add(row)
    for sequence, sample in enumerate(parsed.samples):
        session.add(
            FlightLogSampleRow(
                log_id=row.log_id,
                sequence=sequence,
                recorded_at=sample.timestamp,
                alt_m=sample.alt_m,
                power_w=sample.effective_power_w,
                speed_mps=sample.speed_mps,
                phase=sample.phase.value,
            )
        )
    await session.commit()
    logger.info(
        "Ingested flight log %s for %s: %d samples, %d rejected",
        row.log_id,
        airframe_id,
        len(parsed.samples),
        parsed.rejected_rows,
    )
    return row


async def _find_by_hash(session: AsyncSession, sha256: str) -> FlightLogRow | None:
    """Return an already-ingested log with this content hash, if one exists."""
    result = await session.execute(select(FlightLogRow).where(FlightLogRow.sha256 == sha256))
    return result.scalars().first()


def _provenance_for(
    *,
    estimate: PowerEstimate,
    log_id: str,
) -> FieldProvenance:
    """Return the provenance record for a measured power figure."""
    return FieldProvenance(
        value=estimate.median_w,
        unit="W",
        source=FieldSource.FLIGHT_LOG,
        source_url=None,
        retrieved_at=date.today().isoformat(),
        confidence=Confidence(estimate.confidence.value),
        notes=(
            f"Median of {estimate.sample_count} selected samples from log {log_id}. "
            f"Interquartile range {estimate.iqr_w} W."
        ),
    )


async def apply_flight_log(session: AsyncSession, log_id: str) -> list[str]:
    """Write a log's estimates into its airframe, returning the fields changed.

    Only fields whose estimate clears MIN_APPLY_SAMPLES are written. An estimate
    below the bar stays on the log record, where it is visible without being
    load-bearing.

    Raises:
        FlightLogError: when the log or its airframe is unknown.
    """
    log_row: FlightLogRow | None = await session.get(FlightLogRow, log_id)
    if log_row is None:
        raise FlightLogError(f"Unknown flight log: {log_id}")
    aircraft: AircraftRow | None = await session.get(AircraftRow, log_row.airframe_id)
    if aircraft is None:
        raise FlightLogError(f"Unknown airframe: {log_row.airframe_id}")

    provenance: dict[str, Any] = dict(aircraft.provenance or {})
    changed: list[str] = []

    candidates = (
        ("hover_power_w", log_row.hover_median_w, log_row.hover_samples, log_row.hover_confidence),
        (
            "cruise_power_w",
            log_row.cruise_median_w,
            log_row.cruise_samples,
            log_row.cruise_confidence,
        ),
    )
    for field, median_w, samples, confidence in candidates:
        if median_w is None or samples is None or samples < MIN_APPLY_SAMPLES:
            continue
        estimate = PowerEstimate(
            median_w=median_w,
            sample_count=samples,
            iqr_w=0.0,
            confidence=Confidence(confidence or Confidence.LOW.value),
        )
        record = _provenance_for(estimate=estimate, log_id=log_id)
        provenance[field] = record.model_dump(mode="json")
        setattr(aircraft, field, median_w)
        changed.append(field)

    if changed:
        aircraft.provenance = provenance
        log_row.applied = True
        await session.commit()
        logger.info("Applied flight log %s to %s: %s", log_id, aircraft.id, changed)
    return changed
