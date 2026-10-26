"""The Compose smoke must fail on a catalog contract break (#116).

The dashboard reads the catalog through types declared in
``frontend/src/lib/types.ts``. The smoke parses those interfaces and checks
every catalog item the running stack returns against them, so a backend field
rename or type change fails the run, not the next operator.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _ROOT / "scripts" / "compose_smoke.py"
_TYPES = _ROOT / "frontend" / "src" / "lib" / "types.ts"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("compose_smoke", _SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_SOURCE = """
export interface AircraftSummary {
  readonly id: string;
  /** A comment line the parser must skip. */
  readonly battery_wh: number;
  readonly cruise_achievable: boolean;
  readonly note?: string;
}
"""


def test_interface_fields_reads_required_fields_and_types() -> None:
    fields = _load().interface_fields(_SOURCE, "AircraftSummary")
    assert fields == {"id": "string", "battery_wh": "number", "cruise_achievable": "boolean"}


def test_the_real_catalog_interfaces_parse() -> None:
    source = _TYPES.read_text(encoding="utf-8")
    smoke = _load()
    assert "battery_wh" in smoke.interface_fields(source, "AircraftSummary")
    assert "power_draw_w" in smoke.interface_fields(source, "PayloadSummary")


def test_a_matching_catalog_has_no_breaks() -> None:
    fields = {"id": "string", "battery_wh": "number", "cruise_achievable": "boolean"}
    items = [{"id": "X", "battery_wh": 588, "cruise_achievable": True, "extra": 1}]
    assert _load().contract_breaks("aircraft", items, fields) == []


def test_a_renamed_field_is_a_break() -> None:
    fields = {"id": "string", "battery_wh": "number"}
    breaks = _load().contract_breaks("aircraft", [{"id": "X", "battery_capacity_wh": 588}], fields)
    assert breaks == ["aircraft[X].battery_wh missing"]


def test_a_retyped_field_is_a_break() -> None:
    fields = {"id": "string", "battery_wh": "number"}
    breaks = _load().contract_breaks("aircraft", [{"id": "X", "battery_wh": "588"}], fields)
    assert breaks == ["aircraft[X].battery_wh is str, frontend expects number"]


def test_a_boolean_is_not_a_number() -> None:
    fields = {"id": "string", "battery_wh": "number"}
    assert _load().contract_breaks("aircraft", [{"id": "X", "battery_wh": True}], fields) != []


def test_an_empty_catalog_is_a_break() -> None:
    assert _load().contract_breaks("payloads", [], {"id": "string"}) == ["payloads empty"]


# --- #82: the smoke drives the proxy like a browser -------------------------


def test_a_post_carries_the_dashboard_origin() -> None:
    request = _load().build_request("http://localhost:3000/api/plan", {"a": 1})
    assert request.get_header("Origin") == "http://localhost:3000"
    assert request.get_method() == "POST"


def test_each_browser_keeps_its_own_cookies() -> None:
    import urllib.request

    smoke = _load()
    first, second = smoke.new_browser(), smoke.new_browser()
    jars = [
        handler.cookiejar
        for opener in (first, second)
        for handler in opener.handlers
        if isinstance(handler, urllib.request.HTTPCookieProcessor)
    ]
    assert len(jars) == 2
    assert jars[0] is not jars[1]
