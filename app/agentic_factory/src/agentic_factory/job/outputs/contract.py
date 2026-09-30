from typing import Any

from pydantic import BaseModel, ConfigDict, Field

Schema = dict[str, Any]
"""A JSON schema of the outputs a job must state: an object with named fields,
usually `SomeModel.model_json_schema()`. The caller owns the model; the
job only ever sees the schema."""


class Extraction(BaseModel):
    """What the extraction step found in the coder's text. The step is asked
    in strict mode, where every field is required; `outputs` being null is
    how the model says "not stated" instead of inventing values."""

    model_config = ConfigDict(extra="forbid")

    outputs: dict[str, Any] | None = Field(
        description="The outputs, matching the job's schema, when the text states every field."
    )
    missing: list[str] = Field(
        description="The fields the text does not state; empty when outputs is given."
    )


def field_names(schema: Schema) -> list[str]:
    """The names of the outputs, in schema order."""
    return list(schema.get("properties", {}))
