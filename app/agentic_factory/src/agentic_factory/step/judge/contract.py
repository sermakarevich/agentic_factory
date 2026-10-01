from typing import Any, TypeVar

from pydantic import BaseModel, Field

from agentic_factory.failure import BadOutput
from agentic_factory.settings.load import settings
from agentic_factory.step.judge.answer import Answer, CheckAnswer, ChoiceAnswer, ScoreAnswer
from agentic_factory.step.judge.question import Question
from agentic_factory.tokens import Tokens

A = TypeVar("A", ChoiceAnswer, ScoreAnswer, CheckAnswer)

State = str | dict[str, Any] | list[Any]


class Judgment(BaseModel):
    """One state and the typed questions a judge model answers about it.
    No prompt, no schema, no free text back: every answer is a label, a
    level or a probability, so a workflow can branch on it."""

    provider: str = Field(
        default_factory=lambda: settings.step.judge.provider, description="Which judge answers."
    )
    state: State = Field(description="The text, object or list under judgment.")
    questions: dict[str, Question] = Field(min_length=1, description="Named, answered by name.")
    model: str = Field(default="", description="Empty = the judge's default model.")
    timeout_sec: int = Field(default_factory=lambda: settings.step.judge.timeout_sec)


class JudgmentResult(BaseModel):
    """The answers by question name, with what they cost."""

    answers: dict[str, Answer]
    model: str
    tokens: Tokens = Field(default_factory=Tokens)
    cost_usd: float = 0.0
    duration_sec: float = 0.0

    def choice(self, name: str) -> ChoiceAnswer:
        return self._answer_of_kind(name, ChoiceAnswer)

    def score(self, name: str) -> ScoreAnswer:
        return self._answer_of_kind(name, ScoreAnswer)

    def check(self, name: str) -> CheckAnswer:
        return self._answer_of_kind(name, CheckAnswer)

    def _answer_of_kind(self, name: str, cls: type[A]) -> A:
        """The named answer as the kind the caller asked; a mismatch is a bad output."""
        answer = self.answers.get(name)
        if answer is None:
            raise BadOutput(f"no answer named {name!r}; got {sorted(self.answers)}")
        if not isinstance(answer, cls):
            raise BadOutput(f"answer {name!r} is a {answer.kind}, not a {cls.__name__}")
        return answer
