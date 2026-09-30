from typing import Any

from agentic_factory.job.outputs.contract import Schema

INSTRUCTION = (
    "When you are done, state these outputs plainly in your final message, each on its own "
    "line as `name: value`, lists as json arrays. Put them before anything else you were "
    "asked to end the message with:"
)


def wrap_prompt(prompt: str, schema: Schema) -> str:
    """The prompt the workflow gives the job: the job's own, then the request
    to state the outputs, one line per field with its type and description.
    The engine adds the summary request after it, so the outputs come first
    in the coder's last message."""
    return f"{prompt}\n\n{INSTRUCTION}\n{field_lines(schema)}"


def field_lines(schema: Schema) -> str:
    properties: dict[str, dict[str, Any]] = schema.get("properties", {})
    return "\n".join(_field_line(name, field) for name, field in properties.items())


def _field_line(name: str, field: dict[str, Any]) -> str:
    description = field.get("description", "")
    return f"- {name} ({_type_name(field)}): {description}".rstrip(": ")


def _type_name(field: dict[str, Any]) -> str:
    """`array of string`, `string`, `object`, ...: the type as the coder should read it."""
    kind = str(field.get("type", "object"))
    if kind == "array":
        return f"array of {_type_name(field.get('items', {}))}"
    return kind
