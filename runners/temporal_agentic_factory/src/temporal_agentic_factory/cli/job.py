"""The `run` command: one job submitted to Temporal, waited for by default."""

from typing import Annotated

import typer

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.structured_output.contract import Schema
from temporal_agentic_factory.cli.errors import run_coro
from temporal_agentic_factory.cli.ids import new_id
from temporal_agentic_factory.cli.options import absolute, given, schema, tool_list
from temporal_agentic_factory.cli.providers import refuse_unconfigured
from temporal_agentic_factory.client import awaited, connect
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.workflow import JobWorkflow
from temporal_agentic_factory.workflows.structured_output.workflow import (
    JobWithStructuredOutput,
    JobWithStructuredOutputWorkflow,
    StructuredOutputJob,
)


def run(
    prompt: str,
    workdir: str = ".",
    name: Annotated[str, typer.Option(help="what the job is for, in a word or two")] = "",
    provider: str | None = None,
    model: str | None = None,
    timeout_sec: int | None = None,
    stall_sec: int | None = None,
    context_limit_tokens: int | None = None,
    tools: Annotated[str | None, typer.Option(help="comma-separated allow-list")] = None,
    structured_output: Annotated[
        str | None,
        typer.Option(help="JSON schema of the structured output the job must state, or @file"),
    ] = None,
    detach: Annotated[
        bool, typer.Option("--detach", help="submit and print the workflow id without waiting")
    ] = False,
    workflow_id: Annotated[
        str | None,
        typer.Option(
            help="workflow id to start with; reusing one is idempotent. Empty = generated"
        ),
    ] = None,
) -> None:
    """Submit one job to Temporal. Waits and prints the result as JSON,
    or with --detach prints the workflow id and returns.
    Options left out keep the settings defaults. With --structured-output the
    job must state it and the result carries it. Refused for a provider with
    no `[providers.<name>]` table."""
    options = {
        "provider": provider,
        "model": model,
        "timeout_sec": timeout_sec,
        "stall_sec": stall_sec,
        "context_limit_tokens": context_limit_tokens,
        "tools": tool_list(tools),
    }
    job = Job(name=name, prompt=prompt, workdir=absolute(workdir), **given(options))
    refuse_unconfigured(job.provider)
    job = with_default_model(job, harness_for(job.provider))  # so the UI shows the model
    output_schema = schema(structured_output) if structured_output is not None else None
    wid = new_id("job", job.name, workflow_id)
    if detach:
        typer.echo(run_coro(_submitted_id(job, output_schema, wid)))
    elif output_schema is None:
        typer.echo(run_coro(_job_outcome(job, wid)).model_dump_json(indent=2))
    else:
        typer.echo(
            run_coro(_job_with_structured_output(job, output_schema, wid)).model_dump_json(indent=2)
        )


async def _submitted_id(job: Job, output_schema: Schema | None, wid: str) -> str:
    """The workflow started but not waited for: its id, for `af status` / `af result`."""
    if output_schema is None:
        return await _submitted_job_id(job, wid)
    return await _submitted_structured_id(job, output_schema, wid)


async def _submitted_job_id(job: Job, wid: str) -> str:
    client = await connect()
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=wid,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, job.name),
        static_summary=job.name,
    )
    typer.echo(f"started {handle.id}", err=True)
    return handle.id


async def _submitted_structured_id(job: Job, output_schema: Schema, wid: str) -> str:
    client = await connect()
    handle = await client.start_workflow(
        JobWithStructuredOutputWorkflow.run,
        StructuredOutputJob(job=job, output_schema=output_schema),
        id=wid,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, job.name),
        static_summary=job.name,
    )
    typer.echo(f"started {handle.id}", err=True)
    return handle.id


async def _job_outcome(job: Job, wid: str) -> JobOutcome:
    """The job workflow started and waited for."""
    client = await connect()
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=wid,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, job.name),
        static_summary=job.name,
    )
    return await awaited(handle)


async def _job_with_structured_output(
    job: Job, output_schema: Schema, wid: str
) -> JobWithStructuredOutput:
    """The job-with-structured-output workflow started and waited for."""
    client = await connect()
    handle = await client.start_workflow(
        JobWithStructuredOutputWorkflow.run,
        StructuredOutputJob(job=job, output_schema=output_schema),
        id=wid,
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job, job.name),
        static_summary=job.name,
    )
    return await awaited(handle)
