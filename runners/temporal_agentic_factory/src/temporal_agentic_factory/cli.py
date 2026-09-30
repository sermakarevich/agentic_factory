import asyncio
import json
import logging
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import typer
from temporalio.client import WorkflowHandle

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.outputs.contract import Schema
from agentic_factory.logging_setup import configure_logging
from temporal_agentic_factory import search_attributes
from temporal_agentic_factory.client import connect
from temporal_agentic_factory.identity import runner_identity
from temporal_agentic_factory.runner import serve
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import JobWorkflow
from temporal_agentic_factory.workflows.outputs import (
    JobWithOutputs,
    JobWithOutputsWorkflow,
    OutputsJob,
)

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
    outputs: Annotated[
        str | None, typer.Option(help="JSON schema of the outputs the job must state, or @file")
    ] = None,
) -> None:
    """Start one job on Temporal and wait for it. Prints the result as JSON.
    Options left out keep the settings defaults. With --outputs the job must
    state them and the result carries them."""
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
    if outputs is None:
        typer.echo(asyncio.run(_job_outcome(job)).model_dump_json(indent=2))
    else:
        typer.echo(asyncio.run(_job_with_outputs(job, _schema(outputs))).model_dump_json(indent=2))


def _tool_list(tools: str | None) -> list[str] | None:
    return [t for t in tools.split(",") if t] if tools is not None else None


def _absolute(workdir: str) -> str:
    """The runner's cwd is not ours, so the job gets an absolute path."""
    return str(Path(workdir).expanduser().resolve())


def _schema(option: str) -> Schema:
    """The `--outputs` option as a JSON schema: given inline, or as `@file`."""
    text = Path(option[1:]).read_text() if option.startswith("@") else option
    schema: Schema = json.loads(text)
    return schema


def _given(options: dict[str, Any]) -> dict[str, Any]:
    return {name: value for name, value in options.items() if value is not None}


async def _registered_attributes() -> list[str]:
    return await search_attributes.register(await connect(), settings.temporal.namespace)


async def _job_outcome(job: Job) -> JobOutcome:
    """The job workflow started and waited for."""
    client = await connect()
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=f"job-{uuid4().hex[: settings.cli.job_id_chars]}",
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job),
    )
    return await _awaited(handle)


async def _job_with_outputs(job: Job, schema: Schema) -> JobWithOutputs:
    """The job-with-outputs workflow started and waited for."""
    client = await connect()
    handle = await client.start_workflow(
        JobWithOutputsWorkflow.run,
        OutputsJob(job=job, outputs_schema=schema),
        id=f"job-{uuid4().hex[: settings.cli.job_id_chars]}",
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job),
    )
    return await _awaited(handle)


async def _awaited[T](handle: WorkflowHandle[Any, T]) -> T:
    """The workflow's result; ctrl-c stops the run, not just the wait."""
    typer.echo(f"started {handle.id}", err=True)
    try:
        return await handle.result()
    except asyncio.CancelledError:
        await handle.cancel()
        raise
