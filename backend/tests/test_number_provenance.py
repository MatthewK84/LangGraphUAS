"""Every watt and watt-hour on the wire says what it rests on (#79).

The UI used to receive a watt figure with no hint that it came from an
estimate, so a guessed number rendered exactly like a measured one. Each W and
Wh figure in ``Calculations`` now travels with its own provenance: the weakest
``source`` bucket and the lowest ``confidence`` among the reference fields it
was computed from.

Which fields feed which figure is a table, and a table can drift from the
calculator. So the table is not trusted: the tests perturb each reference
field and watch which figures move, and the table must match exactly.
"""

import re
from pathlib import Path
from typing import Any

import pytest
from pydantic import BaseModel

from suas.api.number_provenance import WATT_FIGURE_INPUTS, number_provenance
from suas.calculations.assessment import assess_mission
from suas.reference_data import load_rows
from suas.schemas.domain import Aircraft, Payload
from suas.schemas.provenance import Confidence, FieldProvenance, FieldSource
from suas.schemas.requests import MissionParams
from suas.schemas.responses import WeatherReading

_PARAMS = MissionParams(
    distance_m=2000.0,
    hover_time_s=120.0,
    target_altitude_m=120.0,
    elevation_m=0.0,
    latitude=34.0,
    longitude=-80.0,
)
_WEATHER = WeatherReading(
    temperature_c=5.0,
    wind_speed_mps=4.0,
    wind_gust_mps=6.0,
    wind_direction=90.0,
    humidity_percent=50.0,
    conditions="clear",
)


def _row(filename: str, key: str) -> dict[str, Any]:
    return next(r for r in load_rows(filename) if r["id"] == key)


_AIRCRAFT = _row("aircraft.json", "Skydio_X10D")
_PAYLOAD = _row("payloads.json", "Sony_ILX_LR1")


def _figures(model: BaseModel, prefix: str = "") -> dict[str, float]:
    found: dict[str, float] = {}
    for name, value in model:
        if isinstance(value, BaseModel):
            found.update(_figures(value, f"{prefix}{name}."))
        elif name.endswith(("_w", "_wh")):
            found[f"{prefix}{name}"] = value
    return found


def _assess(aircraft: dict[str, Any], payload: dict[str, Any]) -> dict[str, float]:
    calculations = assess_mission(
        aircraft=Aircraft.model_validate(aircraft),
        payload=Payload.model_validate(payload),
        params=_PARAMS,
        weather=_WEATHER,
    )
    return _figures(calculations)


def _numeric_fields(row: dict[str, Any]) -> list[str]:
    return [k for k, v in row.items() if isinstance(v, float) and v > 0.0]


def _observed_inputs() -> dict[str, set[str]]:
    base = _assess(_AIRCRAFT, _PAYLOAD)
    moved: dict[str, set[str]] = {figure: set() for figure in base}
    for owner, row in (("aircraft", _AIRCRAFT), ("payload", _PAYLOAD)):
        for field in _numeric_fields(row):
            bumped = {**row, field: row[field] * 1.5}
            after = (
                _assess(bumped, _PAYLOAD) if owner == "aircraft" else _assess(_AIRCRAFT, bumped)
            )
            for figure, value in after.items():
                if value != base[figure]:
                    moved[figure].add(f"{owner}.{field}")
    return moved


def _record(source: FieldSource, confidence: Confidence = Confidence.HIGH) -> FieldProvenance:
    return FieldProvenance(value=1.0, unit="W", source=source, confidence=confidence)


def _with_provenance(row: dict[str, Any], records: dict[str, FieldProvenance]) -> dict[str, Any]:
    return {**row, "provenance": records}


def test_every_watt_figure_in_calculations_has_an_entry() -> None:
    assert set(WATT_FIGURE_INPUTS) == set(_assess(_AIRCRAFT, _PAYLOAD))


def test_the_table_lists_exactly_the_fields_each_figure_moves_with() -> None:
    observed = _observed_inputs()
    assert {k: set(v) for k, v in WATT_FIGURE_INPUTS.items()} == observed


def test_the_weakest_source_and_the_lowest_confidence_win() -> None:
    records = {
        field: _record(FieldSource.DATASHEET)
        for field in (
            "hover_power_w",
            "cruise_power_w",
            "cruise_speed_mps",
            "weight_kg",
            "battery_wh",
        )
    }
    records["battery_wh"] = _record(FieldSource.ESTIMATE, Confidence.MEDIUM)
    aircraft = Aircraft.model_validate(_with_provenance(_AIRCRAFT, records))
    payload = Payload.model_validate(
        _with_provenance(
            _PAYLOAD,
            {f: _record(FieldSource.DATASHEET) for f in ("weight_kg", "power_draw_w")},
        )
    )
    view = number_provenance(aircraft, payload)
    hover = view["effective_hover_power_w"]
    assert (hover.source, hover.confidence, hover.operational_grade) == (
        FieldSource.DATASHEET,
        Confidence.HIGH,
        True,
    )
    margin = view["battery_check.margin_wh"]
    assert (margin.source, margin.confidence, margin.operational_grade) == (
        FieldSource.ESTIMATE,
        Confidence.MEDIUM,
        False,
    )
    assert margin.inputs == sorted(WATT_FIGURE_INPUTS["battery_check.margin_wh"])


