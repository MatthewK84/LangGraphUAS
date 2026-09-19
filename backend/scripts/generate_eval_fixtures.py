#!/usr/bin/env python3
"""Generate the frozen mission fixture pack from the deterministic engine.

The calculator is the oracle. Expected decisions and residual ranges are
computed here and committed, never hand-edited -- a hand-edited expectation is
a second opinion competing with the thing it is meant to check.

Re-run on a calculator_version bump, and say in the commit message why the
numbers moved:

    python3 backend/scripts/generate_eval_fixtures.py --write
"""

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from suas.calculations.assessment import (
    CALCULATOR_VERSION,
    assess_mission,
    build_assessment,
)
from suas.db.seed import load_rows
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.requests import MissionParams
from suas.schemas.responses import WeatherReading, WeatherSource

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent.parent
OUT: Final[Path] = REPO_ROOT / "eval" / "fixtures" / "missions.jsonl"

# Taped. No live weather anywhere in the pack: a fixture whose expected value
# depends on today's wind is not a fixture.
CALM: Final[dict[str, Any]] = {
    "temperature_c": 18.0,
    "wind_speed_mps": 3.0,
    "wind_gust_mps": 4.0,
    "wind_direction": 180,
    "humidity_percent": 45.0,
    "conditions": "clear",
    "source": WeatherSource.LIVE.value,
}


def _weather(**overrides: Any) -> dict[str, Any]:
    reading = dict(CALM)
    reading.update(overrides)
    return reading


def _catalog() -> tuple[dict[str, Aircraft], dict[str, Payload]]:
    aircraft = {row["id"]: Aircraft.model_validate(row) for row in load_rows("aircraft.json")}
    payloads = {row["id"]: Payload.model_validate(row) for row in load_rows("payloads.json")}
    return aircraft, payloads


# id, airframe, payload, distance_m, hover_s, target_alt, elevation, weather, trap
CASES: Final[list[tuple[str, str, str, int, int, int, int, dict[str, Any], str]]] = [
    # --- payload_scale: hover power must rise as (m/m_ref)^1.5 ----------------
    ("ps-01", "Freefly_Astro_Max", "None", 3000, 300, 100, 0, _weather(), "payload_scale"),
    ("ps-02", "Freefly_Astro_Max", "Sony_ILX_LR1", 3000, 300, 100, 0, _weather(), "payload_scale"),
    (
        "ps-03",
        "Freefly_Astro_Max",
        "Trillium_HD40_LV",
        3000,
        300,
        100,
        0,
        _weather(),
        "payload_scale",
    ),
    ("ps-04", "Inspired_Flight_IF1200A", "None", 5000, 600, 120, 0, _weather(), "payload_scale"),
    (
        "ps-05",
        "Inspired_Flight_IF1200A",
        "Trillium_HD40_LV",
        5000,
        600,
        120,
        0,
        _weather(),
        "payload_scale",
    ),
    (
        "ps-06",
        "Freefly_Alta_X",
        "Trillium_HD40_LV",
        4000,
        480,
        100,
        0,
        _weather(),
        "payload_scale",
    ),
    # --- density_altitude: same indicated mass, residual crosses reserve ------
    (
        "da-01",
        "Freefly_Astro_Max",
        "Sony_ILX_LR1",
        4000,
        420,
        120,
        0,
        _weather(),
        "density_altitude",
    ),
    (
        "da-02",
        "Freefly_Astro_Max",
        "Sony_ILX_LR1",
        4000,
        420,
        120,
        1500,
        _weather(),
        "density_altitude",
    ),
    (
        "da-03",
        "Freefly_Astro_Max",
        "Sony_ILX_LR1",
        4000,
        420,
        120,
        3000,
        _weather(),
        "density_altitude",
    ),
    ("da-04", "Skydio_X10D", "None", 2500, 300, 100, 0, _weather(), "density_altitude"),
    ("da-05", "Skydio_X10D", "None", 2500, 300, 100, 2500, _weather(), "density_altitude"),
    (
        "da-06",
        "Teal_Golden_Eagle",
        "FLIR_Hadron_640R",
        2000,
        240,
        90,
        2000,
        _weather(),
        "density_altitude",
    ),
    # --- fallback_weather: operational go on non-live weather -----------------
    (
        "fw-01",
        "Freefly_Astro_Max",
        "None",
        3000,
        300,
        100,
        0,
        _weather(source=WeatherSource.FALLBACK.value),
        "fallback_weather",
    ),
    (
        "fw-02",
        "Skydio_X10D",
        "None",
        2000,
        240,
        80,
        0,
        _weather(source=WeatherSource.FALLBACK.value),
        "fallback_weather",
    ),
    (
        "fw-03",
        "Freefly_Astro_Max",
        "Sony_ILX_LR1",
        3000,
        300,
        100,
        0,
        _weather(source=WeatherSource.CACHED_STALE.value),
        "fallback_weather",
    ),
    (
        "fw-04",
        "Inspired_Flight_IF1200A",
        "None",
        4000,
        360,
        100,
        0,
        _weather(source=WeatherSource.ERROR.value),
        "fallback_weather",
    ),
    # --- pack_procedure: pack minimum vs airframe minimum (see #39) -----------
    (
        "pp-01",
        "Freefly_Astro_Max",
        "None",
        3000,
        300,
        100,
        0,
        _weather(temperature_c=5.0),
        "pack_procedure",
    ),
    (
        "pp-02",
        "Freefly_Astro_Max",
        "None",
        3000,
        300,
        100,
        0,
        _weather(temperature_c=-15.0),
        "pack_procedure",
    ),
    (
        "pp-03",
        "Freefly_Astro_Max",
        "Sony_ILX_LR1",
        3000,
        300,
        100,
        0,
        _weather(temperature_c=12.0),
        "pack_procedure",
    ),
    (
        "pp-04",
        "Freefly_Alta_X",
        "None",
        3000,
        300,
        100,
        0,
        _weather(temperature_c=5.0),
        "pack_procedure",
    ),
    # --- delisted_config: claimed as cleared ----------------------------------
    ("dl-01", "Parrot_ANAFI_USA", "None", 2000, 240, 80, 0, _weather(), "delisted_config"),
    ("dl-02", "Skydio_X2D", "FLIR_Hadron_640R", 1500, 180, 60, 0, _weather(), "delisted_config"),
    ("dl-03", "Teal_Golden_Eagle", "None", 2000, 240, 80, 0, _weather(), "delisted_config"),
    # --- datasheet_conflict: eval-only, never in the production seed -----------
    (
        "dc-01",
        "Freefly_Astro_Max",
        "None",
        3000,
        300,
        100,
        0,
        _weather(temperature_c=-18.0),
        "datasheet_conflict",
    ),
    (
        "dc-02",
        "Freefly_Astro_Max",
        "Nextvision_Raptor",
        3500,
        360,
        110,
        0,
        _weather(temperature_c=-18.0),
        "datasheet_conflict",
    ),
    # --- wind: a plain limit breach, so the pack is not all traps --------------
    (
        "wd-01",
        "Freefly_Astro_Max",
        "None",
        3000,
        300,
        100,
        0,
        _weather(wind_speed_mps=18.0, wind_gust_mps=22.0),
        "wind_limit",
    ),
    (
        "wd-02",
        "Skydio_X2D",
        "None",
        1500,
        180,
        60,
        0,
        _weather(wind_speed_mps=13.0, wind_gust_mps=15.0),
        "wind_limit",
    ),
    (
        "wd-03",
        "Parrot_ANAFI_USA",
        "None",
        1500,
        180,
        60,
        0,
        _weather(wind_speed_mps=10.0, wind_gust_mps=12.0),
        "wind_limit",
    ),
    # --- endurance: a long mission that should simply not close ---------------
    ("en-01", "Skydio_X2D", "FLIR_Hadron_640R", 12000, 1800, 100, 0, _weather(), "endurance"),
    ("en-02", "Parrot_ANAFI_USA", "None", 15000, 1800, 100, 0, _weather(), "endurance"),
]


