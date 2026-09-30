from dataclasses import replace

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agent_factory.event import Observer
from agent_factory.failure import Stalled
from agent_factory.job.contract import Job, JobResult
from temporal_agent_factory.activities import job as activity

JOB = Job(prompt="p", workdir=".", provider="opencode", model="m", session_id="s1")


async def test_second_try_continues_with_the_context_size_from_heartbeat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ran: list[Job] = []

    async def fake_run(job: Job, observer: Observer) -> JobResult:
        ran.append(job)
        return JobResult(session_id=job.session_id)

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    env = ActivityEnvironment()
    details = [{"context_tokens": 120_000}]
    env.info = replace(env.info, attempt=2, heartbeat_details=details)

    result = await env.run(activity.execute_job, JOB)

    assert ran[0].session_id == "s1" and ran[0].session_tokens == 120_000
    assert ran[0].prompt.startswith("Try 2:")
    assert result.session_id == "s1"


async def test_first_try_runs_the_job_as_given(monkeypatch: pytest.MonkeyPatch) -> None:
    ran: list[Job] = []

    async def fake_run(job: Job, observer: Observer) -> JobResult:
        ran.append(job)
        return JobResult()

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    await ActivityEnvironment().run(activity.execute_job, JOB)
    assert ran[0] == JOB


async def test_failure_becomes_typed_application_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_run(job: Job, observer: Observer) -> JobResult:
        raise Stalled("quiet")

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(activity.execute_job, JOB)
    assert err.value.type == "Stalled"
