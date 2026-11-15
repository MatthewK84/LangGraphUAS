"""ULog-to-CSV conversion: pack summing, position fallback, and redaction.

The constructor below writes a tiny, synthetic ULog so the adapter can be
tested without shipping a multi-megabyte flight file. It measures nothing
about any aircraft. The real Astro excerpt lives in fixtures/logs/ and is
covered by test_flight_log.py.
"""

from __future__ import annotations

import struct
from datetime import UTC, datetime
from pathlib import Path

import pytest

from suas.errors import FlightLogError
from suas.ulog_csv import (
    LandedReading,
    MotionReading,
    PackReading,
    TempReading,
    rows_from_topics,
    to_csv,
)

PLANTED_IDENTIFIER = "SECRETXX"


def _msg(msg_type: int, payload: bytes) -> bytes:
    return struct.pack("<HB", len(payload), msg_type) + payload


def write_min_ulog(
    path: Path,
    *,
    include_local_position: bool = True,
    include_fallback: bool = True,
    packs: tuple[tuple[float, float], ...] = ((22.0, 10.0), (22.0, 11.0)),
    landed: bool = False,
    samples: int = 5,
    dt_us: int = 1_000_000,
    vz: float = 0.0,
    vx: float = 0.1,
    alt_m: float = 10.0,
) -> None:
    """Write a minimal ULog that pyulog can read, for converter tests only."""
    header = b"\x55\x4c\x6f\x67\x01\x12\x35"
    buf = bytearray(header + struct.pack("B", 1) + struct.pack("<Q", 1_000_000))
    buf.extend(_msg(ord("B"), bytes(8 + 8 + 24)))
    formats = [
        b"battery_status:uint64_t timestamp;float voltage_v;float current_a;",
        b"vehicle_local_position:uint64_t timestamp;float x;float y;float z;"
        b"float vx;float vy;float vz;",
        b"vehicle_air_data:uint64_t timestamp;float baro_alt_meter;float baro_temp_celcius;",
        b"estimator_states:uint64_t timestamp;float[10] states;",
        b"vehicle_land_detected:uint64_t timestamp;uint8_t landed;",
        b"battery_info:uint64_t timestamp;uint8_t[8] serial_number;",
    ]
    for fmt in formats:
        buf.extend(_msg(ord("F"), fmt))

    def add_logged(multi: int, msg_id: int, name: str) -> bytes:
        return _msg(ord("A"), struct.pack("<BH", multi, msg_id) + name.encode())

    next_id = 1
    pack_ids: list[int] = []
    for multi, _pack in enumerate(packs):
        buf.extend(add_logged(multi, next_id, "battery_status"))
        pack_ids.append(next_id)
        next_id += 1
    local_id = baro_id = est_id = None
    if include_local_position:
        buf.extend(add_logged(0, next_id, "vehicle_local_position"))
        local_id = next_id
        next_id += 1
    if include_fallback:
        buf.extend(add_logged(0, next_id, "vehicle_air_data"))
        baro_id = next_id
        next_id += 1
        buf.extend(add_logged(0, next_id, "estimator_states"))
        est_id = next_id
        next_id += 1
    buf.extend(add_logged(0, next_id, "vehicle_land_detected"))
    land_id = next_id
    next_id += 1
    buf.extend(add_logged(0, next_id, "battery_info"))
    info_id = next_id

    def data(msg_id: int, payload: bytes) -> bytes:
        return _msg(ord("D"), struct.pack("<H", msg_id) + payload)

    for index in range(samples):
        timestamp = 2_000_000 + index * dt_us
        for msg_id, (voltage, current) in zip(pack_ids, packs, strict=True):
            buf.extend(data(msg_id, struct.pack("<Qff", timestamp, voltage, current)))
        if local_id is not None:
            # NED z is down, so a hover at alt_m meters has z = -alt_m.
            buf.extend(
                data(
                    local_id,
                    struct.pack(
                        "<Qffffff",
                        timestamp,
                        0.0,
                        0.0,
                        -alt_m,
                        vx,
                        0.0,
                        vz,
                    ),
                )
            )
        if baro_id is not None and est_id is not None:
            # Distinct from local-position altitude so tests can see which source won.
            buf.extend(data(baro_id, struct.pack("<Qff", timestamp, 320.0 + alt_m, 25.0)))
            states = [0.0] * 10
            states[4] = vx
            states[5] = 0.0
            states[6] = vz
            states[9] = -alt_m
            buf.extend(data(est_id, struct.pack("<Q" + "f" * 10, timestamp, *states)))
        buf.extend(data(land_id, struct.pack("<QB", timestamp, int(landed))))
        buf.extend(data(info_id, struct.pack("<Q", timestamp) + PLANTED_IDENTIFIER.encode()))
    path.write_bytes(buf)


