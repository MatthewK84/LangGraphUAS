"""Turn parsed ULog topics into the CSV the flight-log ingest path reads.

This module is the conversion core: it sums battery packs, prefers measured
local position, and emits only the allowlisted CSV columns. It does not read
ULog files; the workstation script in ``scripts/ulog_to_csv.py`` does that with
pyulog and then calls here. Pack serials and vehicle identifiers never enter
these structures, so they cannot appear in the output.
"""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

from suas.errors import FlightLogError

# ULog timestamps are microseconds since boot. The ingest parser requires ISO
# 8601 datetimes; only the deltas matter for climb rate. The origin is
# documented, not a claim about the wall-clock flight time.
_BOOT_ORIGIN: Final[datetime] = datetime(1970, 1, 1, tzinfo=UTC)

# A pack reading further than this from the motion sample is not the same instant.
_ALIGN_TOLERANCE_US: Final[int] = 250_000

# vehicle_land_detected is often near 1 Hz. A motion sample between those flags
# is still on the ground if the last known flag, within this window, is landed.
_LAND_HOLD_US: Final[int] = 2_000_000

CSV_COLUMNS: Final[tuple[str, ...]] = (
    "timestamp",
    "alt_m",
    "power_w",
    "groundspeed_mps",
    "wind_mps",
    "outside_temp_c",
    "payload_id",
)


@dataclass(frozen=True)
class PackReading:
    """Voltage and current from one battery pack at one instant."""

    timestamp_us: int
    voltage_v: float
    current_a: float


@dataclass(frozen=True)
class MotionReading:
    """Altitude and NED velocity at one instant."""

    timestamp_us: int
    alt_m: float
    north_mps: float
    east_mps: float
    down_mps: float

    @property
    def groundspeed_mps(self) -> float:
        """Return horizontal speed, independent of the vertical component."""
        return math.hypot(self.north_mps, self.east_mps)


@dataclass(frozen=True)
class LandedReading:
    """The land-detector flag at one instant."""

    timestamp_us: int
    landed: bool


@dataclass(frozen=True)
class WindReading:
    """Horizontal wind speed at one instant."""

    timestamp_us: int
    wind_mps: float


@dataclass(frozen=True)
class TempReading:
    """Outside air temperature at one instant."""

    timestamp_us: int
    outside_temp_c: float


@dataclass(frozen=True)
class CsvRow:
    """One allowlisted ingest row. ``payload_id`` is always unset here."""

    timestamp: datetime
    alt_m: float
    power_w: float
    groundspeed_mps: float
    wind_mps: float | None
    outside_temp_c: float | None
    payload_id: None = None


def pack_power_w(voltage_v: float, current_a: float) -> float:
    """Return electrical power for one pack. Current may be signed on discharge."""
    return voltage_v * abs(current_a)


def sum_pack_powers(powers: Sequence[float]) -> float:
    """Return the aircraft power as the sum of every pack's contribution."""
    return sum(powers)


def choose_motion(
    local_position: Sequence[MotionReading],
    fallback: Sequence[MotionReading],
) -> Sequence[MotionReading]:
    """Return local position when it has samples, otherwise the baro+EKF fallback."""
    if local_position:
        return local_position
    if fallback:
        return fallback
    raise FlightLogError(
        "ULog has neither vehicle_local_position nor baro altitude plus EKF velocity"
    )


def _nearest(
    readings: Sequence[PackReading]
    | Sequence[LandedReading]
    | Sequence[WindReading]
    | Sequence[TempReading],
    timestamp_us: int,
    cursor: int,
) -> tuple[int, int]:
    """Return the index of the nearest reading and its absolute time gap."""
    if not readings:
        return 0, 10**18
    index = cursor
    while index + 1 < len(readings) and abs(
        readings[index + 1].timestamp_us - timestamp_us
    ) <= abs(readings[index].timestamp_us - timestamp_us):
        index += 1
    return index, abs(readings[index].timestamp_us - timestamp_us)


def _datetime_for(timestamp_us: int) -> datetime:
    """Render a boot-relative microsecond timestamp as an aware UTC datetime."""
    return _BOOT_ORIGIN + timedelta(microseconds=timestamp_us)


