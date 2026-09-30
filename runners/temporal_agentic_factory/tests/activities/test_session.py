import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.failure import CoderCrashed
from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from temporal_agentic_factory.activities import session as activity
from tests.fakes import FakeStore

JOB = Job(prompt="p", workdir=".", provider="opencode", model="m")


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    fake = FakeStore()
    monkeypatch.setattr(activity, "store", lambda: fake)
    return fake


async def test_returns_the_session_the_app_made(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(job: Job, harness: Harness | None = None) -> str:
        return "ses_new"

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    assert await ActivityEnvironment().run(activity.create_session, JOB) == "ses_new"
    assert db.calls == [
        ("start_session", "ses_new", JOB.provider, JOB.model, JOB.workdir, JOB.prompt)
    ]


async def test_session_row_carries_the_default_model_when_none_is_given(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(job: Job, harness: Harness | None = None) -> str:
        return "ses_new"

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    await ActivityEnvironment().run(activity.create_session, JOB.model_copy(update={"model": ""}))
    assert db.calls[0][3] == harness_for(JOB.provider).default_model


async def test_failure_becomes_typed_application_error(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(job: Job, harness: Harness | None = None) -> str:
        raise CoderCrashed(1, "no opencode")

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(activity.create_session, JOB)
    assert err.value.type == "CoderCrashed"
