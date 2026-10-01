import uuid
from typing import Any

import pytest
from temporalio import activity, workflow
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import (
    ActivityError,
    ApplicationError,
    CancelledError,
    TimeoutError,
    TimeoutType,
)
from temporalio.testing import WorkflowEnvironment

from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.job.submission.ask import AskedJob, asked_job
from agentic_factory.job.submission.contract import Schema
from agentic_factory.job.submission.schema import submission_schema
from agentic_factory.job.submission.submit import Submitted
from temporal_agentic_factory.settings.load import settings
from temporal_agentic_factory.workflows.job import search_attributes
from temporal_agentic_factory.workflows.job.child import (
    run_job_or_fail,
    run_job_with_report,
    run_job_with_structured_output,
)
from temporal_agentic_factory.workflows.job.coder_queue import coder_queue
from temporal_agentic_factory.workflows.job.execute import TryResult
from temporal_agentic_factory.workflows.job.submission import SubmissionRequest
from temporal_agentic_factory.workflows.job.workflow import JobRequest, JobWorkflow, _failure_text
from tests.workers import running

SCHEMA: Schema = {
    "type": "object",
    "properties": {"urls": {"type": "array", "items": {"type": "string"}}},
}
REPORT = JobReport(task="t", done=["wrote a.md"], not_done=[], problems=[], verdict=Verdict.DONE)
PLAIN = Submitted(report=REPORT)
WITH_OUTPUT = Submitted(report=REPORT, output={"urls": ["u"]})

tries: list[int] = []
queues: list[str] = []
jobs: list[Job] = []
asked: list[SubmissionRequest] = []
reads: list[str] = []
recorded: list[JobOutcome] = []
submissions: list[Submitted | None] = []  # what each read gives, in turn; then None


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    return "s1"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> TryResult:
    """Fails the first try of the first job, then answers. Stands in for the real activity."""
    tries.append(activity.info().attempt)
    queues.append(activity.info().task_queue)
    if activity.info().attempt == 1 and not jobs:
        raise ApplicationError("no output", type="Stalled")
    jobs.append(job)
    return TryResult(result=JobResult(session_id=job.session_id, cost_usd=0.5), runner="r1")


@activity.defn(name="execute_job")
async def always_fails(job: Job) -> TryResult:
    raise ApplicationError("no output", type="Stalled", non_retryable=True)


@activity.defn(name="ask_for_submission")
async def fake_ask(request: SubmissionRequest) -> AskedJob:
    asked.append(request)
    schema = submission_schema(request.output_schema)
    return asked_job(request.job, schema, "af", harness_for(request.job.provider))


@activity.defn(name="read_submission")
async def fake_read(session_id: str) -> Submitted | None:
    reads.append(session_id)
    return submissions.pop(0) if submissions else None


@activity.defn(name="record_job")
async def fake_record(outcome: JobOutcome) -> None:
    recorded.append(outcome)


QUICK = [fake_session, fake_ask, fake_read, fake_record]


def _submitting(*given: Submitted | None) -> None:
    """Every record cleared, and the reads to give `given` in turn."""
    for record in (tries, queues, jobs, asked, reads, recorded, submissions):
        record.clear()
    submissions.extend(given)


async def _environment() -> WorkflowEnvironment:
    """A test server with the job's search attributes, as `factory attributes`
    gives a real one; without them the workflow's upserts are refused."""
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    await search_attributes.add(env.client, "default", [key.name for key in search_attributes.KEYS])
    return env


def _request(output_schema: Schema | None = None) -> JobRequest:
    job = Job(name="urls", prompt="fetch", workdir=".", model="m")
    return JobRequest(job=job, output_schema=output_schema)


async def _run(
    request: JobRequest, execute: Any = fake_job, quick: list[Any] = QUICK
) -> tuple[JobOutcome, Any]:
    """The job workflow run to its end: its outcome and its search attributes."""
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with running(env.client, queue, [JobWorkflow], quick, execute):
            handle = await env.client.start_workflow(
                JobWorkflow.run, request, id=f"j-{uuid.uuid4()}", task_queue=queue
            )
            outcome = await handle.result()
            return outcome, (await handle.describe()).typed_search_attributes


