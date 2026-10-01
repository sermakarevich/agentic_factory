"""The helpers that turn command-line option values into what the contracts want,
shared by both cli modules."""

import json
from pathlib import Path
from typing import Any

from agentic_factory.job.structured_output.contract import Schema


def absolute(path: str) -> str:
    """The runner's cwd is not ours, so the job gets an absolute path."""
    return str(Path(path).expanduser().resolve())


def source_url(url: str) -> str:
    """A local path made absolute, since the runner's cwd is not ours; a URL as given."""
    return url if "://" in url else absolute(url)


def tool_list(tools: str | None) -> list[str] | None:
    return [t for t in tools.split(",") if t] if tools is not None else None


def schema(option: str) -> Schema:
    """The `--structured-output` option as a JSON schema: given inline, or as `@file`."""
    text = Path(option[1:]).read_text() if option.startswith("@") else option
    parsed: Schema = json.loads(text)
    return parsed


def given(options: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in options.items() if value is not None}
