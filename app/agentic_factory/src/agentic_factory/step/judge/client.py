from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from agentic_factory.step.judge.answer import Answer
from agentic_factory.step.judge.contract import Judgment
from agentic_factory.tokens import Tokens


class JudgeReply(BaseModel):
    """What a judge sent back: the answers by name, and what it billed."""

    answers: dict[str, Answer]
    tokens: Tokens = Field(default_factory=Tokens)
    cost_usd: float = 0.0


class JudgeClient(ABC):
    """One subclass per judge provider: how to send a judgment over the wire
    and read the reply. Raises a `JobFailed` subclass when there is no answer."""

    default_model: ClassVar[str] = ""

    @classmethod
    @abstractmethod
    def from_env(cls) -> "JudgeClient":
        """Build from environment variables (keys, URLs)."""

    @abstractmethod
    async def answer(self, judgment: Judgment) -> JudgeReply:
        """`judgment.model` is already set; the engine fills the default."""
