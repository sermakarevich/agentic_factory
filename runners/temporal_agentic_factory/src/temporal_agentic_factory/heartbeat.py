from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from temporalio import activity

from agentic_factory.event import Event, EventKind
from agentic_factory.job.engine import context_of


class Heartbeat(BaseModel):
    """What one try tells the server as it runs: that it is alive, and how big
    the session's context is. The next try reads the last one back from
    `activity.info().heartbeat_details`. The session itself is in the job."""

    at: datetime | None = None
    events: int = 0
    context_tokens: int = Field(default=0, description="Context size of the last model turn.")

    @classmethod
    def last(cls, details: Sequence[Any]) -> "Heartbeat | None":
        """The previous try's last heartbeat, or None on a first try. Details
        come back without a type hint, so as a plain dict."""
        if not details:
            return None
        first = details[0]
        return first if isinstance(first, cls) else cls.model_validate(first)


class HeartbeatObserver:
    """Heartbeats Temporal on every event. The SDK throttles the actual sends."""

    def __init__(self) -> None:
        self.state = Heartbeat()

    async def on_event(self, event: Event) -> None:
        context = self.state.context_tokens
        if event.kind == EventKind.AI:
            context = context_of(event) or context
        self.state = Heartbeat(at=event.at, events=self.state.events + 1, context_tokens=context)
        activity.heartbeat(self.state)