async def test_a_plain_job_retries_its_tries_and_its_submitted_report_is_recorded() -> None:
    _submitting(PLAIN)
    outcome, shown = await _run(_request())

    assert tries == [1, 2] and len(jobs) == 1  # one job, two tries, no reminder
    (request,) = asked
    assert request.job.session_id == "s1" and request.output_schema is None
    (job,) = jobs
    assert job.session_id == "s1" and "af output submit s1 <<'JSON'" in job.prompt
    assert reads == ["s1"]
    assert outcome.result is not None and outcome.result.cost_usd == 0.5
    assert outcome.report == REPORT and outcome.output is None
    assert shown.get(search_attributes.RUNNER) == "r1"
    assert shown.get(search_attributes.OUTCOME) == "done"
    assert shown.get(search_attributes.VERDICT) == "done"
    assert recorded == [outcome]  # the job row is written once, from the outcome


async def test_a_structured_job_gives_its_output_and_its_report() -> None:
    _submitting(WITH_OUTPUT)
    outcome, _ = await _run(_request(SCHEMA))

    assert outcome.output == {"urls": ["u"]} and outcome.report == REPORT
    (request,) = asked
    assert request.output_schema == SCHEMA
    assert '"urls"' in jobs[0].prompt and '"report"' in jobs[0].prompt


async def test_a_coder_that_did_not_submit_is_reminded_in_its_session() -> None:
    _submitting(None, PLAIN)
    outcome, _ = await _run(_request())

    first, reminder = jobs
    assert reminder.name == "urls/reminder" and reminder.session_id == first.session_id == "s1"
    assert reminder.try_offset == settings.job_activity.max_attempts  # after the first job's
    assert "af output submit s1" in reminder.prompt and reads == ["s1", "s1"]
    assert outcome.report == REPORT
    assert outcome.result is not None and outcome.result.cost_usd == pytest.approx(1.0)
    assert recorded == [outcome]


async def test_a_plain_job_that_never_submitted_ends_with_verdict_unknown() -> None:
    _submitting()
    outcome, shown = await _run(_request())

    assert len(jobs) == 1 + settings.job_workflow.submit_reminders
    assert outcome.result is not None and outcome.report is None
    assert shown.get(search_attributes.VERDICT) == "unknown"
    assert recorded == [outcome]


async def test_a_structured_job_that_never_submitted_fails() -> None:
    _submitting()
    with pytest.raises(WorkflowFailureError) as err:
        await _run(_request(SCHEMA))

    cause = err.value.cause
    assert isinstance(cause, ApplicationError) and cause.type == "StructuredOutputNotStated"
    assert cause.message.startswith("urls: ")
    assert len(recorded) == 1 and recorded[0].report is None  # its row is still written


async def test_a_permanently_failed_job_gets_a_report_made_by_code() -> None:
    _submitting(PLAIN)
    outcome, shown = await _run(_request(), always_fails)

    assert outcome.result is None and outcome.failure.startswith("Stalled")
    assert outcome.report == JobReport(
        task="urls", done=[], not_done=[], problems=[outcome.failure], verdict=Verdict.FAILED
    )
    assert reads == [] and jobs == []  # no submission read, no reminder
    assert shown.get(search_attributes.OUTCOME) == "failed"
    assert shown.get(search_attributes.VERDICT) == "failed"


async def test_a_failed_structured_job_raises_job_failed() -> None:
    _submitting()
    with pytest.raises(WorkflowFailureError) as err:
        await _run(_request(SCHEMA), always_fails)

    cause = err.value.cause
    assert isinstance(cause, ApplicationError) and cause.type == "JobFailed"
    assert cause.message.startswith("urls: Stalled")


async def test_a_failed_record_is_not_fatal() -> None:
    @activity.defn(name="record_job")
    async def broken_record(outcome: JobOutcome) -> None:
        raise ApplicationError("db down", type="OSError", non_retryable=True)

    _submitting(PLAIN)
    outcome, _ = await _run(_request(), quick=[fake_session, fake_ask, fake_read, broken_record])
    assert outcome.result is not None and outcome.report == REPORT


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


