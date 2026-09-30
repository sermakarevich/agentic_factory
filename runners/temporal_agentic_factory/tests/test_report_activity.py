from datetime import UTC, datetime

import pytest
from factory_store.store import StoredEvent
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import BadOutput
from agentic_factory.job.contract import JobResult
from agentic_factory.job.report import JobReport, Verdict
from agentic_factory.step.client import Client
from temporal_agentic_factory.activities import report as activity
from tests.fakes import FakeStore

RESULT = JobResult(session_id="s1", cost_usd=0.5)
REPORT = JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.DONE)


def _stored(
    row_id: int, attempt: int, kind: EventKind, content: str, name: str = ""
) -> StoredEvent:
    at = datetime.now(UTC)
    payload = Event(kind=kind, at=at, content=content, name=name).model_dump(mode="json")
    return StoredEvent(
        id=row_id, session_id="s1", attempt=attempt, at=at, kind=kind.value, payload=payload
    )


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> FakeStore:
    fake = FakeStore()
    fake.events = [
        _stored(1, 1, EventKind.AI, "hello"),
        _stored(2, 1, EventKind.TOOL, "out", name="bash"),
    ]
    monkeypatch.setattr(activity, "store", lambda: fake)
    return fake


async def test_report_is_built_over_the_rendered_conversation(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def fake_report(
        conversation: str,
        result: JobResult | None,
        failure: str = "",
        client: Client | None = None,
    ) -> JobReport:
        seen.append(conversation)
        assert result is not None and result.session_id == "s1"
        assert failure == ""
        return REPORT

    monkeypatch.setattr(activity.reports, "report", fake_report)
    report = await ActivityEnvironment().run(
        activity.build_report, activity.ReportRequest(session_id="s1", result=RESULT)
    )

    assert report == REPORT
    assert len(seen) == 1 and "===== try 1 =====" in seen[0]
    assert ("save_conversation", "s1", seen[0], 2) in db.calls
    assert (
        "save_report",
        "s1",
        RESULT.model_dump(mode="json"),
        REPORT.model_dump(mode="json"),
        "done",
    ) in db.calls


async def test_report_failure_becomes_typed_error(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_report(
        conversation: str,
        result: JobResult | None,
        failure: str = "",
        client: Client | None = None,
    ) -> JobReport:
        raise BadOutput("not json")

    monkeypatch.setattr(activity.reports, "report", fake_report)
    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(
            activity.build_report, activity.ReportRequest(session_id="s1", result=RESULT)
        )
    assert err.value.type == "BadOutput"
