from typing import Any, TypeVar

from pydantic import BaseModel, Field, ValidationError

from agentic_factory.failure import BadOutput
from agentic_factory.settings.load import settings
from agentic_factory.step.reasoning import Reasoning
from agentic_factory.tokens import Tokens

T = TypeVar("T", bound=BaseModel)


class Step(BaseModel):
    """One structured-output request to a model. No tools, no workdir, no session."""

    provider: str = Field(
        default_factory=lambda: settings.step.provider, description="Which client sends it."
    )
    prompt: str
    output_schema: dict[str, Any] = Field(
        description="JSON schema the answer must match; usually SomeModel.model_json_schema(). "
        "Sent in strict mode: every property required and `additionalProperties: false`, "
        "which a pydantic model gives with `extra='forbid'` and no defaults."
    )
    system_prompt: str = Field(default="", description="Standing instructions: role and rules.")
    model: str = Field(default="", description="Empty = the client's default model.")
    reasoning: Reasoning = Field(
        default_factory=lambda: Reasoning(settings.step.reasoning),
        description="Tokens are covered by the plan; only time is spent.",
    )
    max_tokens: int = Field(
        default_factory=lambda: settings.step.max_tokens, description="Answer plus reasoning."
    )
    timeout_sec: int = Field(default_factory=lambda: settings.step.timeout_sec)


class StepResult(BaseModel):
    """The answer as a JSON object, with what it cost."""

    output: dict[str, Any]
    model: str
    tokens: Tokens = Field(default_factory=Tokens)
    duration_sec: float = 0.0

    def parse(self, cls: type[T]) -> T:
        """The output as the model the schema came from."""
        try:
            return cls.model_validate(self.output)
        except ValidationError as error:
            raise BadOutput(f"answer does not match {cls.__name__}: {error}") from None
