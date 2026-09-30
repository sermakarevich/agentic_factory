from datetime import datetime
from typing import Any


class FakeStore:
    """Records every call; stands in for factory_store.store.Store."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

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
        self, session_id: str, attempt: int, outcome: str, failure: str = ""
    ) -> None:
        self.calls.append(("finish_try", session_id, attempt, str(outcome), failure))
