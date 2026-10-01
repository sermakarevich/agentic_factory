"""The `af output` commands a coder runs on its job's result: submit, schema, show."""

import json
import sys
from pathlib import Path
from typing import Annotated, Any, NoReturn

import typer
from factory_settings.shared import shared
from factory_store.store import Store, StoredReport, StoredStructuredOutput

from agentic_factory.job.submission import submit as submission
from agentic_factory.job.submission.check import Checked
from agentic_factory.job.submission.contract import Schema
from temporal_agentic_factory.cli.errors import run_coro

UNKNOWN = 2  # the exit code of a session with no schema saved; 1 is an invalid submission

output_app = typer.Typer(
    no_args_is_help=True,
    help="The result a coder submits for its job, its report and output: submit, schema, show.",
)


def opened_store() -> Store:
    """The store of the shared settings, where the workflow saved the schema."""
    return Store.from_url(shared.store.url)


@output_app.command()
def submit(
    session_id: str,
    file: Annotated[Path | None, typer.Option(help="Read the JSON here, not on stdin.")] = None,
) -> None:
    """Check the JSON on stdin, `{"report": ..., "output": ...}`, against the
    session's schema; save both parts when it matches. Prints `ok` (exit 0),
    or `invalid:` and every error (exit 1, nothing saved)."""
    text = file.read_text() if file else sys.stdin.read()
    checked = run_coro(_submitted(session_id, text))
    if checked is None:
        exit_unknown(session_id)
    if checked.errors:
        typer.echo("\n".join(["invalid:", *checked.errors]))
        raise typer.Exit(1)
    typer.echo("ok")


@output_app.command()
def schema(session_id: str) -> None:
    """Print the JSON Schema the session's submission is checked against: the
    report and, when the job asks for one, the output."""
    found = run_coro(_schema(session_id))
    if found is None:
        exit_unknown(session_id)
    typer.echo(json.dumps(found, indent=2))


@output_app.command()
def show(session_id: str) -> None:
    """Print the session's saved report and output, or say what is missing."""
    report, output = run_coro(_saved(session_id))
    if report is None:
        typer.echo(f"no report saved for session {session_id}")
    else:
        typer.echo("report:")
        typer.echo(_json(report.report))
    if output is None:
        typer.echo(f"no structured output saved for session {session_id}")
    else:
        typer.echo(f"output (source: {output.source}):")
        typer.echo(_json(output.structured_output))


def _json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2)


def exit_unknown(session_id: str) -> NoReturn:
    """A session with no schema saved: one stderr line and exit 2."""
    message = f"no submission schema is saved for session {session_id}"
    typer.echo(f"af: error: {message}", err=True)
    raise typer.Exit(UNKNOWN)


async def _submitted(session_id: str, text: str) -> Checked | None:
    """The app's submit; None when the session has no schema."""
    store = opened_store()
    try:
        return await submission.submit(store, session_id, text)
    except submission.NoSchemaSaved:
        return None
    finally:
        await store.dispose()


async def _schema(session_id: str) -> Schema | None:
    store = opened_store()
    try:
        return await store.load_output_schema(session_id)
    finally:
        await store.dispose()


async def _saved(session_id: str) -> tuple[StoredReport | None, StoredStructuredOutput | None]:
    store = opened_store()
    try:
        return await store.load_report(session_id), await store.load_structured_output(session_id)
    finally:
        await store.dispose()
