"""Fake submission activities for a workflow test whose jobs submit their
structured output: the schema is remembered by session at the ask, and the
read gives what the test's own fake extraction would give for it."""

from collections.abc import Awaitable, Callable
from typing import Any

from temporalio import activity

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.structured_output.ask import AskedJob, asked_job
from agentic_factory.job.structured_output.contract import Schema
from temporal_agentic_factory.workflows.structured_output.extract import StructuredOutputRequest
from temporal_agentic_factory.workflows.structured_output.submission import SubmissionRequest

Extract = Callable[[StructuredOutputRequest], Awaitable[dict[str, Any]]]


def submitted_by(extract: Extract) -> list[Callable[..., Any]]:
    """`ask_for_submission` and `read_submitted_output`, every job having
    submitted what `extract` says for its session and schema."""
    schemas: dict[str, Schema] = {}

    @activity.defn(name="ask_for_submission")
    async def fake_ask(request: SubmissionRequest) -> AskedJob:
        job = request.job
        schemas[job.session_id] = request.output_schema
        return asked_job(job, request.output_schema, "af", harness_for(job.provider))

    @activity.defn(name="read_submitted_output")
    async def fake_read(session_id: str) -> dict[str, Any] | None:
        request = StructuredOutputRequest(session_id=session_id, output_schema=schemas[session_id])
        return await extract(request)

    return [fake_ask, fake_read]
