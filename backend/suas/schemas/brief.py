"""The only shape language-model output may take.

A closed model, not a filter: unknown keys are a validation failure rather than
something to tidy away, and the fields that exist are the two a brief is allowed
to contribute. Everything a brief might be tempted to assert -- a decision, a
watt, a limit, a mode -- is absent by construction, so there is nothing to strip.

Nothing produces this yet; the report service returns prose. It exists now
because the moment to build the barrier is before there is something to carry
through it.
"""

from pydantic import BaseModel, ConfigDict, Field


class BriefOutput(BaseModel):
    """Parsed model output for a safety brief."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    brief_markdown: str = Field(default="", max_length=8000)
    suggested_contingencies: list[str] = Field(default_factory=list, max_length=8)
    cited_chunk_ids: list[str] = Field(default_factory=list, max_length=12)
