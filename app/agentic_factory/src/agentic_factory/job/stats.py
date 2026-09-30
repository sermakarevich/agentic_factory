from pydantic import BaseModel, Field

from agentic_factory.event import Event, EventKind


class JobStats(BaseModel):
    """Counts over the events of one run: the cheapest evidence of what the
    coder did, used to sanity-check what it claims."""

    turns: int = Field(default=0, description="Model turns (ai events).")
    tool_calls: int = Field(default=0, description="Tool outputs seen.")
    tool_failures: int = Field(default=0, description="Of those, calls that failed.")

    def add(self, event: Event) -> None:
        match event.kind:
            case EventKind.AI:
                self.turns += 1
            case EventKind.TOOL:
                self.tool_calls += 1
                self.tool_failures += event.error
