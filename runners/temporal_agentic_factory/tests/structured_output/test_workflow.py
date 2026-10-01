import uuid
from typing import Any

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.job.structured_output.prompt import INSTRUCTION
from temporal_agentic_factory.job import search_attributes
from temporal_agentic_factory.job.execute import TryResult
from temporal_agentic_factory.job.report import ReportRequest
from temporal_agentic_factory.structured_output.extract import StructuredOutputRequest
from temporal_agentic_factory.structured_output.workflow import (
    JobWithStructuredOutputWorkflow,
    StructuredOutputJob,
)

SCHEMA = {"type": "object", "properties": {"urls": {"type": "array", "items": {"type": "string"}}}}
prompts: list[str] = []
extractions: list[StructuredOutputRequest] = []


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    return "s1"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> TryResult:
    prompts.append(job.prompt)
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


@activity.defn(name="extract_structured_output")
async def fake_extract(request: StructuredOutputRequest) -> dict[str, Any]:
    extractions.append(request)
    return {"urls": ["u"]}


@activity.defn(name="extract_structured_output")
async def nothing_stated(request: StructuredOutputRequest) -> dict[str, Any]:
    raise ApplicationError(
        "the coder did not state: urls", type="StructuredOutputNotStated", non_retryable=True
    )


async def _environment() -> WorkflowEnvironment:
    env = await WorkflowEnvironment.start_time_skipping(data_converter=pydantic_data_converter)
    await search_attributes.add(env.client, "default", [key.name for key in search_attributes.KEYS])
    return env


async def _run(activities: list[Any]) -> Any:
    async with await _environment() as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[JobWithStructuredOutputWorkflow],
            activities=[fake_session, fake_report, fake_record, *activities],
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


async def test_the_job_is_asked_for_the_structured_output_and_the_result_carries_it() -> None:
    prompts.clear()
    extractions.clear()
    result = await _run([fake_job, fake_extract])
    assert result.structured_output == {"urls": ["u"]}
    assert result.outcome.session_id == "s1" and result.outcome.report is not None
    (prompt,) = prompts
    assert prompt.startswith("fetch\n\n" + INSTRUCTION) and "- urls (array of string)" in prompt
    assert extractions == [StructuredOutputRequest(session_id="s1", output_schema=SCHEMA)]


async def test_a_job_that_failed_for_good_fails_the_workflow() -> None:
    with pytest.raises(WorkflowFailureError) as err:
        await _run([failing_job, fake_extract])
    assert isinstance(err.value.cause, ApplicationError) and err.value.cause.type == "JobFailed"
    assert err.value.cause.message.startswith("urls: Stalled")


async def test_structured_output_not_stated_fails_the_workflow() -> None:
    with pytest.raises(WorkflowFailureError) as err:
        await _run([fake_job, nothing_stated])
    step_failure = err.value.cause.cause if err.value.cause else None
    assert (
        isinstance(step_failure, ApplicationError)
        and step_failure.type == "StructuredOutputNotStated"
    )
