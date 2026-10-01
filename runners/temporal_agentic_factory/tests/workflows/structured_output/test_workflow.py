import uuid
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.job.structured_output.ask import AskedJob, asked_job
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.execute import TryResult
from temporal_agentic_factory.workflows.job.report import ReportRequest
from temporal_agentic_factory.workflows.job.workflow import JobWorkflow
from temporal_agentic_factory.workflows.structured_output.child import (
    run_job_with_structured_output,
)
from temporal_agentic_factory.workflows.structured_output.extract import StructuredOutputRequest
from temporal_agentic_factory.workflows.structured_output.submission import SubmissionRequest
from temporal_agentic_factory.workflows.structured_output.workflow import (
    JobWithStructuredOutputWorkflow,
    StructuredOutputJob,
)
from tests.workers import running

SCHEMA = {"type": "object", "properties": {"urls": {"type": "array", "items": {"type": "string"}}}}
SUBMITTED = {"urls": ["submitted"]}
EXTRACTED = {"urls": ["extracted"]}
jobs: list[Job] = []
asked: list[SubmissionRequest] = []
reads: list[str] = []
extractions: list[StructuredOutputRequest] = []
submissions: list[dict[str, Any] | None] = []  # what each read gives, in turn; then None


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    return "s1"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> TryResult:
    jobs.append(job)
    return TryResult(result=JobResult(session_id=job.session_id, cost_usd=0.5), runner="r1")


@activity.defn(name="execute_job")
async def failing_job(job: Job) -> TryResult:
    raise ApplicationError("no output", type="Stalled", non_retryable=True)


@activity.defn(name="build_report")
async def fake_report(request: ReportRequest) -> JobReport:
    return JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.DONE)


@activity.defn(name="record_job")
async def fake_record(outcome: JobOutcome) -> None:
    return None


@activity.defn(name="ask_for_submission")
async def fake_ask(request: SubmissionRequest) -> AskedJob:
    asked.append(request)
    return asked_job(request.job, request.output_schema, "af", harness_for(request.job.provider))


@activity.defn(name="read_submitted_output")
async def fake_read(session_id: str) -> dict[str, Any] | None:
    reads.append(session_id)
    return submissions.pop(0) if submissions else None


@activity.defn(name="extract_structured_output")
async def fake_extract(request: StructuredOutputRequest) -> dict[str, Any]:
    extractions.append(request)
    return EXTRACTED


@activity.defn(name="extract_structured_output")
async def nothing_stated(request: StructuredOutputRequest) -> dict[str, Any]:
    raise ApplicationError(
        "the coder did not state: urls", type="StructuredOutputNotStated", non_retryable=True
    )


def _submitting(*outputs: dict[str, Any] | None) -> None:
    """Every record cleared, and the reads to give `outputs` in turn."""
    for record in (jobs, asked, reads, extractions, submissions):
        record.clear()
    submissions.extend(outputs)


async def _environment() -> WorkflowEnvironment:
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    await search_attributes.add(env.client, "default", [key.name for key in search_attributes.KEYS])
    return env


async def _run(execute: Any, extract: Any) -> Any:
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with running(
            env.client,
            queue,
            [JobWithStructuredOutputWorkflow],
            [fake_session, fake_report, fake_record, fake_ask, fake_read, extract],
            execute,
        ):
            return await env.client.execute_workflow(
                JobWithStructuredOutputWorkflow.run,
                StructuredOutputJob(
                    job=Job(name="urls", prompt="fetch", workdir=".", model="m"),
                    output_schema=SCHEMA,
                ),
                id=f"j-{uuid.uuid4()}",
                task_queue=queue,
            )


async def test_a_submitted_output_is_the_result_and_nothing_is_extracted() -> None:
    _submitting(SUBMITTED)
    result = await _run(fake_job, fake_extract)

    assert result.structured_output == SUBMITTED and extractions == []
    assert result.outcome.session_id == "s1" and result.outcome.report is not None
    (request,) = asked
    assert request.job.session_id == "s1" and request.output_schema == SCHEMA
    (job,) = jobs
    assert job.prompt.startswith("fetch\n\n") and "af output submit s1 <<'JSON'" in job.prompt
    assert '"urls"' in job.prompt and reads == ["s1"]


