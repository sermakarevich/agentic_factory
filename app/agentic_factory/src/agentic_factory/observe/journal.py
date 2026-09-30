from factory_store.store import Store

from agentic_factory.event import Event


class JournalObserver:
    """Writes every event of one try to the store as it happens. The session
    and try are given, not read from the event: the first events of a run
    carry no session id yet."""

    def __init__(self, store: Store, session_id: str, attempt: int) -> None:
        self.store = store
        self.session_id = session_id
        self.attempt = attempt
        self.written = 0

    async def on_event(self, event: Event) -> None:
        await self.store.append_event(
            self.session_id, self.attempt, event.at, event.kind, event.model_dump(mode="json")
        )
        self.written += 1
