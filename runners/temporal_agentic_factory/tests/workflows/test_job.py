import uuid

from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    CancelledError,
    TimeoutError,
    TimeoutType,
)
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from temporal_agentic_factory import search_attributes
from temporal_agentic_factory.activities.job import TryResult
from temporal_agentic_factory.activities.report import ReportRequest
from temporal_agentic_factory.workflows.job import JobWorkflow, _failure_text

tries: list[int] = []
sessions: list[str] = []
report_requests: list[ReportRequest] = []
recorded: list[JobOutcome] = []


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    return "s1"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> TryResult:
    """Fails once, then answers. Stands in for the real activity."""
    tries.append(activity.info().attempt)
    sessions.append(job.session_id)
    if activity.info().attempt == 1:
        raise ApplicationError("no output", type="Stalled")
    return TryResult(result=JobResult(session_id=job.session_id, cost_usd=0.5), runner="r1")


@activity.defn(name="build_report")
async def fake_report(request: ReportRequest) -> JobReport:
    report_requests.append(request)
    return JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.DONE)


@activity.defn(name="record_job")
async def fake_record(outcome: JobOutcome) -> None:
    recorded.append(outcome)


async def _environment() -> WorkflowEnvironment:
    """A test server with the job's search attributes, as `factory attributes`
    gives a real one; without them the workflow's upserts are refused."""
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    await search_attributes.add(env.client, "default", [key.name for key in search_attributes.KEYS])
    return env


async def test_job_workflow_retries_the_activity_and_returns_its_result() -> None:
    tries.clear()
    sessions.clear()
    report_requests.clear()
    recorded.clear()
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[JobWorkflow],
            activities=[fake_session, fake_job, fake_report, fake_record],
        ):
            handle = await env.client.start_workflow(
                JobWorkflow.run,
                Job(prompt="hi", workdir=".", model="m"),
                id=f"j-{uuid.uuid4()}",
                task_queue=queue,
            )
            result = await handle.result()
            shown = (await handle.describe()).typed_search_attributes
    assert tries == [1, 2] and sessions == ["s1", "s1"]  # one session, made before try 1
    assert shown.get(search_attributes.RUNNER) == "r1"  # what the ui's columns show
    assert shown.get(search_attributes.OUTCOME) == "done"
    assert shown.get(search_attributes.VERDICT) == "done"
    assert result.result is not None
    assert result.session_id == "s1"
    assert result.result.session_id == "s1" and result.result.cost_usd == 0.5
    assert result.report is not None and result.report.verdict == Verdict.DONE
    assert len(report_requests) == 1 and report_requests[0].result is not None
    assert report_requests[0].result.session_id == "s1"
    assert recorded == [result]  # the job row is written from the outcome, after the report


def test_failure_text_names_what_ended_the_last_try() -> None:
    def failed_with(cause: BaseException) -> ActivityError:
        error = ActivityError(
            "activity failed",
            scheduled_event_id=1,
            started_event_id=2,
            identity="runner",
            activity_type="execute_job",
            activity_id="1",
            retry_state=None,
        )
        error.__cause__ = cause
        return error

    typed = _failure_text(failed_with(ApplicationError("no output", type="Stalled")))
    assert typed == "Stalled: no output"
    timeout = _failure_text(
        failed_with(TimeoutError("t", type=TimeoutType.HEARTBEAT, last_heartbeat_details=[]))
    )
    assert timeout == "Timeout: heartbeat"
    assert _failure_text(failed_with(CancelledError("c"))).startswith("Cancelled")


async def test_a_permanently_failed_job_still_gets_a_report() -> None:
    @activity.defn(name="execute_job")
    async def always_fails(job: Job) -> TryResult:
        raise ApplicationError("no output", type="Stalled")

    report_requests.clear()
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[JobWorkflow],
            activities=[fake_session, always_fails, fake_report, fake_record],
        ):
            result = await env.client.execute_workflow(
                JobWorkflow.run,
                Job(prompt="hi", workdir=".", model="m"),
                id=f"j-{uuid.uuid4()}",
                task_queue=queue,
            )
    assert result.result is None
    assert result.failure.startswith("Stalled")
    assert result.report is not None and result.report.verdict == Verdict.DONE


async def test_a_failed_report_is_not_fatal() -> None:
    @activity.defn(name="build_report")
    async def broken_report(request: ReportRequest) -> JobReport:
        raise ApplicationError("bad", type="BadOutput", non_retryable=True)

    report_requests.clear()
    tries.clear()
    sessions.clear()
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[JobWorkflow],
            activities=[fake_session, fake_job, broken_report, fake_record],
        ):
            result = await env.client.execute_workflow(
                JobWorkflow.run,
                Job(prompt="hi", workdir=".", model="m"),
                id=f"j-{uuid.uuid4()}",
                task_queue=queue,
            )
    assert result.result is not None and result.result.session_id == "s1"
    assert result.report is None


async def test_a_failed_record_is_not_fatal() -> None:
    @activity.defn(name="record_job")
    async def broken_record(outcome: JobOutcome) -> None:
        raise ApplicationError("db down", type="OSError", non_retryable=True)

    tries.clear()
    sessions.clear()
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[JobWorkflow],
            activities=[fake_session, fake_job, fake_report, broken_record],
        ):
            result = await env.client.execute_workflow(
                JobWorkflow.run,
                Job(prompt="hi", workdir=".", model="m"),
                id=f"j-{uuid.uuid4()}",
                task_queue=queue,
            )
    assert result.result is not None and result.report is not None
