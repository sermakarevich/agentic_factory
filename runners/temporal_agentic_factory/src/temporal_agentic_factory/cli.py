import asyncio
import logging
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer

from agentic_factory.job.contract import Job, JobResult
from agentic_factory.observe.log import configure_logging
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.runner import serve
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import JobWorkflow

app = typer.Typer(no_args_is_help=True, help="agentic_factory on Temporal.")

JOB_FIELDS = ("provider", "model", "timeout_sec", "stall_sec", "context_limit_tokens", "tools")


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
    given = locals()
    fields: dict[str, Any] = {k: given[k] for k in JOB_FIELDS if given[k] is not None}
    if "tools" in fields:
        fields["tools"] = [t for t in fields["tools"].split(",") if t]
    # absolute: the runner's cwd is not ours
    job = Job(prompt=prompt, workdir=str(Path(workdir).expanduser().resolve()), **fields)
    result = asyncio.run(_run(job))
    typer.echo(result.model_dump_json(indent=2))


async def _run(job: Job) -> JobResult:
    client = await connect()
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=f"job-{uuid4().hex[:8]}",
        task_queue=settings.temporal.task_queue,
    )
    typer.echo(f"started {handle.id}", err=True)
    try:
        return await handle.result()
    except asyncio.CancelledError:  # ctrl-c: stop the run, not just the wait
        await handle.cancel()
        raise
