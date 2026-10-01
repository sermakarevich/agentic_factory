import pytest
from factory_store.store import Store
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.failure import BadOutput
from agentic_factory.job.contract import JobResult
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.step.providers.client import Client
from temporal_agentic_factory.job import report as activity
from tests.fakes import FakeStore

RESULT = JobResult(session_id="s1", cost_usd=0.5)
REPORT = JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.DONE)
REQUEST = activity.ReportRequest(session_id="s1", result=RESULT, failure="")


@pytest.fixture
def db() -> FakeStore:
    return FakeStore()


def build_report(db: FakeStore) -> activity.ReportActivity:
    return activity.ReportActivity(db)  # type: ignore[arg-type]


async def test_the_app_builds_the_report_with_the_store_and_a_step_client(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    given: list[tuple[Store, str, JobResult | None, str, Client]] = []

    async def fake_build(
        store: Store, session_id: str, result: JobResult | None, failure: str, client: Client
    ) -> JobReport:
        given.append((store, session_id, result, failure, client))
        return REPORT

    monkeypatch.setattr(activity.reports, "build_report", fake_build)
    report = await ActivityEnvironment().run(build_report(db).build_report, REQUEST)

    assert report == REPORT
    ((store, session_id, result, failure, client),) = given
    assert store is db and (session_id, result, failure) == ("s1", RESULT, "")
    assert isinstance(client, Client)


async def test_report_failure_becomes_typed_error(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_build(
        store: Store, session_id: str, result: JobResult | None, failure: str, client: Client
    ) -> JobReport:
        raise BadOutput("not json")

    monkeypatch.setattr(activity.reports, "build_report", fake_build)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(build_report(db).build_report, REQUEST)
    assert err.value.type == "BadOutput"