async def test_a_coder_that_did_not_submit_is_reminded_in_its_session() -> None:
    _submitting(None, SUBMITTED)
    result = await _run(fake_job, fake_extract)

    assert result.structured_output == SUBMITTED and extractions == []
    first, reminder = jobs
    assert reminder.name == "urls/reminder" and reminder.session_id == first.session_id == "s1"
    assert reminder.try_offset == settings.job_activity.max_attempts
    assert "af output submit s1" in reminder.prompt and reads == ["s1", "s1"]
    assert result.outcome.result.cost_usd == pytest.approx(1.0)


async def test_nothing_submitted_after_the_reminders_falls_back_to_the_extraction() -> None:
    _submitting()
    result = await _run(fake_job, fake_extract)

    assert result.structured_output == EXTRACTED
    assert extractions == [StructuredOutputRequest(session_id="s1", output_schema=SCHEMA)]
    reminders = settings.structured_output_workflow.submit_reminders
    assert len(jobs) == 1 + reminders and len(reads) == 1 + reminders


async def test_nothing_submitted_with_the_fallback_off_fails_the_workflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings.structured_output_workflow, "llm_fallback", False)
    _submitting()
    with pytest.raises(WorkflowFailureError) as err:
        await _run(fake_job, fake_extract)

    cause = err.value.cause
    assert isinstance(cause, ApplicationError) and cause.type == "StructuredOutputNotStated"
    assert cause.message.startswith("urls: ") and extractions == []


async def test_a_job_that_failed_for_good_fails_the_workflow() -> None:
    _submitting()
    with pytest.raises(WorkflowFailureError) as err:
        await _run(failing_job, fake_extract)
    assert isinstance(err.value.cause, ApplicationError) and err.value.cause.type == "JobFailed"
    assert err.value.cause.message.startswith("urls: Stalled")


async def test_structured_output_not_stated_by_the_fallback_fails_the_workflow() -> None:
    _submitting()
    with pytest.raises(WorkflowFailureError) as err:
        await _run(fake_job, nothing_stated)
    step_failure = err.value.cause.cause if err.value.cause else None
    assert (
        isinstance(step_failure, ApplicationError)
        and step_failure.type == "StructuredOutputNotStated"
    )


@workflow.defn(name="parent", sandboxed=False)
class ParentWorkflow:
    """Needs one job's structured output, the way distill and research do."""

    @workflow.run
    async def run(self, job: Job) -> dict[str, Any]:
        return (await run_job_with_structured_output(job, SCHEMA)).structured_output


async def _parent_run(execute: Any, extract: Any) -> Any:
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with running(
            env.client,
            queue,
            [ParentWorkflow, JobWithStructuredOutputWorkflow, JobWorkflow],
            [fake_session, fake_report, fake_record, fake_ask, fake_read, extract],
            execute,
        ):
            parent_id = f"p-{uuid.uuid4()}"
            stated = await env.client.execute_workflow(
                ParentWorkflow.run,
                Job(name="urls", prompt="fetch", workdir=".", model="m"),
                id=parent_id,
                task_queue=queue,
            )
            child = await env.client.get_workflow_handle(f"{parent_id}/urls").describe()
            return stated, child


async def test_a_child_states_the_output_for_its_parent() -> None:
    _submitting(SUBMITTED)
    stated, child = await _parent_run(fake_job, fake_extract)
    assert stated == SUBMITTED
    assert child.workflow_type == "job_with_structured_output"
    assert child.typed_search_attributes.get(search_attributes.NAME) == "urls"


@pytest.mark.parametrize(
    ("execute", "extract", "error_type"),
    [
        (failing_job, fake_extract, "JobFailed"),
        (fake_job, nothing_stated, "StructuredOutputNotStated"),
    ],
)
async def test_a_failed_child_raises_its_own_error_type_in_the_parent(
    execute: Any, extract: Any, error_type: str
) -> None:
    _submitting()
    with pytest.raises(WorkflowFailureError) as err:
        await _parent_run(execute, extract)
    assert isinstance(err.value.cause, ApplicationError) and err.value.cause.type == error_type