@pytest.mark.parametrize(
    ("weaker", "stronger"),
    [
        (FieldSource.UNKNOWN, FieldSource.ESTIMATE),
        (FieldSource.ESTIMATE, FieldSource.DERIVED),
        (FieldSource.DERIVED, FieldSource.SECONDARY),
        (FieldSource.SECONDARY, FieldSource.FLIGHT_LOG),
        (FieldSource.SECONDARY, FieldSource.DATASHEET),
    ],
)
def test_source_buckets_rank_from_unknown_up(weaker: FieldSource, stronger: FieldSource) -> None:
    aircraft = Aircraft.model_validate(
        _with_provenance(
            _AIRCRAFT,
            {
                "hover_power_w": _record(weaker),
                "weight_kg": _record(stronger),
            },
        )
    )
    payload = Payload.model_validate(_with_provenance(_PAYLOAD, {"weight_kg": _record(stronger)}))
    assert number_provenance(aircraft, payload)["effective_hover_power_w"].source is weaker


def test_a_field_with_no_record_reads_as_unknown_and_low() -> None:
    aircraft = Aircraft.model_validate(_with_provenance(_AIRCRAFT, {}))
    payload = Payload.model_validate(_with_provenance(_PAYLOAD, {}))
    for figure in number_provenance(aircraft, payload).values():
        assert (figure.source, figure.confidence, figure.operational_grade) == (
            FieldSource.UNKNOWN,
            Confidence.LOW,
            False,
        )


def test_an_all_estimate_configuration_is_estimate_on_every_figure() -> None:
    def estimates(row: dict[str, Any]) -> dict[str, Any]:
        records = {f: _record(FieldSource.ESTIMATE) for f in _numeric_fields(row)}
        return _with_provenance(row, records)

    view = number_provenance(
        Aircraft.model_validate(estimates(_AIRCRAFT)),
        Payload.model_validate(estimates(_PAYLOAD)),
    )
    assert {figure.source for figure in view.values()} == {FieldSource.ESTIMATE}
    assert not any(figure.operational_grade for figure in view.values())


def test_the_bundled_x10d_sony_figures_follow_live_provenance() -> None:
    """X10D + Sony ILX-LR1 now carry datasheet mass/energy and derived/estimate power.

    Every W/Wh figure's summary source is the weakest bucket among the reference
    fields it rests on. After the manufacturer promotion that is datasheet,
    derived, or estimate — not universally unknown. usable_capacity_wh rests
    only on datasheet battery_wh, so it alone is operational-grade; figures that
    still pull in derived hover or estimate cruise stay non-operational.
    """
    view = number_provenance(Aircraft.model_validate(_AIRCRAFT), Payload.model_validate(_PAYLOAD))
    sources = {figure.source for figure in view.values()}
    assert sources == {FieldSource.DATASHEET, FieldSource.DERIVED, FieldSource.ESTIMATE}
    assert view["battery_check.usable_capacity_wh"].operational_grade is True
    assert view["battery_check.usable_capacity_wh"].source is FieldSource.DATASHEET
    assert view["effective_hover_power_w"].operational_grade is False
    assert view["energy_breakdown.total_wh"].operational_grade is False


def test_every_figure_the_dashboard_labels_is_one_the_backend_reports() -> None:
    panel = (
        Path(__file__).resolve().parents[2] / "frontend/src/app/components/ResultsPanel.tsx"
    ).read_text(encoding="utf-8")
    # Every W and Wh row names its figure by dotted path, a quoted string ending _w or _wh.
    paths = set(re.findall(r'"([a-z_]+(?:\.[a-z_]+)?_wh?)"', panel))
    assert len(paths) == 8
    assert paths <= set(WATT_FIGURE_INPUTS)


def test_each_figure_carries_the_record_of_every_input_it_rests_on() -> None:
    """The drawer (#96) links a datasheet figure to its cited URL.

    The summary says how weak a figure's basis is; the basis itself says which
    field, from where and when, so a reviewer can trace a watt to its source.
    """
    cited = FieldProvenance(
        value=4260.0,
        unit="W",
        source=FieldSource.DATASHEET,
        source_url="https://example.test/spec",
        retrieved_at="2026-01-05",
        confidence=Confidence.HIGH,
        notes="Manufacturer spec sheet.",
    )
    aircraft = Aircraft.model_validate(_with_provenance(_AIRCRAFT, {"hover_power_w": cited}))
    payload = Payload.model_validate(_with_provenance(_PAYLOAD, {}))
    hover = number_provenance(aircraft, payload)["effective_hover_power_w"]
    assert [entry.field for entry in hover.basis] == hover.inputs
    first = next(entry for entry in hover.basis if entry.field == "aircraft.hover_power_w")
    assert (first.source_url, first.retrieved_at, first.notes) == (
        "https://example.test/spec",
        "2026-01-05",
        "Manufacturer spec sheet.",
    )
    assert (first.value, first.unit, first.source, first.confidence) == (
        4260.0,
        "W",
        FieldSource.DATASHEET,
        Confidence.HIGH,
    )
    unrecorded = next(entry for entry in hover.basis if entry.field == "payload.weight_kg")
    assert (unrecorded.source, unrecorded.source_url, unrecorded.value) == (
        FieldSource.UNKNOWN,
        None,
        None,
    )
