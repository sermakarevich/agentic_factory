from dataclasses import replace
from datetime import UTC, datetime

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.event import Event, EventKind, Observer
from agentic_factory.failure import Stalled
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.engine import Repair
from agentic_factory.job.harness import Harness
from temporal_agentic_factory.activities import job as activity
from tests.fakes import FakeStore

JOB = Job(prompt="p", workdir=".", provider="opencode", model="m", session_id="s1")


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    fake = FakeStore()
    monkeypatch.setattr(activity, "store", lambda: fake)
    return fake


async def test_second_try_continues_with_the_context_size_from_heartbeat(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[Job] = []

    async def fake_run(job: Job, observer: Observer, harness: Harness, repair: Repair) -> JobResult:
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


async def test_first_try_runs_the_job_as_given(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[Job] = []

    async def fake_run(job: Job, observer: Observer, harness: Harness, repair: Repair) -> JobResult:
        ran.append(job)
        return JobResult()

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    await ActivityEnvironment().run(activity.execute_job, JOB)
    assert ran[0] == JOB


async def test_failure_becomes_typed_application_error(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run(job: Job, observer: Observer, harness: Harness, repair: Repair) -> JobResult:
        raise Stalled("quiet")

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(activity.execute_job, JOB)
    assert err.value.type == "Stalled"


async def test_a_try_is_opened_closed_and_journaled(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run(job: Job, observer: Observer, harness: Harness, repair: Repair) -> JobResult:
        await observer.on_event(Event(kind=EventKind.AI, at=datetime.now(UTC), content="x"))
        return JobResult()

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    env = ActivityEnvironment()
    env.info = replace(env.info, attempt=2)

    await env.run(activity.execute_job, JOB)

    assert db.calls == [
        ("start_try", "s1", 2),
        ("append_event", "s1", 2, "ai"),
        ("finish_try", "s1", 2, "done", ""),
    ]


async def test_a_failed_try_is_closed_as_failed(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run(job: Job, observer: Observer, harness: Harness, repair: Repair) -> JobResult:
        raise Stalled("quiet")

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    with pytest.raises(ApplicationError):
        await ActivityEnvironment().run(activity.execute_job, JOB)

    assert db.calls[-1] == ("finish_try", "s1", 1, "failed", "quiet")
