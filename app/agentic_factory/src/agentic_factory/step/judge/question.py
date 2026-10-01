from typing import Annotated, Literal

from pydantic import BaseModel, Field


class Choice(BaseModel):
    """Pick one label out of named options."""

    kind: Literal["choice"] = "choice"
    question: str
    options: dict[str, str | None] = Field(
        min_length=2, description="Label to description; None leaves the label undescribed."
    )
    focus: str = Field(
        default="", description="What in the state to weigh; sent next to the question."
    )


class Score(BaseModel):
    """Place the state on an ordered scale; the score is the level's index."""

    kind: Literal["score"] = "score"
    question: str
    levels: list[str] = Field(min_length=2, description="Level descriptions, lowest first.")
    focus: str = ""


class Check(BaseModel):
    """A yes/no question answered as the probability of yes."""

    kind: Literal["check"] = "check"
    question: str
    yes: str = Field(default="", description="What a yes means; empty leaves it undescribed.")
    no: str = Field(default="", description="What a no means; empty leaves it undescribed.")
    focus: str = ""


Question = Annotated[Choice | Score | Check, Field(discriminator="kind")]
