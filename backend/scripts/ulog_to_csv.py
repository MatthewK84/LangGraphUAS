#!/usr/bin/env python3
"""Convert a PX4 ULog file into the CSV that ``POST /api/logs`` accepts.

The script is a workstation tool. It is not on the API request path. pyulog
reads the file; ``suas.ulog_csv`` does the summing, alignment, and redaction.
Pack serials, vehicle UUIDs, and any other identifier stay in the ULog; they
are never copied into the CSV.

Usage:
    python scripts/ulog_to_csv.py flight.ulg flight.csv
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

from suas.ulog_csv import (
    LandedReading,
    MotionReading,
    PackReading,
    TempReading,
    WindReading,
    rows_from_topics,
    to_csv,
)


@runtime_checkable
class _Dataset(Protocol):
    """The pyulog dataset surface this script reads."""

    name: str
    multi_id: int
    data: Mapping[str, Sequence[object]]


@runtime_checkable
class _ULog(Protocol):
    """The pyulog file surface this script reads."""

    data_list: Sequence[_Dataset]


def _series(dataset: _Dataset, field: str) -> list[object]:
    """Return one field of a pyulog dataset as a Python list."""
    values: list[object] = []
    for value in dataset.data[field]:
        item = getattr(value, "item", None)
        values.append(item() if callable(item) else value)
    return values


def _dataset(ulog: _ULog, name: str) -> _Dataset | None:
    """Return the first instance of a topic, or None when it was not logged."""
    for dataset in ulog.data_list:
        if dataset.name == name and dataset.multi_id == 0:
            return dataset
    return None


def _pack_readings(ulog: _ULog) -> list[list[PackReading]]:
    """Collect every battery_status instance that carries voltage and current."""
    packs: list[list[PackReading]] = []
    for dataset in ulog.data_list:
        if dataset.name != "battery_status":
            continue
        if "voltage_v" not in dataset.data or "current_a" not in dataset.data:
            continue
        stamps = _series(dataset, "timestamp")
        volts = _series(dataset, "voltage_v")
        amps = _series(dataset, "current_a")
        packs.append(
            [
                PackReading(int(stamp), float(volt), float(amp))
                for stamp, volt, amp in zip(stamps, volts, amps, strict=True)
            ]
        )
    return packs


def _motion_from_local_position(ulog: _ULog) -> list[MotionReading]:
    """Return motion from vehicle_local_position, whose z axis is NED down."""
    dataset = _dataset(ulog, "vehicle_local_position")
    if dataset is None or "z" not in dataset.data or "vx" not in dataset.data:
        return []
    rows: list[MotionReading] = []
    for stamp, z_down, north, east, down in zip(
        _series(dataset, "timestamp"),
        _series(dataset, "z"),
        _series(dataset, "vx"),
        _series(dataset, "vy"),
        _series(dataset, "vz"),
        strict=True,
    ):
        rows.append(
            MotionReading(
                int(stamp),
                alt_m=-float(z_down),
                north_mps=float(north),
                east_mps=float(east),
                down_mps=float(down),
            )
        )
    return rows


def _motion_from_baro_and_ekf(ulog: _ULog) -> list[MotionReading]:
    """Return motion using baro altitude and EKF velocity states 4, 5, and 6."""
    baro = _dataset(ulog, "vehicle_air_data")
    ekf = _dataset(ulog, "estimator_states")
    if baro is None or ekf is None or "baro_alt_meter" not in baro.data:
        return []
    if "states[4]" not in ekf.data or "states[5]" not in ekf.data or "states[6]" not in ekf.data:
        return []
    ekf_stamps = _series(ekf, "timestamp")
    norths = _series(ekf, "states[4]")
    easts = _series(ekf, "states[5]")
    downs = _series(ekf, "states[6]")
    baro_stamps = _series(baro, "timestamp")
    alts = _series(baro, "baro_alt_meter")
    rows: list[MotionReading] = []
    cursor = 0
    for stamp, north, east, down in zip(ekf_stamps, norths, easts, downs, strict=True):
        while cursor + 1 < len(baro_stamps) and abs(
            int(baro_stamps[cursor + 1]) - int(stamp)
        ) <= abs(int(baro_stamps[cursor]) - int(stamp)):
            cursor += 1
        if abs(int(baro_stamps[cursor]) - int(stamp)) > 250_000:
            continue
        rows.append(
            MotionReading(
                int(stamp),
                alt_m=float(alts[cursor]),
                north_mps=float(north),
                east_mps=float(east),
                down_mps=float(down),
            )
        )
    return rows


def _landed(ulog: _ULog) -> list[LandedReading]:
    """Return land-detector flags when the topic is present."""
    dataset = _dataset(ulog, "vehicle_land_detected")
    if dataset is None or "landed" not in dataset.data:
        return []
    return [
        LandedReading(int(stamp), bool(flag))
        for stamp, flag in zip(
            _series(dataset, "timestamp"), _series(dataset, "landed"), strict=True
        )
    ]


def _wind(ulog: _ULog) -> list[WindReading]:
    """Return horizontal wind speed when the wind topic is present."""
    dataset = _dataset(ulog, "wind")
    if (
        dataset is None
        or "windspeed_north" not in dataset.data
        or "windspeed_east" not in dataset.data
    ):
        return []
    return [
        WindReading(int(stamp), math.hypot(float(north), float(east)))
        for stamp, north, east in zip(
            _series(dataset, "timestamp"),
            _series(dataset, "windspeed_north"),
            _series(dataset, "windspeed_east"),
            strict=True,
        )
    ]


def _temperatures(ulog: _ULog) -> list[TempReading]:
    """Return barometric temperature when it is logged."""
    dataset = _dataset(ulog, "vehicle_air_data")
    if dataset is None or "baro_temp_celcius" not in dataset.data:
        return []
    return [
        TempReading(int(stamp), float(temp))
        for stamp, temp in zip(
            _series(dataset, "timestamp"),
            _series(dataset, "baro_temp_celcius"),
            strict=True,
        )
    ]


def convert_ulog_file(source: Path) -> str:
    """Return ingest CSV for one ULog file, with identifiers left behind."""
    from pyulog import ULog

    ulog = ULog(str(source), disable_str_exceptions=True)
    rows = rows_from_topics(
        packs=_pack_readings(ulog),
        motion=_motion_from_local_position(ulog),
        fallback_motion=_motion_from_baro_and_ekf(ulog),
        landed=_landed(ulog),
        wind=_wind(ulog),
        temperatures=_temperatures(ulog),
    )
    return to_csv(rows)


def main(argv: list[str] | None = None) -> int:
    """Convert the ULog path in argv[1] and write CSV to argv[2]."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ulog", type=Path, help="Input .ulg file")
    parser.add_argument("csv", type=Path, help="Output .csv path")
    args = parser.parse_args(argv)
    if not args.ulog.is_file():
        print(f"No such ULog file: {args.ulog}", file=sys.stderr)
        return 2
    args.csv.write_text(convert_ulog_file(args.ulog), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
