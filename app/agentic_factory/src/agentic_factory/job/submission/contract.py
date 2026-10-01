from enum import StrEnum
from typing import Any

Schema = dict[str, Any]
"""A JSON schema: an object with named fields, usually
`SomeModel.model_json_schema()`. The caller owns the model; the job only
ever sees the schema."""


class Source(StrEnum):
    """Where the structured output came from; stored beside it."""

    SUBMITTED = "submitted"  # the coder's own `af output submit`, checked against the schema
