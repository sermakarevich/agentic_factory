from pydantic import BaseModel, Field

from agentic_factory.event import Event, ToolCall


class Turn(BaseModel):
    """One model turn as it is being collected: text, the calls the model made,
    and the tool events for their outputs. Emitted when `step_finish` arrives."""

    text: list[str] = Field(default_factory=list)
    calls: list[ToolCall] = Field(default_factory=list)
    tools: list[Event] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.text and not self.calls

    @property
    def is_final_answer(self) -> bool:
        """Text and no tool calls: the turn a run ends on."""
        return bool(self.text) and not self.calls
