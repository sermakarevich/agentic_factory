import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.logging_setup import configure_logging
from temporal_agentic_factory import search_attributes
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.identity import runner_identity
from temporal_agentic_factory.runner import serve
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import JobWorkflow

app = typer.Typer(no_args_is_help=True, help="agentic_factory on Temporal.")


@app.command()
def runner(debug: bool = False) -> None:
    """Start the process that polls Temporal task queues."""
    configure_logging(logging.DEBUG if debug else logging.INFO)
    identity = runner_identity()
    typer.echo(f"runner {identity}", err=True)
    asyncio.run(serve(identity))


@app.command()
def attributes() -> None:
    """Register the job's search attributes on the server, once per server.
    The UI then offers them as columns and filters."""
    added = asyncio.run(_registered_attributes())
    typer.echo(f"added {', '.join(added)}" if added else "all attributes were registered already")


@app.command()
def run(
    prompt: str,
    workdir: str = ".",
    provider: str | None = None,
    model: str | None = None,
    timeout_sec: int | None = None,
    stall_sec: int | None = None,
    context_limit_tokens: int | None = None,
    tools: Annotated[str | None, typer.Option(help="comma-separated allow-list")] = None,
) -> None:
    """Start one job on Temporal and wait for it. Prints the result as JSON.
    Options left out keep the settings defaults."""
    options = {
        "provider": provider,
        "model": model,
        "timeout_sec": timeout_sec,
        "stall_sec": stall_sec,
        "context_limit_tokens": context_limit_tokens,
        "tools": _tool_list(tools),
    }
    job = Job(prompt=prompt, workdir=_absolute(workdir), **_given(options))
    job = with_default_model(job, harness_for(job.provider))  # so the UI shows the model
    outcome = asyncio.run(_job_outcome(job))
    typer.echo(outcome.model_dump_json(indent=2))


def _tool_list(tools: str | None) -> list[str] | None:
    return [t for t in tools.split(",") if t] if tools is not None else None


def _absolute(workdir: str) -> str:
    """The runner's cwd is not ours, so the job gets an absolute path."""
    return str(Path(workdir).expanduser().resolve())


def _given(options: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in options.items() if value is not None}


async def _registered_attributes() -> list[str]:
    return await search_attributes.register(await connect(), settings.temporal.namespace)


async def _job_outcome(job: Job) -> JobOutcome:
    """The job workflow started and waited for; ctrl-c stops the run, not just the wait."""
    client = await connect()
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=f"job-{uuid4().hex[: settings.cli.job_id_chars]}",
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job),
    )
    typer.echo(f"started {handle.id}", err=True)
    try:
        return await handle.result()
    except asyncio.CancelledError:
        await handle.cancel()
        raise
