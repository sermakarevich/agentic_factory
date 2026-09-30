from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LineType(StrEnum):
    STEP_START = "step_start"
    TEXT = "text"
    TOOL_USE = "tool_use"
    STEP_FINISH = "step_finish"
    ERROR = "error"


class Reason(StrEnum):
    """`part.reason` of a step_finish line."""

    TOOL_CALLS = "tool-calls"
    STOP = "stop"
    LENGTH = "length"


class ToolStatus(StrEnum):
    """`part.state.status` of a tool_use line."""

    COMPLETED = "completed"
    ERROR = "error"


class Cache(BaseModel):
    read: int = 0
    write: int = 0


class StepTokens(BaseModel):
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cache: Cache = Field(default_factory=Cache)


class ToolState(BaseModel):
    status: str = ""
    input: dict[str, Any] = Field(default_factory=dict)
    output: str = ""
    error: Any = None


class Part(BaseModel):
    """The `part` of a line. Which fields are set depends on the line type."""

    id: str = ""
    tool: str = ""  # tool_use
    text: str = ""  # text
    state: ToolState = Field(default_factory=ToolState)  # tool_use
    reason: str = ""  # step_finish
    cost: float = 0.0  # step_finish
    tokens: StepTokens = Field(default_factory=StepTokens)  # step_finish


class Line(BaseModel):
    """One JSON object of `opencode run --format json`.

    Every line carries `sessionID` and a millisecond `timestamp`. `step_start`
    opens a model turn, `text` and `tool_use` are its parts (a tool_use line
    already holds the tool's output), `step_finish` closes it with the turn's
    tokens and a reason: `tool-calls`, `stop` or `length`.
    """

    model_config = ConfigDict(populate_by_name=True)

    type: str
    session_id: str = Field(default="", alias="sessionID")
    timestamp: float | None = Field(default=None, description="Epoch milliseconds.")
    part: Part = Field(default_factory=Part)
    error: Any = None

    @property
    def at(self) -> datetime:
        if self.timestamp is None:
            return datetime.now(tz=UTC)
        return datetime.fromtimestamp(self.timestamp / 1000, tz=UTC)
