from datetime import datetime
from typing import Any

from factory_store.store import JobRecord, StoredEvent, StoredTry, Totals


class FakeStore:
    """Records every call; stands in for factory_store.store.Store."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.events: list[StoredEvent] = []
        self.tries: list[StoredTry] = []

    async def start_session(
        self, session_id: str, provider: str, model: str, workdir: str, prompt: str
    ) -> None:
        self.calls.append(("start_session", session_id, provider, model, workdir, prompt))

    async def start_try(self, session_id: str, attempt: int) -> None:
        self.calls.append(("start_try", session_id, attempt))

    async def append_event(
        self, session_id: str, attempt: int, at: datetime, kind: str, payload: dict[str, Any]
    ) -> int:
        self.calls.append(("append_event", session_id, attempt, kind))
        return len(self.calls)

    async def finish_try(
        self,
        session_id: str,
        attempt: int,
        outcome: str,
        failure: str = "",
        totals: Totals | None = None,
        result: dict[str, Any] | None = None,
    ) -> None:
        self.calls.append(("finish_try", session_id, attempt, str(outcome), failure))

    async def load_tries(self, session_id: str) -> list[StoredTry]:
        self.calls.append(("load_tries", session_id))
        return self.tries

    async def save_job(self, session_id: str, job: JobRecord) -> None:
        self.calls.append(("save_job", session_id, job))

    async def load_events(self, session_id: str) -> list[StoredEvent]:
        self.calls.append(("load_events", session_id))
        return self.events

    async def save_conversation(self, session_id: str, text: str, events_count: int) -> None:
        self.calls.append(("save_conversation", session_id, text, events_count))

    async def save_report(
        self, session_id: str, result: dict[str, Any], summary: dict[str, Any], verdict: str
    ) -> None:
        self.calls.append(("save_report", session_id, result, summary, str(verdict)))