def test_the_coder_queue_is_the_main_queue_with_the_provider() -> None:
    assert coder_queue("claude") == "agentic-factory-coder-claude"


async def test_the_execute_step_waits_in_the_providers_coder_queue() -> None:
    _submitting(PLAIN)
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with running(env.client, queue, [JobWorkflow], QUICK, fake_job):
            await env.client.execute_workflow(
                JobWorkflow.run,
                JobRequest(job=Job(prompt="hi", workdir=".", provider="claude", model="m")),
                id=f"j-{uuid.uuid4()}",
                task_queue=queue,
            )
    assert queues and set(queues) == {coder_queue("claude")}


@workflow.defn(name="parent", sandboxed=False)
class ParentWorkflow:
    """Runs one job as a child, the way distill and research do."""

    @workflow.run
    async def run(self, job: Job) -> JobOutcome:
        return await run_job_or_fail(job)


@workflow.defn(name="soft_parent", sandboxed=False)
class SoftParentWorkflow:
    """Runs one job as a child and keeps going whatever it ended with."""

    @workflow.run
    async def run(self, job: Job) -> JobOutcome:
        return await run_job_with_report(job)


async def test_a_job_runs_as_a_named_child_with_its_attributes() -> None:
    _submitting(PLAIN)
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        parent_id = f"p-{uuid.uuid4()}"
        async with running(
            env.client,
            queue,
            [ParentWorkflow, JobWorkflow],
            QUICK,
            fake_job,
        ):
            outcome = await env.client.execute_workflow(
                ParentWorkflow.run,
                Job(name="wiki/3", prompt="hi", workdir=".", model="m"),
                id=parent_id,
                task_queue=queue,
            )
            child = await env.client.get_workflow_handle(f"{parent_id}/wiki/3").describe()
    assert outcome.result is not None
    assert child.parent_id == parent_id and child.workflow_type == "job"
    shown = child.typed_search_attributes
    assert shown.get(search_attributes.NAME) == "wiki/3"
    assert shown.get(search_attributes.MODEL) == "m"
    assert shown.get(search_attributes.OUTCOME) == "done"


async def test_a_child_job_that_failed_for_good_raises_the_named_job_failed() -> None:
    _submitting()
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with running(
            env.client,
            queue,
            [ParentWorkflow, SoftParentWorkflow, JobWorkflow],
            QUICK,
            always_fails,
        ):
            job = Job(name="wiki/3", prompt="hi", workdir=".", model="m")
            soft = await env.client.execute_workflow(
                SoftParentWorkflow.run, job, id=f"s-{uuid.uuid4()}", task_queue=queue
            )
            with pytest.raises(WorkflowFailureError) as err:
                await env.client.execute_workflow(
                    ParentWorkflow.run, job, id=f"p-{uuid.uuid4()}", task_queue=queue
                )
    assert soft.result is None and soft.failure.startswith("Stalled")
    assert isinstance(err.value.cause, ApplicationError) and err.value.cause.type == "JobFailed"
    assert err.value.cause.message.startswith("wiki/3: Stalled")


@workflow.defn(name="structured_parent", sandboxed=False)
class StructuredParentWorkflow:
    """Runs one job asked for a structured output as a child, the way research does."""

    @workflow.run
    async def run(self, job: Job) -> dict[str, Any] | None:
        return (await run_job_with_structured_output(job, SCHEMA)).output


async def test_a_child_job_gives_its_output_or_raises_its_typed_error() -> None:
    _submitting(WITH_OUTPUT)
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with running(
            env.client, queue, [StructuredParentWorkflow, JobWorkflow], QUICK, fake_job
        ):
            job = Job(name="urls", prompt="fetch", workdir=".", model="m")
            output = await env.client.execute_workflow(
                StructuredParentWorkflow.run, job, id=f"p-{uuid.uuid4()}", task_queue=queue
            )
            with pytest.raises(WorkflowFailureError) as err:
                await env.client.execute_workflow(
                    StructuredParentWorkflow.run, job, id=f"p-{uuid.uuid4()}", task_queue=queue
                )
    assert output == {"urls": ["u"]}
    cause = err.value.cause
    assert isinstance(cause, ApplicationError) and cause.type == "StructuredOutputNotStated"
