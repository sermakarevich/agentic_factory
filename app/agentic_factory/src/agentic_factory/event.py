from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from agentic_factory.tokens import Tokens


class EventKind(StrEnum):
    SESSION = "session"  # coder started, session id known
    AI = "ai"  # one model turn: text and/or tool calls, with its usage
    TOOL = "tool"  # one tool's output
    RATE_LIMIT = "rate_limit"  # provider quota signal
    FINISHED = "finished"  # coder said it is done; carries the totals
    USAGE = "usage"  # the try's totals read back from the coder, after a `finished` without them
    COMPACTION = "compaction"  # the engine asked the coder to compact its context
    UNKNOWN = "unknown"  # a line the harness could not translate; content is the text


class ToolCall(BaseModel):
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class Event(BaseModel):
    """Field names follow LangChain messages (content, tool_calls, tool_call_id,
    name) so an event converts to an AIMessage or ToolMessage in a few lines."""

    kind: EventKind
    at: datetime
    session_id: str = ""
    content: str = Field(
        default="", description="Model text on ai, tool output on tool, the line on unknown."
    )
    tool_calls: list[ToolCall] = Field(default_factory=list, description="On ai.")
    tool_call_id: str = Field(default="", description="On tool.")
    name: str = Field(default="", description="Tool name on tool.")
    error: bool = Field(default=False, description="On tool: the call failed.")
    usage: Tokens | None = Field(
        default=None, description="Tokens of the turn on ai, totals on finished."
    )
    cost_usd: float = Field(
        default=0.0, description="On finished; on ai too when the coder prices each turn."
    )
    resets_at: datetime | None = Field(default=None, description="On rate_limit.")
    raw: dict[str, Any] = Field(default_factory=dict, description="The original line, untouched.")
