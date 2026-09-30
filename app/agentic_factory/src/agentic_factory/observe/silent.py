from agentic_factory.event import Event


class Silent:
    """The repair step's events stay out of the job's stream: a heartbeat
    observer would read the step's tokens as the coder's context."""

    async def on_event(self, event: Event) -> None:
        return None
