"""Fake submission activities for a workflow test whose jobs submit their
structured output: the schema is remembered by session at the ask, and the
read gives what the test's own `output` function gives for it, with a done
report."""

from collections.abc import Callable
from typing import Any

from temporalio import activity

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.job.submission.ask import AskedJob, asked_job
from agentic_factory.job.submission.contract import Schema
from agentic_factory.job.submission.schema import submission_schema
from agentic_factory.job.submission.submit import Submitted
from temporal_agentic_factory.workflows.job.submission import SubmissionRequest

Output = Callable[[str, Schema], dict[str, Any]]
REPORT = JobReport(task="t", done=["the output"], not_done=[], problems=[], verdict=Verdict.DONE)


def submitted_by(output: Output) -> list[Callable[..., Any]]:
    """`ask_for_submission` and `read_submission`, every job having submitted
    a done report and, when it was asked for one, what `output` gives for its
    session and output schema."""
    schemas: dict[str, Schema | None] = {}

    @activity.defn(name="ask_for_submission")
    async def fake_ask(request: SubmissionRequest) -> AskedJob:
        job = request.job
        schemas[job.session_id] = request.output_schema
        schema = submission_schema(request.output_schema)
        return asked_job(job, schema, "af", harness_for(job.provider))

    @activity.defn(name="read_submission")
    async def fake_read(session_id: str) -> Submitted:
        schema = schemas[session_id]
        return Submitted(report=REPORT, output=output(session_id, schema) if schema else None)

    return [fake_ask, fake_read]
