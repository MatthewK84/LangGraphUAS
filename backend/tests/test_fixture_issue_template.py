"""The good-first-fixture issue template is the stated path to adding a mission.

A contributor should not have to read the generator, the pack, and the backlog
spec to guess the format. These tests pin that the template exists, names the
regeneration script, and shows the mission JSON shape and trap types.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / ".github" / "ISSUE_TEMPLATE" / "good-first-fixture.yml"
README = ROOT / "README.md"
GENERATOR = "backend/scripts/generate_eval_fixtures.py"

TRAPS = (
    "payload_scale",
    "density_altitude",
    "fallback_weather",
    "pack_procedure",
    "delisted_config",
    "datasheet_conflict",
    "wind_limit",
    "endurance",
)

MISSION_FIELDS = (
    "id",
    "airframe",
    "payload",
    "trap",
    "distance_m",
    "hover_time_s",
    "target_altitude_m",
    "elevation_m",
)


def test_the_template_exists() -> None:
    assert TEMPLATE.is_file(), "expected .github/ISSUE_TEMPLATE/good-first-fixture.yml"


def test_the_template_names_the_regeneration_script() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    assert GENERATOR in text
    assert "--write" in text


def test_the_template_lists_every_trap_type() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    missing = [trap for trap in TRAPS if trap not in text]
    assert missing == []


def test_the_template_shows_the_mission_json_fields() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    missing = [field for field in MISSION_FIELDS if field not in text]
    assert missing == []


def test_the_readme_points_at_the_template() -> None:
    text = README.read_text(encoding="utf-8")
    assert ".github/ISSUE_TEMPLATE/good-first-fixture.yml" in text
    assert GENERATOR in text
