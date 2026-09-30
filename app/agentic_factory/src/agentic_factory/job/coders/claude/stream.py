from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LineType(StrEnum):
    SYSTEM = "system"
    ASSISTANT = "assistant"
    USER = "user"
    RATE_LIMIT = "rate_limit_event"
    RESULT = "result"


class SystemSubtype(StrEnum):
    """`subtype` of a system line. Others (hook chatter) are ignored."""

    INIT = "init"


class ResultSubtype(StrEnum):
    """`subtype` of the result line."""

    SUCCESS = "success"  # anything else (error_max_turns, error_during_execution) is an error


class BlockType(StrEnum):
    """`type` of a content block inside a message."""

    TEXT = "text"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"


class RateLimitStatus(StrEnum):
    """`rate_limit_info.status`."""

    ALLOWED = "allowed"
    ALLOWED_WARNING = "allowed_warning"
    REJECTED = "rejected"


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class Block(BaseModel):
    """One content block. Which fields are set depends on `type`."""

    type: str
    text: str = ""  # text
    id: str = ""  # tool_use
    name: str = ""  # tool_use
    input: dict[str, Any] = Field(default_factory=dict)  # tool_use
    tool_use_id: str = ""  # tool_result
    content: str | list["Block"] = ""  # tool_result: plain text or text blocks
    is_error: bool = False  # tool_result

    @property
    def result_text(self) -> str:
        if isinstance(self.content, str):
            return self.content
        return "".join(b.text for b in self.content if b.type == BlockType.TEXT)


class Message(BaseModel):
    id: str = ""  # assistant: one message can arrive as several lines sharing this id
    content: str | list[Block] = ""
    usage: Usage | None = None

    @property
    def blocks(self) -> list[Block]:
        if isinstance(self.content, str):
            return [Block(type=BlockType.TEXT, text=self.content)] if self.content else []
        return self.content


class RateLimitInfo(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    status: str = ""
    resets_at: float | None = Field(default=None, alias="resetsAt", description="Epoch seconds.")


class Line(BaseModel):
    """One JSON object of `claude -p --verbose --output-format stream-json`.

    Every line carries `session_id`. `system/init` opens the run (cwd, model).
    `assistant` is one model message: text and `tool_use` blocks plus its usage,
    with an ISO `timestamp`. `user` carries the `tool_result` blocks for those
    calls. `rate_limit_event` reports quota status. `result` closes the run with
    the totals, `total_cost_usd` and `is_error`.
    """

    type: str
    subtype: str = ""
    session_id: str = ""
    timestamp: str | None = Field(default=None, description="ISO 8601, on messages only.")
    message: Message = Field(default_factory=Message)  # assistant, user
    rate_limit_info: RateLimitInfo = Field(default_factory=RateLimitInfo)  # rate_limit_event
    usage: Usage = Field(default_factory=Usage)  # result: totals
    total_cost_usd: float = 0.0  # result
    is_error: bool = False  # result
    result: str = ""  # result: final text or error message

    @property
    def at(self) -> datetime | None:
        if self.timestamp is None:
            return None
        return datetime.fromisoformat(self.timestamp.replace("Z", "+00:00")).astimezone(UTC)