def test_two_packs_are_summed() -> None:
    rows = rows_from_topics(
        packs=[
            [PackReading(1_000_000, 22.0, 10.0)],
            [PackReading(1_000_000, 22.0, 11.0)],
        ],
        motion=[MotionReading(1_000_000, alt_m=10.0, north_mps=0.1, east_mps=0.0, down_mps=0.0)],
    )
    assert len(rows) == 1
    # 22*10 + 22*11 = 462 W
    assert rows[0].power_w == pytest.approx(462.0)
    assert rows[0].alt_m == pytest.approx(10.0)
    assert rows[0].groundspeed_mps == pytest.approx(0.1)
    assert rows[0].payload_id is None


def test_local_position_is_preferred_over_baro_and_ekf() -> None:
    rows = rows_from_topics(
        packs=[[PackReading(1_000_000, 22.0, 10.0)]],
        motion=[MotionReading(1_000_000, alt_m=10.0, north_mps=0.2, east_mps=0.0, down_mps=0.0)],
        fallback_motion=[
            MotionReading(1_000_000, alt_m=330.0, north_mps=5.0, east_mps=0.0, down_mps=0.0)
        ],
    )
    assert rows[0].alt_m == pytest.approx(10.0)
    assert rows[0].groundspeed_mps == pytest.approx(0.2)


def test_baro_and_ekf_are_used_when_local_position_is_missing() -> None:
    rows = rows_from_topics(
        packs=[[PackReading(1_000_000, 22.0, 10.0)]],
        motion=[],
        fallback_motion=[
            MotionReading(1_000_000, alt_m=330.0, north_mps=1.5, east_mps=2.0, down_mps=0.0)
        ],
    )
    assert rows[0].alt_m == pytest.approx(330.0)
    assert rows[0].groundspeed_mps == pytest.approx((1.5**2 + 2.0**2) ** 0.5)


def test_landed_samples_are_omitted() -> None:
    rows = rows_from_topics(
        packs=[[PackReading(1_000_000, 22.0, 10.0), PackReading(2_000_000, 22.0, 10.0)]],
        motion=[
            MotionReading(1_000_000, alt_m=0.0, north_mps=0.0, east_mps=0.0, down_mps=0.0),
            MotionReading(2_000_000, alt_m=10.0, north_mps=0.1, east_mps=0.0, down_mps=0.0),
        ],
        landed=[
            LandedReading(1_000_000, landed=True),
            LandedReading(2_000_000, landed=False),
        ],
    )
    assert len(rows) == 1
    assert rows[0].alt_m == pytest.approx(10.0)


def test_landed_flag_is_held_between_one_hertz_samples() -> None:
    """Land detection is logged near 1 Hz; a mid-interval motion sample is still landed."""
    rows = rows_from_topics(
        packs=[
            [
                PackReading(1_500_000, 22.0, 0.4),
                PackReading(3_500_000, 22.0, 10.0),
            ]
        ],
        motion=[
            MotionReading(1_500_000, alt_m=0.2, north_mps=0.0, east_mps=0.0, down_mps=0.0),
            MotionReading(3_500_000, alt_m=10.0, north_mps=0.1, east_mps=0.0, down_mps=0.0),
        ],
        landed=[
            LandedReading(1_000_000, landed=True),
            LandedReading(2_000_000, landed=True),
            LandedReading(3_000_000, landed=False),
        ],
    )
    assert len(rows) == 1
    assert rows[0].alt_m == pytest.approx(10.0)


