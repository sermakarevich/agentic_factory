from datetime import UTC, datetime
from typing import Any

import pytest
from factory_store.store import StoredEvent, StoredSession

from agentic_factory.event import Event, EventKind
from agentic_factory.failure import StructuredOutputNotStated
from agentic_factory.job.structured_output import extract as module
from agentic_factory.job.structured_output.contract import Extraction, Schema
from agentic_factory.job.structured_output.extract import extract_structured_output, last_message
from agentic_factory.step.providers.client import Client

SCHEMA: Schema = {"type": "object", "properties": {"urls": {"type": "array"}}}
FOUND = Extraction(structured_output={"urls": ["u"]}, missing=[])
NOT_FOUND = Extraction(structured_output=None, missing=["urls"])


class FakeStore:
    def __init__(self, events: list[StoredEvent]) -> None:
        self.events = events
        self.saved: list[tuple[str, Schema, dict[str, Any], str]] = []

    async def save_structured_output(
        self, session_id: str, schema: Schema, structured_output: dict[str, Any], source: str
    ) -> None:
        self.saved.append((session_id, schema, structured_output, str(source)))

    async def load_session(self, session_id: str) -> StoredSession | None:
        return StoredSession(
            id=session_id,
            provider="p",
            model="m",
            workdir="/w",
            prompt="fetch",
            created_at=datetime.now(UTC),
        )

    async def load_events(self, session_id: str) -> list[StoredEvent]:
        return self.events


def stored(row_id: int, attempt: int, kind: EventKind, content: str) -> StoredEvent:
    at = datetime.now(UTC)
    payload = Event(kind=kind, at=at, content=content).model_dump(mode="json")
    return StoredEvent(
        id=row_id, session_id="s1", attempt=attempt, at=at, kind=kind.value, payload=payload
    )


ROWS = [
    stored(1, 1, EventKind.AI, "urls: [a]"),
    stored(2, 2, EventKind.AI, "looking"),
    stored(3, 2, EventKind.TOOL, "out"),
    stored(4, 2, EventKind.AI, "urls: [u]"),
    stored(5, 2, EventKind.AI, ""),
    stored(6, 2, EventKind.FINISHED, ""),
]


class Scripted:
    """Stands in for the step: one answer per call, in order; records the texts."""

    def __init__(self, *answers: Extraction) -> None:
        self.answers = list(answers)
        self.texts: list[str] = []

    async def __call__(self, text: str, schema: Schema, client: Client) -> Extraction:
        self.texts.append(text)
        assert schema == SCHEMA
        return self.answers.pop(0)


def test_last_message_is_the_last_ai_event_with_text() -> None:
    assert last_message(ROWS) == "urls: [u]"
    assert last_message(ROWS[2:3]) == ""


async def test_the_last_message_is_enough_when_it_states_the_structured_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = Scripted(FOUND)
    monkeypatch.setattr(module, "extract", step)
    db = FakeStore(ROWS)
    structured_output = await extract_structured_output(db, "s1", SCHEMA, client=None)  # type: ignore[arg-type]
    assert structured_output == {"urls": ["u"]}
    assert step.texts == ["urls: [u]"]
    assert db.saved == [("s1", SCHEMA, {"urls": ["u"]}, "last_message")]


async def test_the_conversation_is_read_when_the_last_message_does_not_state_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = Scripted(NOT_FOUND, FOUND)
    monkeypatch.setattr(module, "extract", step)
    db = FakeStore(ROWS)
    structured_output = await extract_structured_output(db, "s1", SCHEMA, client=None)  # type: ignore[arg-type]
    assert structured_output == {"urls": ["u"]}
    assert db.saved == [("s1", SCHEMA, {"urls": ["u"]}, "conversation")]
    assert len(step.texts) == 2
    assert step.texts[1].startswith("user: fetch\n===== try 1 =====\nassistant: urls: [a]")
    assert "===== try 2 =====" in step.texts[1]


async def test_a_job_with_no_message_goes_straight_to_the_conversation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step = Scripted(FOUND)
    monkeypatch.setattr(module, "extract", step)
    rows = [stored(1, 1, EventKind.TOOL, "out")]
    await extract_structured_output(FakeStore(rows), "s1", SCHEMA, client=None)  # type: ignore[arg-type]
    assert step.texts == ["user: fetch\n===== try 1 =====\ntool : out"]


async def test_not_stated_anywhere_fails_and_names_the_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(module, "extract", Scripted(NOT_FOUND, NOT_FOUND))
    db = FakeStore(ROWS)
    with pytest.raises(StructuredOutputNotStated, match="did not state: urls"):
        await extract_structured_output(db, "s1", SCHEMA, client=None)  # type: ignore[arg-type]
    assert not StructuredOutputNotStated.retryable
    assert db.saved == []
