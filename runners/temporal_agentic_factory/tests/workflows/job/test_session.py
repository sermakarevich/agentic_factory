import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.failure import CoderCrashed
from agentic_factory.job.coders.catalog import harness_for
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job
from temporal_agentic_factory.workflows.job import session as activity
from tests.fakes import FakeStore

JOB = Job(prompt="p", workdir=".", provider="opencode", model="m")


@pytest.fixture
def db() -> FakeStore:
    return FakeStore()


def create_session(db: FakeStore) -> activity.SessionActivity:
    return activity.SessionActivity(db)  # type: ignore[arg-type]


async def test_returns_the_session_the_app_made(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(job: Job, harness: Harness) -> str:
        return "ses_new"

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    made = create_session(db)
    assert await ActivityEnvironment().run(made.create_session, JOB) == "ses_new"
    assert db.calls == [
        ("start_session", "ses_new", JOB.provider, JOB.model, JOB.workdir, JOB.prompt)
    ]


async def test_session_row_carries_the_default_model_when_none_is_given(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(job: Job, harness: Harness) -> str:
        return "ses_new"

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    unnamed = JOB.model_copy(update={"model": ""})
    await ActivityEnvironment().run(create_session(db).create_session, unnamed)
    assert db.calls[0][3] == harness_for(JOB.provider).default_model


async def test_failure_becomes_typed_application_error(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_create(job: Job, harness: Harness) -> str:
        raise CoderCrashed(1, "no opencode")

    monkeypatch.setattr(activity.sessions, "create_session", fake_create)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(create_session(db).create_session, JOB)
    assert err.value.type == "CoderCrashed"
