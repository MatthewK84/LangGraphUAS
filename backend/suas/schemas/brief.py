"""The only shape language-model output may take.

A closed model, not a filter: unknown keys are a validation failure rather than
something to tidy away, and the fields that exist are the two a brief is allowed
to contribute. Everything a brief might be tempted to assert -- a decision, a
watt, a limit, a mode -- is absent by construction, so there is nothing to strip.

The report service and the eval harness both request this shape through a
JSON schema, so a model has no structured field in which to author a
decision, a mode, or a watt.
"""

from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field


class BriefOutput(BaseModel):
    """Parsed model output for a safety brief."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brief_markdown: str = Field(default="", max_length=8000)
    suggested_contingencies: list[str] = Field(default_factory=list, max_length=8)
    cited_chunk_ids: list[str] = Field(default_factory=list, max_length=12)


BRIEF_JSON_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "brief_markdown": {"type": "string"},
        "suggested_contingencies": {"type": "array", "items": {"type": "string"}},
        "cited_chunk_ids": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["brief_markdown", "suggested_contingencies", "cited_chunk_ids"],
    "additionalProperties": False,
}


def brief_response_format() -> dict[str, Any]:
    """Return the OpenAI-compatible response_format that constrains a brief.

    This is what llama.cpp's server (and any other OpenAI-compatible endpoint)
    receives as a JSON schema. additionalProperties is false, so a model that
    wants to emit a decision has to smuggle it into brief_markdown, where the
    seal and the override still catch it.
    """
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "brief_output",
            "strict": True,
            "schema": BRIEF_JSON_SCHEMA,
        },
    }
