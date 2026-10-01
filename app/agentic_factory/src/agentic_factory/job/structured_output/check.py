import json
from dataclasses import dataclass, field
from typing import Any

from jsonschema import Draft202012Validator, ValidationError

from agentic_factory.job.structured_output.contract import Schema

TOP = "(top)"  # the path of an error on the whole object
NOT_AN_OBJECT = "the structured output must be a JSON object"


@dataclass(frozen=True)
class Checked:
    """A JSON text checked against a schema: the object when it matches,
    else every error as a readable line with its path."""

    structured_output: dict[str, Any] | None
    errors: list[str] = field(default_factory=list)


def check(text: str, schema: Schema) -> Checked:
    """The text parsed and validated against the schema (Draft 2020-12, its
    `$defs` and `$ref` resolved). A syntax error is one line with its line
    and column."""
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        return Checked(None, [f"not JSON: {error.msg} at line {error.lineno} column {error.colno}"])
    errors = schema_errors(value, schema)
    if errors:
        return Checked(None, errors)
    if not isinstance(value, dict):
        return Checked(None, [f"{TOP}: {NOT_AN_OBJECT}"])
    return Checked(value)


def schema_errors(value: Any, schema: Schema) -> list[str]:
    """Every way the value breaks the schema, one line each, in path order."""
    found = Draft202012Validator(schema).iter_errors(value)
    return sorted(error_line(error) for error in found)


def error_line(error: ValidationError) -> str:
    """`chapters[1].formats[0]: 'pdf' is not one of ['md', 'ipynb']`."""
    return f"{path_of(list(error.absolute_path))}: {error.message}"


def path_of(steps: list[str | int]) -> str:
    """`chapters[1].formats[0]` from `["chapters", 1, "formats", 0]`; `(top)` when empty."""
    text = "".join(f"[{step}]" if isinstance(step, int) else f".{step}" for step in steps)
    return text.removeprefix(".") or TOP
