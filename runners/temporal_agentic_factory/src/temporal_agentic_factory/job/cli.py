"""The `run` command: one job started on Temporal and waited for."""

import asyncio
from typing import Annotated
from uuid import uuid4

import typer

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job
from agentic_factory.job.defaults import with_default_model
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.structured_output.contract import Schema
from temporal_agentic_factory.client import awaited, connect
from temporal_agentic_factory.job import search_attributes
from temporal_agentic_factory.job.workflow import JobWorkflow
from temporal_agentic_factory.options import absolute, given, schema, tool_list
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.structured_output.workflow import (
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
) -> None:
    """Start one job on Temporal and wait for it. Prints the result as JSON.
    Options left out keep the settings defaults. With --structured-output the
    job must state it and the result carries it."""
    options = {
        "provider": provider,
        "model": model,
        "timeout_sec": timeout_sec,
        "stall_sec": stall_sec,
        "context_limit_tokens": context_limit_tokens,
        "tools": tool_list(tools),
    }
    job = Job(name=name, prompt=prompt, workdir=absolute(workdir), **given(options))
    job = with_default_model(job, harness_for(job.provider))  # so the UI shows the model
    if structured_output is None:
        typer.echo(asyncio.run(_job_outcome(job)).model_dump_json(indent=2))
    else:
        typer.echo(
            asyncio.run(
                _job_with_structured_output(job, schema(structured_output))
            ).model_dump_json(indent=2)
        )


async def _job_outcome(job: Job) -> JobOutcome:
    """The job workflow started and waited for."""
    client = await connect()
    handle = await client.start_workflow(
        JobWorkflow.run,
        job,
        id=f"job-{uuid4().hex[: settings.cli.job_id_chars]}",
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job),
        static_summary=job.name,
    )
    return await awaited(handle)


async def _job_with_structured_output(job: Job, output_schema: Schema) -> JobWithStructuredOutput:
    """The job-with-structured-output workflow started and waited for."""
    client = await connect()
    handle = await client.start_workflow(
        JobWithStructuredOutputWorkflow.run,
        StructuredOutputJob(job=job, output_schema=output_schema),
        id=f"job-{uuid4().hex[: settings.cli.job_id_chars]}",
        task_queue=settings.temporal.task_queue,
        search_attributes=search_attributes.at_start(job),
        static_summary=job.name,
    )
    return await awaited(handle)
