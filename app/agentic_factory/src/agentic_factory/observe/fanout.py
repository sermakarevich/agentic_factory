from agentic_factory.event import Event, Observer


class Fanout:
    """One observer that forwards every event to several."""

    def __init__(self, *observers: Observer) -> None:
        self.observers = observers

    async def on_event(self, event: Event) -> None:
        for observer in self.observers:
            await observer.on_event(event)
