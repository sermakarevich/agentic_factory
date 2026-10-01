"""A job run as a child workflow of the calling one: its own row in the UI,
its own history and search attributes."""

from temporalio import workflow
from temporalio.workflow import ParentClosePolicy

with workflow.unsafe.imports_passed_through():
    from temporalio.exceptions import (
        ApplicationError,
        ChildWorkflowError,
        FailureError,
        is_cancelled_exception,
    )

    from agentic_factory.job.contract import Job
    from agentic_factory.job.outcome import JobOutcome
    from temporal_agentic_factory.workflows.job import search_attributes
    from temporal_agentic_factory.workflows.job.workflow import (
        JobWorkflow,
        done_or_raised,
        job_failed,
    )


async def run_job_with_report(job: Job) -> JobOutcome:
    """The job workflow as a child, waited for: the job, its report and its
    row. A child that failed anyway (a timeout, a termination) is an outcome
    with that failure, as a failed job is; a cancellation is raised."""
    try:
        return await workflow.execute_child_workflow(
            JobWorkflow.run,
            job,
            id=child_id(job.name),
            static_summary=job.name,
            search_attributes=search_attributes.at_start(job, job.name),
            parent_close_policy=ParentClosePolicy.REQUEST_CANCEL,
        )
    except ChildWorkflowError as error:
        if is_cancelled_exception(error):
            raise
        return JobOutcome(session_id=job.session_id, failure=failure_text(error))


async def run_job_or_fail(job: Job) -> JobOutcome:
    """`run_job_with_report` for a workflow whose next step needs what this
    job made: a job that failed for good raises the named JobFailed, so the
    workflow stops there instead of building on nothing."""
    return done_or_raised(job, await run_job_with_report(job))


def child_id(name: str) -> str:
    """`<this workflow's id>/<name>`: `research-agent-memory-4f2a/topic/01`."""
    return f"{workflow.info().workflow_id}/{name}"


def failure_text(error: ChildWorkflowError) -> str:
    """What ended the child, as `Kind: message`: its typed error, else what Temporal says."""
    typed = typed_cause(error)
    if typed:
        return f"{typed.type}: {typed.message}"
    return f"{type(error.cause).__name__}: {error.cause}" if error.cause else str(error)


def raised_for(job: Job, error: ChildWorkflowError) -> BaseException:
    """What a failed child job raises in its parent: a cancellation as it is,
    the child's own typed error (JobFailed, StructuredOutputNotStated, ...)
    as the same type and message, anything else as the named JobFailed."""
    if is_cancelled_exception(error):
        return error
    typed = typed_cause(error)
    if typed:
        return ApplicationError(typed.message, type=typed.type, non_retryable=True)
    return job_failed(job, failure_text(error))


def typed_cause(error: FailureError) -> ApplicationError | None:
    """The first typed error under `error`: the child's own, or the one its
    failed activity raised."""
    cause = error.cause
    while isinstance(cause, FailureError):
        if isinstance(cause, ApplicationError):
            return cause
        cause = cause.cause
    return None
