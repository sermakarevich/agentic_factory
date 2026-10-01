from agentic_factory.event import Event


class Callback:
    """Whoever listens to a run hears every event as it happens. A base whose
    method does nothing; a callback overrides it. This is all the judge
    engine tells; the job engine's `JobCallback` adds the start and the end."""

    async def on_event(self, event: Event) -> None:
        return None
