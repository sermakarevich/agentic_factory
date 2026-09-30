from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pydantic import BaseModel, Field
    from temporalio.exceptions import ApplicationError

    from agentic_factory.job.contract import Job
    from agentic_factory.job.outcome import JobOutcome
    from agentic_factory.job.outputs.contract import Schema
    from agentic_factory.job.outputs.prompt import wrap_prompt
    from agentic_factory.settings.load import settings as app_settings
    from temporal_agentic_factory.activities.outputs import OutputsActivity, OutputsRequest
    from temporal_agentic_factory.settings.load import settings
    from temporal_agentic_factory.workflows.job import run_job_with_report

EXTRACTION_STEPS = 2  # the last message, then the whole conversation when that was not enough


class OutputsJob(BaseModel):
    """A job and the shape of the outputs it must state."""

    job: Job
    outputs_schema: Schema


class JobWithOutputs(BaseModel):
    """What the workflow returns: the job's outcome and the outputs it
    stated, matching the schema it was given. A caller with a model
    validates them: `Model.model_validate(result.outputs)`."""

    outcome: JobOutcome
    outputs: dict[str, Any] = Field(default_factory=dict)


@workflow.defn(name="job_with_outputs")
class JobWithOutputsWorkflow:
    """One job that must state outputs; fails when it did not."""

    @workflow.run
    async def run(self, request: OutputsJob) -> JobWithOutputs:
        return await run_job_with_outputs(request.job, request.outputs_schema)


async def run_job_with_outputs(job: Job, schema: Schema) -> JobWithOutputs:
    """For any workflow with a job whose outputs it needs: the outputs asked
    for in the prompt, the job run with its report, then the extraction
    activity over what it wrote. A job that failed for good has nothing to
    extract, and outputs the coder never stated cannot be made up: either
    raises, so the workflow stops where fleet stopped on a missing outputs
    file."""
    asked = job.model_copy(update={"prompt": wrap_prompt(job.prompt, schema)})
    outcome = await run_job_with_report(asked)
    if outcome.result is None:
        raise ApplicationError(outcome.failure, type="JobFailed", non_retryable=True)
    request = OutputsRequest(session_id=outcome.session_id, outputs_schema=schema)
    return JobWithOutputs(outcome=outcome, outputs=await _extracted(request))


async def _extracted(request: OutputsRequest) -> dict[str, Any]:
    """The extraction activity, given as long as its steps take plus a
    margin, with the outputs policy."""
    cfg = settings.outputs_activity
    timeout_sec = EXTRACTION_STEPS * app_settings.step.timeout_sec + cfg.close_margin_sec
    return await workflow.execute_activity_method(
        OutputsActivity.extract_outputs,
        request,
        start_to_close_timeout=timedelta(seconds=timeout_sec),
        retry_policy=RetryPolicy(maximum_attempts=cfg.max_attempts),
    )
