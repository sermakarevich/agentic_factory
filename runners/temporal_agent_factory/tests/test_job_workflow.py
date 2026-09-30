import uuid

from temporalio import activity
from temporalio.contrib.pydantic import pydantic_data_converter
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from agent_factory.job.contract import Job, JobResult
from temporal_agent_factory.workflows.job import JobWorkflow

tries: list[int] = []
sessions: list[str] = []


@activity.defn(name="create_session")
async def fake_session(job: Job) -> str:
    return "s1"


@activity.defn(name="execute_job")
async def fake_job(job: Job) -> JobResult:
    """Fails once, then answers. Stands in for the real activity."""
    tries.append(activity.info().attempt)
    sessions.append(job.session_id)
    if activity.info().attempt == 1:
        raise ApplicationError("no output", type="Stalled")
    return JobResult(session_id=job.session_id, cost_usd=0.5)


async def test_job_workflow_retries_the_activity_and_returns_its_result() -> None:
    tries.clear()
    sessions.clear()
    async with await WorkflowEnvironment.start_time_skipping(
        data_converter=pydantic_data_converter
    ) as env:
        queue = f"test-{uuid.uuid4()}"
        async with Worker(
            env.client,
            task_queue=queue,
            workflows=[JobWorkflow],
            activities=[fake_session, fake_job],
        ):
            result = await env.client.execute_workflow(
                JobWorkflow.run,
                Job(prompt="hi", workdir=".", model="m"),
                id=f"j-{uuid.uuid4()}",
                task_queue=queue,
            )
    assert tries == [1, 2] and sessions == ["s1", "s1"]  # one session, made before try 1
    assert result.session_id == "s1" and result.cost_usd == 0.5
