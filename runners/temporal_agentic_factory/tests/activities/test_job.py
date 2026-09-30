from dataclasses import replace

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.callbacks.fanout import Fanout
from agentic_factory.callbacks.journal import JournalCallback
from agentic_factory.callbacks.log import LogCallback
from agentic_factory.failure import Stalled
from agentic_factory.job.callback import JobCallback
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.engine import Repair
from temporal_agentic_factory.activities import job as activity
from temporal_agentic_factory.activities.heartbeat import HeartbeatCallback
from tests.fakes import FakeStore

JOB = Job(prompt="p", workdir=".", provider="opencode", model="m", session_id="s1")


@pytest.fixture
def db() -> FakeStore:
    return FakeStore()


def execute_job(db: FakeStore) -> activity.JobActivity:
    return activity.JobActivity(db)  # type: ignore[arg-type]


async def test_second_try_continues_with_the_context_size_from_heartbeat(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[Job] = []

    async def fake_run(
        job: Job, callback: JobCallback, harness: Harness, repair: Repair
    ) -> JobResult:
        ran.append(job)
        return JobResult(session_id=job.session_id)

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    env = ActivityEnvironment()
    details = [{"context_tokens": 120_000}]
    env.info = replace(env.info, attempt=2, heartbeat_details=details)

    result = await env.run(execute_job(db).execute_job, JOB)

    assert ran[0].session_id == "s1" and ran[0].session_tokens == 120_000
    assert ran[0].prompt.startswith("Try 2:")
    assert result.session_id == "s1"


async def test_first_try_runs_the_job_as_given(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    ran: list[Job] = []

    async def fake_run(
        job: Job, callback: JobCallback, harness: Harness, repair: Repair
    ) -> JobResult:
        ran.append(job)
        return JobResult()

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    await ActivityEnvironment().run(execute_job(db).execute_job, JOB)
    assert ran[0] == JOB


async def test_failure_becomes_typed_application_error(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_run(
        job: Job, callback: JobCallback, harness: Harness, repair: Repair
    ) -> JobResult:
        raise Stalled("quiet")

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(execute_job(db).execute_job, JOB)
    assert err.value.type == "Stalled"


async def test_the_engine_gets_heartbeat_log_and_journal_for_this_try(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[JobCallback] = []

    async def fake_run(
        job: Job, callback: JobCallback, harness: Harness, repair: Repair
    ) -> JobResult:
        given.append(callback)
        return JobResult()

    monkeypatch.setattr(activity.jobs, "run", fake_run)
    env = ActivityEnvironment()
    env.info = replace(env.info, attempt=2)

    await env.run(execute_job(db).execute_job, JOB)

    (fanout,) = given
    assert isinstance(fanout, Fanout)
    heartbeat, log, journal = fanout.callbacks
    assert isinstance(heartbeat, HeartbeatCallback) and isinstance(log, LogCallback)
    assert isinstance(journal, JournalCallback)
    assert journal.store is db and (journal.session_id, journal.attempt) == ("s1", 2)
    assert db.calls == []  # the journal writes when the engine calls it, not here