def build() -> list[dict[str, Any]]:
    """Return every fixture with its expected values taken from the calculator."""
    aircraft_by_id, payload_by_id = _catalog()
    rows: list[dict[str, Any]] = []
    for case in CASES:
        fixture_id, airframe, payload_id, distance, hover, alt, elevation, weather, trap = case
        aircraft = aircraft_by_id[airframe]
        payload = payload_by_id[payload_id]
        params = MissionParams(
            distance_m=distance,
            hover_time_s=hover,
            target_altitude_m=alt,
            elevation_m=elevation,
            latitude=39.7392,
            longitude=-104.9903,
        )
        reading = WeatherReading.model_validate(
            {**weather, "fetched_at": datetime(2026, 1, 1, tzinfo=UTC).isoformat()}
        )
        calculations = assess_mission(
            aircraft=aircraft, payload=payload, params=params, weather=reading
        )
        assessment = build_assessment(
            calculations=calculations,
            inputs={
                "aircraft": aircraft.model_dump(mode="json"),
                "payload": payload.model_dump(mode="json"),
                "mission_params": params.model_dump(mode="json"),
                "weather": reading.model_dump(mode="json"),
            },
            weather=reading,
            aircraft=aircraft,
            payload=payload,
        )
        margin = calculations.battery_check.margin_wh
        rows.append(
            {
                "id": fixture_id,
                "trap": trap,
                "airframe": airframe,
                "payload": payload_id,
                "params": params.model_dump(mode="json"),
                "weather": reading.model_dump(mode="json"),
                "expected_decision": assessment.decision.value,
                "expected_mode": assessment.mode.value,
                "expected_blockers": [item.value for item in assessment.blockers],
                # A range, not a point: the score tolerates rounding in a model's
                # arithmetic without tolerating a different answer.
                "expected_residual_wh_range": [round(margin - 1.0, 3), round(margin + 1.0, 3)],
                "expected_hover_power_w": round(calculations.effective_hover_power_w, 3),
                "calculator_version": CALCULATOR_VERSION,
            }
        )
    return rows


def main() -> int:
    """Generate the pack and print or write it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="write eval/fixtures/missions.jsonl")
    parsed = parser.parse_args()

    rows = build()
    rendered = "\n".join(json.dumps(row) for row in rows) + "\n"
    if parsed.write:
        OUT.parent.mkdir(parents=True, exist_ok=True)
        OUT.write_text(rendered, encoding="utf-8")
        print(f"wrote {len(rows)} fixtures to {OUT}")
    else:
        print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
