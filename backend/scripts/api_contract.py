"""Freeze and check the public API's shape (#115).

The contract is flattened from the app's OpenAPI document: for each planning
endpoint, every response field path (``assessment.blockers[]``) with the JSON
types it can take, and every request field path with which ones a client must
send. A change breaks it when a response field disappears or gains a type
(``null`` included), or a request field disappears or becomes required.
Additions that a client can ignore are not breaks.

    python scripts/api_contract.py          # exit 1 and list breaks, if any
    python scripts/api_contract.py --write  # re-freeze after a deliberate break
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Final

ENDPOINTS: Final[tuple[str, ...]] = (
    "/api/plan",
    "/api/plan/{thread_id}/ack",
    "/api/replan",
)
FROZEN: Final[Path] = (
    Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "api_contract.json"
)
REGENERATE: Final[str] = "cd backend && python scripts/api_contract.py --write"

Shape = dict[str, set[str]]


class _Flattener:
    """Walks one schema into field paths, following ``$ref`` once per branch."""

    def __init__(self, components: dict[str, Any]) -> None:
        self._components = components
        self.types: Shape = {}
        self.required: set[str] = set()

    def walk(
        self, schema: dict[str, Any], path: str, *, required: bool, seen: frozenset[str]
    ) -> None:
        if "$ref" in schema:
            name = str(schema["$ref"]).rsplit("/", 1)[-1]
            if name in seen:
                self.types.setdefault(path, set()).add(f"ref:{name}")
                return
            self.walk(self._components[name], path, required=required, seen=seen | {name})
            return
        variants = schema.get("anyOf") or schema.get("oneOf") or schema.get("allOf")
        if variants:
            for variant in variants:
                self.walk(variant, path, required=required, seen=seen)
            return
        kind = str(schema.get("type", "any"))
        self.types.setdefault(path, set()).add(kind)
        if required and path:
            self.required.add(path)
        if kind == "array" and isinstance(schema.get("items"), dict):
            self.walk(schema["items"], f"{path}[]", required=False, seen=seen)
        if kind == "object":
            self._walk_object(schema, path, required=required, seen=seen)

    def _walk_object(
        self, schema: dict[str, Any], path: str, *, required: bool, seen: frozenset[str]
    ) -> None:
        must = set(schema.get("required", []))
        for name, child in schema.get("properties", {}).items():
            child_path = f"{path}.{name}" if path else name
            self.walk(child, child_path, required=required and name in must, seen=seen)
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            self.walk(extra, f"{path}{{}}", required=False, seen=seen)


def _flatten(components: dict[str, Any], schema: dict[str, Any]) -> _Flattener:
    flattener = _Flattener(components)
    flattener.walk(schema, "", required=True, seen=frozenset())
    flattener.types.pop("", None)
    return flattener


def _body(operation: dict[str, Any]) -> dict[str, Any]:
    return dict(
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )


def extract(spec: dict[str, Any]) -> dict[str, Any]:
    """Return the contract of the planning endpoints in ``spec``."""
    components = spec["components"]["schemas"]
    contract: dict[str, Any] = {}
    for path in ENDPOINTS:
        operation = spec["paths"][path]["post"]
        response = operation["responses"]["200"]["content"]["application/json"]["schema"]
        request = _flatten(components, _body(operation))
        contract[f"POST {path}"] = {
            "request": {
                "fields": {k: sorted(v) for k, v in sorted(request.types.items())},
                "required": sorted(request.required),
            },
            "response": {
                k: sorted(v) for k, v in sorted(_flatten(components, response).types.items())
            },
        }
    return contract


def _response_breaks(
    endpoint: str, frozen: dict[str, list[str]], current: dict[str, list[str]]
) -> list[str]:
    breaks = []
    for field, types in frozen.items():
        if field not in current:
            breaks.append(f"{endpoint} response: {field} was removed")
            continue
        for added in sorted(set(current[field]) - set(types)):
            verb = "can now be null" if added == "null" else f"can now be {added}"
            breaks.append(f"{endpoint} response: {field} {verb}")
    return breaks


def _request_breaks(endpoint: str, frozen: dict[str, Any], current: dict[str, Any]) -> list[str]:
    removed = [
        f"{endpoint} request: {f} was removed"
        for f in frozen["fields"]
        if f not in current["fields"]
    ]
    newly = sorted(set(current["required"]) - set(frozen["required"]))
    return removed + [f"{endpoint} request: {f} is newly required" for f in newly]


def breaking_changes(frozen: dict[str, Any], current: dict[str, Any]) -> list[str]:
    """Return one line per change that would break a client of ``frozen``."""
    breaks: list[str] = []
    for endpoint, shape in frozen.items():
        if endpoint not in current:
            breaks.append(f"{endpoint} was removed")
            continue
        breaks += _response_breaks(endpoint, shape["response"], current[endpoint]["response"])
        breaks += _request_breaks(endpoint, shape["request"], current[endpoint]["request"])
    return breaks


def report(breaks: list[str]) -> str:
    """Explain the breaks and how to accept a deliberate one."""
    lines = ["The public API contract changed in a way a client would notice:", *breaks]
    lines.append(
        "If the break is deliberate, update the dashboard, then re-freeze with "
        f"`{REGENERATE}` and commit tests/fixtures/api_contract.json."
    )
    return "\n".join(lines)


def render(contract: dict[str, Any]) -> str:
    """Return the contract as the committed file's text."""
    return json.dumps(contract, indent=2, sort_keys=True) + "\n"


def main(argv: list[str]) -> int:
    """Check the app against the frozen contract, or re-freeze it with ``--write``."""
    from suas.main import create_app

    current = extract(create_app().openapi())
    if "--write" in argv:
        FROZEN.write_text(render(current))
        print(f"Wrote {FROZEN}")
        return 0
    breaks = breaking_changes(json.loads(FROZEN.read_text()), current)
    if breaks:
        print(report(breaks), file=sys.stderr)
        return 1
    print("API contract holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
