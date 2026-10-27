"""Per-figure provenance for every watt and watt-hour on the wire (#79).

A watt the calculator derived from an estimate used to reach the client looking
exactly like one read from a datasheet. This module labels each W and Wh figure
in ``Calculations`` with the weakest ``source`` bucket and the lowest
``confidence`` among the reference fields it was computed from, so the UI can
show which is which. It reads provenance; it computes no number and decides
nothing. The operational gate keeps its own rule in ``suas.calculations.gate``.

Weather also moves these figures (air density, cold derate). Its provenance is
already on the wire as ``weather.source``, so it is not repeated here.
"""

from collections.abc import Mapping
from typing import Final

from suas.schemas.domain import Aircraft, Payload
from suas.schemas.provenance import Confidence, FieldProvenance, FieldSource
from suas.schemas.responses import InputBasis, NumberProvenance

_HOVER: Final = ("aircraft.hover_power_w", "aircraft.weight_kg", "payload.weight_kg")
_PHASE: Final = (*_HOVER, "payload.power_draw_w")
_CRUISE: Final = (
    "aircraft.cruise_power_w",
    "aircraft.cruise_speed_mps",
    "aircraft.weight_kg",
    "payload.power_draw_w",
    "payload.weight_kg",
)
_TOTAL: Final = tuple(sorted({*_PHASE, *_CRUISE}))

# Which reference fields each figure is computed from. Not trusted on its own:
# tests/test_number_provenance.py perturbs every field through the calculator
# and fails if this table names a field that does not move a figure, or misses
# one that does.
WATT_FIGURE_INPUTS: Final[Mapping[str, tuple[str, ...]]] = {
    "effective_hover_power_w": _HOVER,
    "energy_required_wh": _TOTAL,
    "energy_breakdown.climb_wh": _PHASE,
    "energy_breakdown.cruise_wh": _CRUISE,
    "energy_breakdown.hover_wh": _PHASE,
    "energy_breakdown.descent_wh": _PHASE,
    "energy_breakdown.total_wh": _TOTAL,
    "battery_check.energy_required_wh": _TOTAL,
    "battery_check.usable_capacity_wh": ("aircraft.battery_wh",),
    "battery_check.margin_wh": ("aircraft.battery_wh", *_TOTAL),
}

# Weakest first. A figure is only as good as the worst number it rests on.
_SOURCE_RANK: Final[tuple[FieldSource, ...]] = (
    FieldSource.UNKNOWN,
    FieldSource.ESTIMATE,
    FieldSource.DERIVED,
    FieldSource.SECONDARY,
    FieldSource.FLIGHT_LOG,
    FieldSource.DATASHEET,
)
_CONFIDENCE_RANK: Final[tuple[Confidence, ...]] = (
    Confidence.LOW,
    Confidence.MEDIUM,
    Confidence.HIGH,
)
# What a field with no provenance record reads as: nobody vouched for it.
_UNRECORDED: Final = FieldProvenance(value=0.0, unit="-", source=FieldSource.UNKNOWN)


def _lookup(aircraft: Aircraft, payload: Payload, path: str) -> FieldProvenance | None:
    owner, field = path.split(".", 1)
    records = aircraft.provenance if owner == "aircraft" else payload.provenance
    return records.get(field)


def _basis(path: str, record: FieldProvenance | None) -> InputBasis:
    if record is None:
        return InputBasis(
            field=path,
            value=None,
            unit=None,
            source=_UNRECORDED.source,
            confidence=_UNRECORDED.confidence,
        )
    return InputBasis(
        field=path,
        value=record.value,
        unit=record.unit,
        source=record.source,
        confidence=record.confidence,
        source_url=record.source_url,
        retrieved_at=record.retrieved_at,
        notes=record.notes,
    )


def _summarise(
    found: dict[str, FieldProvenance | None], inputs: tuple[str, ...]
) -> NumberProvenance:
    records = [found[path] or _UNRECORDED for path in inputs]
    paths = sorted(set(inputs))
    return NumberProvenance(
        source=min((r.source for r in records), key=_SOURCE_RANK.index),
        confidence=min((r.confidence for r in records), key=_CONFIDENCE_RANK.index),
        operational_grade=all(r.is_operational_grade for r in records),
        inputs=paths,
        basis=[_basis(path, found[path]) for path in paths],
    )


def number_provenance(aircraft: Aircraft, payload: Payload) -> dict[str, NumberProvenance]:
    """Return the provenance of each W and Wh figure, keyed by its path in ``Calculations``."""
    return {
        figure: _summarise({path: _lookup(aircraft, payload, path) for path in inputs}, inputs)
        for figure, inputs in WATT_FIGURE_INPUTS.items()
    }
