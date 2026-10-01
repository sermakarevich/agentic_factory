from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field


class ChoiceAnswer(BaseModel):
    kind: Literal["choice"] = "choice"
    choice: str
    confidence: float
    probabilities: dict[str, float] = Field(description="One entry per option.")


class ScoreAnswer(BaseModel):
    kind: Literal["score"] = "score"
    score: float
    confidence: float
    probabilities: dict[int, float] = Field(description="One entry per level index.")
    legend: dict[int, Any] = Field(description="Level index to its description.")


class CheckAnswer(BaseModel):
    kind: Literal["check"] = "check"
    yes: float = Field(description="Probability of yes, 0 to 1.")


Answer = Annotated[ChoiceAnswer | ScoreAnswer | CheckAnswer, Field(discriminator="kind")]