def test_csv_does_not_carry_pack_serials_or_a_payload_id() -> None:
    rows = rows_from_topics(
        packs=[[PackReading(1_000_000, 22.0, 10.0)]],
        motion=[MotionReading(1_000_000, alt_m=10.0, north_mps=0.0, east_mps=0.0, down_mps=0.0)],
        temperatures=[TempReading(1_000_000, 25.0)],
    )
    text = to_csv(rows)
    assert PLANTED_IDENTIFIER not in text
    assert "sys_uuid" not in text
    assert "payload_id" in text.splitlines()[0]
    # The cell is present and empty; a real payload id would be a catalog slug.
    assert ",," in text.splitlines()[1] or text.splitlines()[1].endswith(",")
    assert rows[0].payload_id is None
    assert rows[0].timestamp == datetime(1970, 1, 1, 0, 0, 1, tzinfo=UTC)


def test_script_converts_a_ulog_and_redacts_serials(tmp_path: Path) -> None:
    import subprocess
    import sys

    source = tmp_path / "min.ulg"
    dest = tmp_path / "out.csv"
    write_min_ulog(source, samples=3)
    script = Path(__file__).resolve().parents[1] / "scripts" / "ulog_to_csv.py"
    completed = subprocess.run(
        [sys.executable, str(script), str(source), str(dest)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0
    text = dest.read_text(encoding="utf-8")
    assert PLANTED_IDENTIFIER not in text
    lines = text.strip().splitlines()
    assert lines[0].startswith("timestamp,")
    assert len(lines) == 4  # header + 3 samples
    # Two packs at 22 V, 10 A and 11 A.
    assert "462" in lines[1]


def test_a_stale_landed_flag_is_not_held() -> None:
    """A land-detector flag older than the hold window does not skip an in-air sample."""
    rows = rows_from_topics(
        packs=[[PackReading(4_000_000, 22.0, 10.0)]],
        motion=[MotionReading(4_000_000, alt_m=10.0, north_mps=0.1, east_mps=0.0, down_mps=0.0)],
        landed=[LandedReading(1_000_000, landed=True)],
    )
    assert len(rows) == 1
    assert rows[0].alt_m == pytest.approx(10.0)


def test_an_upcoming_landed_flag_within_the_hold_is_honored() -> None:
    with pytest.raises(FlightLogError, match="no in-air samples"):
        rows_from_topics(
            packs=[[PackReading(500_000, 22.0, 0.4)]],
            motion=[MotionReading(500_000, alt_m=0.2, north_mps=0.0, east_mps=0.0, down_mps=0.0)],
            landed=[LandedReading(1_000_000, landed=True)],
        )


def test_missing_packs_or_motion_is_refused() -> None:
    motion = [MotionReading(1_000_000, alt_m=10.0, north_mps=0.0, east_mps=0.0, down_mps=0.0)]
    packs = [[PackReading(1_000_000, 22.0, 10.0)]]
    with pytest.raises(FlightLogError, match="no battery_status"):
        rows_from_topics(packs=[], motion=motion)
    with pytest.raises(FlightLogError, match="neither vehicle_local_position nor baro"):
        rows_from_topics(packs=packs, motion=[], fallback_motion=[])


def test_a_pack_outside_the_alignment_window_is_skipped() -> None:
    with pytest.raises(FlightLogError, match="no in-air samples"):
        rows_from_topics(
            packs=[[PackReading(2_000_000, 22.0, 10.0)]],
            motion=[
                MotionReading(1_000_000, alt_m=10.0, north_mps=0.0, east_mps=0.0, down_mps=0.0)
            ],
        )
