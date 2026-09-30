import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agent_factory.failure import CoderCrashed
from agent_factory.job.contract import Job
from agent_factory.job.harness import Harness
from temporal_agent_factory.activities import session as activity

JOB = Job(prompt="p", workdir=".", provider="opencode", model="m")


async def test_returns_the_session_the_app_made(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create(job: Job, harness: Harness | None = None) -> str:
        return "ses_new"

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    assert await ActivityEnvironment().run(activity.create_session, JOB) == "ses_new"


async def test_failure_becomes_typed_application_error(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create(job: Job, harness: Harness | None = None) -> str:
        raise CoderCrashed(1, "no opencode")

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(activity.create_session, JOB)
    assert err.value.type == "CoderCrashed"
