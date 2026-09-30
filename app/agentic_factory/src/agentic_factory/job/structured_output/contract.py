from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

Schema = dict[str, Any]
"""A JSON schema of the structured output a job must state: an object with named fields,
usually `SomeModel.model_json_schema()`. The caller owns the model; the
job only ever sees the schema."""


class Source(StrEnum):
    """Where the structured output was found; stored beside it."""

    LAST_MESSAGE = "last_message"  # the coder's last message, where the prompt asked for it
    CONVERSATION = "conversation"  # the whole rendered conversation, when the last message had none


class Extraction(BaseModel):
    """What the extraction step found in the coder's text. The step is asked
    in strict mode, where every field is required; `structured_output` being null is
    how the model says "not stated" instead of inventing values."""

    model_config = ConfigDict(extra="forbid")

    structured_output: dict[str, Any] | None = Field(
        description="The output, matching the job's schema, when the text states every field."
    )
    missing: list[str] = Field(
        description="The fields the text does not state; empty when structured_output is given."
    )


def field_names(schema: Schema) -> list[str]:
    """The names of the fields, in schema order."""
    return list(schema.get("properties", {}))
