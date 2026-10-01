"""The job parameters at the very top of a bead's description: a `---` block
of `key: value` lines, then `---`. The block is cut from the prompt.

A value that starts with `{`, `[` or `"` is read as JSON (a schema, a list, a
quoted string); any other value is the text as written.
"""

import json
from typing import Any

FENCE = "---"
JSON_STARTS = ("{", "[", '"')


class FrontMatterError(ValueError):
    """A block that opens but does not parse."""


def split_front_matter(description: str) -> tuple[dict[str, Any], str]:
    """The block's fields and the description without it; ({}, description)
    when the description does not open with a block."""
    lines = description.splitlines()
    if not lines or lines[0].strip() != FENCE:
        return {}, description
    closing = _closing_line(lines)
    fields = dict(_field_of(line) for line in lines[1:closing] if line.strip())
    return fields, "\n".join(lines[closing + 1 :]).strip()


def _closing_line(lines: list[str]) -> int:
    """The index of the `---` that ends the block."""
    for at, line in enumerate(lines[1:], start=1):
        if line.strip() == FENCE:
            return at
    raise FrontMatterError("front matter opens with --- but never closes")


def _field_of(line: str) -> tuple[str, Any]:
    """One `key: value` line as its key and value."""
    key, colon, value = line.partition(":")
    if not colon or not key.strip():
        raise FrontMatterError(f"front matter line is not `key: value`: {line.strip()!r}")
    return key.strip(), _value_of(value.strip())


def _value_of(text: str) -> Any:
    """JSON for a JSON-looking value, the text itself for anything else."""
    if not text.startswith(JSON_STARTS):
        return text
    try:
        return json.loads(text)
    except ValueError as error:
        raise FrontMatterError(f"front matter value is not valid JSON: {text!r}") from error
