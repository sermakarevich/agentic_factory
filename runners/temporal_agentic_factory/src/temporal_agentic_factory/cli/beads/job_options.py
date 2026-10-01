"""The job options `af beads add` and `af beads set` share with `af run`, and the
`af_job` fields they make: only the options given, validated before any
bead is written."""

from pathlib import Path
from typing import Annotated, Any

import typer

from temporal_agentic_factory.cli.errors import fail
from temporal_agentic_factory.cli.options import given, schema, tool_list
from temporal_agentic_factory.cli.providers import refuse_unconfigured
from temporal_agentic_factory.watchers.beads.parameters import InvalidParameters, parameters_of

ProviderOption = Annotated[
    str | None, typer.Option(help="the coder: a configured [providers.<name>]")
]
ModelOption = Annotated[str | None, typer.Option(help="its model; empty = the provider's default")]
NameOption = Annotated[str | None, typer.Option(help="what the job is for; empty = the bead id")]
WorkdirOption = Annotated[
    Path | None,
    typer.Option(
        "--workdir",
        "--cwd",
        exists=True,
        file_okay=False,
        resolve_path=True,
        help="the folder the coder works in",
    ),
]
ToolsOption = Annotated[str | None, typer.Option(help="comma-separated allow-list")]
TimeoutOption = Annotated[int | None, typer.Option(help="the job's time limit in seconds")]
StallOption = Annotated[int | None, typer.Option(help="no output for this long = kill")]
ContextLimitOption = Annotated[
    int | None, typer.Option(help="context size at which the run is killed and retried")
]
StructuredOutputOption = Annotated[
    str | None,
    typer.Option(help="JSON schema of the structured output the job must state, or @file"),
]


def job_fields(options: dict[str, Any]) -> dict[str, Any]:
    """The `af_job` fields of the options given (None = not given), in the
    shapes Job wants; a clean exit when one is invalid or names a provider
    nobody runs."""
    fields = given(
        options
        | {
            "workdir": _text_or_none(options.get("workdir")),
            "tools": tool_list(options.get("tools")),
            "structured_output": _schema_or_none(options.get("structured_output")),
        }
    )
    checked = valid_fields(fields)
    if "provider" in checked:
        refuse_unconfigured(checked["provider"])
    return checked


def valid_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """`fields` checked as `af_job`; a clean exit naming what is wrong."""
    try:
        return parameters_of(fields, "job options")
    except InvalidParameters as error:
        fail(str(error))


def _text_or_none(path: Path | None) -> str | None:
    return str(path) if path is not None else None


def _schema_or_none(option: str | None) -> dict[str, Any] | None:
    """The `--structured-output` schema, inline or `@file`; a clean exit when unreadable."""
    if option is None:
        return None
    try:
        return schema(option)
    except (OSError, ValueError) as error:
        fail(f"--structured-output: {error}")
