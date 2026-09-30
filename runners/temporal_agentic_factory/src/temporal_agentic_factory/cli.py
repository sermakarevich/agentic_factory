import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer

from agentic_factory.callbacks.log import configure_logging
from agentic_factory.job.contract import Job
from agentic_factory.job.outcome import JobOutcome
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.runner import serve
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import JobWorkflow

app = typer.Typer(no_args_is_help=True, help="agentic_factory on Temporal.")


@app.command()
def runner(debug: bool = False) -> None:
    """Start the process that polls Temporal task queues."""
    configure_logging(logging.DEBUG if debug else logging.INFO)
    asyncio.run(serve())


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
    outcome = asyncio.run(_job_outcome(job))
    typer.echo(outcome.model_dump_json(indent=2))


def _tool_list(tools: str | None) -> list[str] | None:
    return [t for t in tools.split(",") if t] if tools is not None else None


def _absolute(workdir: str) -> str:
    """The runner's cwd is not ours, so the job gets an absolute path."""
    return str(Path(workdir).expanduser().resolve())


def _given(options: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in options.items() if value is not None}


JOB_ID_CHARS = 8  # of the uuid, after "job-": enough to tell runs apart in the ui


async def _job_outcome(job: Job) -> JobOutcome:
    """The job workflow started and waited for; ctrl-c stops the run, not just the wait."""
    client = await connect()
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=f"job-{uuid4().hex[:JOB_ID_CHARS]}",
        task_queue=settings.temporal.task_queue,
    )
    typer.echo(f"started {handle.id}", err=True)
    try:
        return await handle.result()
    except asyncio.CancelledError:
        await handle.cancel()
        raise
