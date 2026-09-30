from agentic_factory.event import Event


class Callback:
    """Whoever listens to a run hears every event as it happens. A base whose
    method does nothing; a callback overrides it. This is all the step engine
    tells; the job engine's `JobCallback` adds the start and the end. A step
    run inside a job (summary repair, the report) gets a plain `Callback()`:
    its events stay out of the job's stream, where a heartbeat callback would
    read the step's tokens as the coder's context."""

    async def on_event(self, event: Event) -> None:
        return None