def _is_landed(
    landed: Sequence[LandedReading], timestamp_us: int, cursor: int
) -> tuple[int, bool]:
    """Return whether the last known land-detector flag at this instant is landed."""
    index = cursor
    while index + 1 < len(landed) and landed[index + 1].timestamp_us <= timestamp_us:
        index += 1
    candidate = landed[index]
    gap = abs(timestamp_us - candidate.timestamp_us)
    if gap > _LAND_HOLD_US:
        return index, False
    return index, bool(candidate.landed)


def _sum_aligned_pack_power(
    packs: Sequence[Sequence[PackReading]],
    timestamp_us: int,
    cursors: list[int],
) -> float | None:
    """Return summed pack power when every pack has a reading in the window."""
    powers: list[float] = []
    for pack_index, series in enumerate(packs):
        cursors[pack_index], gap = _nearest(series, timestamp_us, cursors[pack_index])
        if gap > _ALIGN_TOLERANCE_US:
            return None
        reading = series[cursors[pack_index]]
        powers.append(pack_power_w(reading.voltage_v, reading.current_a))
    return sum_pack_powers(powers)


def _aligned_optional(
    readings: Sequence[WindReading] | Sequence[TempReading],
    timestamp_us: int,
    cursor: int,
) -> tuple[int, WindReading | TempReading | None]:
    """Return the nearest optional reading when it falls inside the pack window."""
    if not readings:
        return cursor, None
    index, gap = _nearest(readings, timestamp_us, cursor)
    if gap > _ALIGN_TOLERANCE_US:
        return index, None
    return index, readings[index]


@dataclass
class _Cursors:
    """Walk-once alignment cursors for one conversion pass."""

    packs: list[int]
    landed: int = 0
    wind: int = 0
    temperature: int = 0


def _row_for_sample(
    sample: MotionReading,
    packs: Sequence[Sequence[PackReading]],
    landed: Sequence[LandedReading],
    wind: Sequence[WindReading],
    temperatures: Sequence[TempReading],
    cursors: _Cursors,
) -> CsvRow | None:
    """Return one ingest row, or None when the sample is landed or unaligned."""
    if landed:
        cursors.landed, on_ground = _is_landed(landed, sample.timestamp_us, cursors.landed)
        if on_ground:
            return None
    power = _sum_aligned_pack_power(packs, sample.timestamp_us, cursors.packs)
    if power is None:
        return None
    cursors.wind, wind_row = _aligned_optional(wind, sample.timestamp_us, cursors.wind)
    cursors.temperature, temp_row = _aligned_optional(
        temperatures, sample.timestamp_us, cursors.temperature
    )
    return CsvRow(
        timestamp=_datetime_for(sample.timestamp_us),
        alt_m=sample.alt_m,
        power_w=power,
        groundspeed_mps=sample.groundspeed_mps,
        wind_mps=wind_row.wind_mps if isinstance(wind_row, WindReading) else None,
        outside_temp_c=temp_row.outside_temp_c if isinstance(temp_row, TempReading) else None,
    )


def rows_from_topics(
    *,
    packs: Sequence[Sequence[PackReading]],
    motion: Sequence[MotionReading],
    fallback_motion: Sequence[MotionReading] = (),
    landed: Sequence[LandedReading] = (),
    wind: Sequence[WindReading] = (),
    temperatures: Sequence[TempReading] = (),
) -> list[CsvRow]:
    """Align packs onto motion samples and return ingest rows, skipping landings."""
    if not packs:
        raise FlightLogError("ULog has no battery_status voltage and current")
    chosen = choose_motion(motion, fallback_motion)
    cursors = _Cursors(packs=[0] * len(packs))
    rows: list[CsvRow] = []
    for sample in chosen:
        row = _row_for_sample(sample, packs, landed, wind, temperatures, cursors)
        if row is not None:
            rows.append(row)
    if not rows:
        raise FlightLogError("ULog produced no in-air samples with power and motion")
    return rows


def to_csv(rows: Sequence[CsvRow]) -> str:
    """Return the ingest CSV. ``payload_id`` is written as an empty cell."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(CSV_COLUMNS), lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                "timestamp": row.timestamp.isoformat(),
                "alt_m": f"{row.alt_m:.6f}",
                "power_w": f"{row.power_w:.6f}",
                "groundspeed_mps": f"{row.groundspeed_mps:.6f}",
                "wind_mps": "" if row.wind_mps is None else f"{row.wind_mps:.6f}",
                "outside_temp_c": ""
                if row.outside_temp_c is None
                else f"{row.outside_temp_c:.6f}",
                "payload_id": "",
            }
        )
    return buffer.getvalue()
