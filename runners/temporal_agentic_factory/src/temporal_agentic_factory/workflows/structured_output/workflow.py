from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel, Field

    from agentic_factory.job.contract import Job
    from agentic_factory.job.outcome import JobOutcome
    from agentic_factory.job.structured_output.contract import Schema
    from agentic_factory.job.structured_output.prompt import wrap_prompt
    from agentic_factory.settings.load import settings as app_settings
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.job.workflow import run_job_or_fail
    from temporal_agentic_factory.workflows.structured_output.extract import (
        StructuredOutputActivity,
        StructuredOutputRequest,
    )

EXTRACTION_STEPS = 2  # the last message, then the whole conversation when that was not enough


class StructuredOutputJob(BaseModel):
    """A job and the shape of the structured output it must state."""

    job: Job
    output_schema: Schema


class JobWithStructuredOutput(BaseModel):
    """What the workflow returns: the job's outcome and the structured output
    it stated, matching the schema it was given. A caller with a model
    validates it: `Model.model_validate(result.structured_output)`."""

    outcome: JobOutcome
    structured_output: dict[str, Any] = Field(default_factory=dict)


@workflow.defn(name="job_with_structured_output")
class JobWithStructuredOutputWorkflow:
    """One job that must state a structured output; fails when it did not."""

    @workflow.run
    async def run(self, request: StructuredOutputJob) -> JobWithStructuredOutput:
        return await run_job_with_structured_output(request.job, request.output_schema)


async def run_job_with_structured_output(job: Job, schema: Schema) -> JobWithStructuredOutput:
    """For any workflow with a job whose structured output it needs: the
    output asked for in the prompt, the job run with its report, then the
    extraction activity over what it wrote. A job that failed for good has
    nothing to extract, and an output the coder never stated cannot be made
    up: either raises, so the workflow stops where fleet stopped on a
    missing outputs file."""
    asked = job.model_copy(update={"prompt": wrap_prompt(job.prompt, schema)})
    outcome = await run_job_or_fail(asked)
    request = StructuredOutputRequest(session_id=outcome.session_id, output_schema=schema)
    extracted = await _extracted(request, job.name)
    return JobWithStructuredOutput(outcome=outcome, structured_output=extracted)


async def _extracted(request: StructuredOutputRequest, name: str) -> dict[str, Any]:
    """The extraction activity, given as long as its steps take plus a
    margin, with the structured output activity's retry policy, labeled
    with the job's name in the UI."""
    cfg = settings.structured_output_activity
    timeout_sec = EXTRACTION_STEPS * app_settings.step.timeout_sec + cfg.close_margin_sec
    return await workflow.execute_activity_method(
        StructuredOutputActivity.extract_structured_output,
        request,
        start_to_close_timeout=timedelta(seconds=timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
        summary=name,
    )
