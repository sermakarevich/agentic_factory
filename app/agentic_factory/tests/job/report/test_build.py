from datetime import UTC, datetime
from typing import Any

import pytest
from factory_store.store import StoredEvent, StoredSession

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import BadOutput
from agentic_factory.job.contract import JobResult
from agentic_factory.job.report import build
from agentic_factory.job.report.build import build_report
from agentic_factory.job.report.contract import JobReport, Verdict
from agentic_factory.step.providers.client import Client

RESULT = JobResult(session_id="s1", cost_usd=0.5)
REPORT = JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.DONE)


class FakeStore:
    def __init__(self, events: list[StoredEvent]) -> None:
        self.events = events
        self.calls: list[tuple[Any, ...]] = []

    async def load_session(self, session_id: str) -> StoredSession | None:
        return StoredSession(
            id=session_id,
            provider="p",
            model="m",
            workdir="/w",
            prompt="say ok",
            created_at=datetime.now(UTC),
        )

    async def load_events(self, session_id: str) -> list[StoredEvent]:
        return self.events

    async def save_conversation(self, session_id: str, text: str, events_count: int) -> None:
        self.calls.append(("save_conversation", session_id, text, events_count))

    async def save_report(
        self, session_id: str, result: dict[str, Any], summary: dict[str, Any], verdict: str
    ) -> None:
        self.calls.append(("save_report", session_id, result, summary, str(verdict)))


def stored(row_id: int, kind: EventKind, content: str, name: str = "") -> StoredEvent:
    at = datetime.now(UTC)
    payload = Event(kind=kind, at=at, content=content, name=name).model_dump(mode="json")
    return StoredEvent(
        id=row_id, session_id="s1", attempt=1, at=at, kind=kind.value, payload=payload
    )


@pytest.fixture
def db() -> FakeStore:
    return FakeStore([stored(1, EventKind.AI, "hello"), stored(2, EventKind.TOOL, "out", "bash")])


async def test_the_report_is_written_over_the_rendered_conversation(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []

    async def fake_report(
        conversation: str, result: JobResult | None, failure: str, client: Client
    ) -> JobReport:
        seen.append(conversation)
        assert result == RESULT and failure == ""
        return REPORT

    monkeypatch.setattr(build, "report", fake_report)
    written = await build_report(db, "s1", RESULT, "", client=None)  # type: ignore[arg-type]

    assert written == REPORT
    assert len(seen) == 1 and seen[0].startswith("user: say ok\n===== try 1 =====")
    assert db.calls == [
        ("save_conversation", "s1", seen[0], 2),
        (
            "save_report",
            "s1",
            RESULT.model_dump(mode="json"),
            REPORT.model_dump(mode="json"),
            "done",
        ),
    ]


async def test_a_failed_step_writes_the_conversation_but_no_report(
    db: FakeStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_report(
        conversation: str, result: JobResult | None, failure: str, client: Client
    ) -> JobReport:
        raise BadOutput("not json")

    monkeypatch.setattr(build, "report", fake_report)
    with pytest.raises(BadOutput):
        await build_report(db, "s1", None, "Stalled: quiet", client=None)  # type: ignore[arg-type]
    assert [call[0] for call in db.calls] == ["save_conversation"]
