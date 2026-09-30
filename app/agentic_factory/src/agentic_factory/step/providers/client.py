from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel, Field

from agentic_factory.step.contract import Step
from agentic_factory.tokens import Tokens


class Answer(BaseModel):
    """What a provider sent back, before the engine reads it as JSON."""

    text: str
    tokens: Tokens = Field(default_factory=Tokens)


class Client(ABC):
    """One subclass per provider: how to send a step over the wire and read
    the reply. Raises a `JobFailed` subclass when there is no usable answer."""

    default_model: ClassVar[str] = ""

    @classmethod
    @abstractmethod
    def from_env(cls) -> "Client":
        """Build from environment variables (keys, URLs)."""

    @abstractmethod
    async def complete(self, step: Step) -> Answer:
        """`step.model` is already set; the engine fills the default."""
