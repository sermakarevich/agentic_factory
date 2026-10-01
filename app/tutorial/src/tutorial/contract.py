"""What the tutorial workflow passes around: the request that starts it, the
plan the designer states, what a reviewer and the finish job state, and the
outcome the workflow returns."""

import re
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from tutorial.settings.load import settings

NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class Format(StrEnum):
    """What a chapter is written as: a markdown page, a notebook, or both."""

    md = "md"
    ipynb = "ipynb"


def name_problem(name: str) -> str:
    """Why `name` is not a folder name (lowercase letters, digits, `_`, `-`); empty when it is."""
    if NAME_PATTERN.match(name):
        return ""
    return f"name must be lowercase letters, digits, '_' or '-', got {name!r}"


class Coder(BaseModel):
    """Who runs one role's jobs: the provider and its model."""

    provider: str
    model: str = Field(default="", description="Empty = the harness's default model.")


class TutorialRequest(BaseModel):
    """One topic to write up as a tutorial in the knowledge base."""

    topic: str = Field(description="What the tutorial teaches, in a sentence or a few words.")
    name: str = Field(default="", description="Folder name; empty = the one the designer picks.")
    formats: list[Format] = Field(
        default_factory=lambda: [Format(item) for item in settings.tutorial.formats],
        description="The chapter formats allowed; the designer picks per chapter.",
    )
    level: str = Field(
        default_factory=lambda: settings.tutorial.level, description="Who the reader is."
    )
    review_rounds: int = Field(
        default_factory=lambda: settings.tutorial.review_rounds,
        ge=0,
        description="Rewrite rounds a failing chapter gets before it is marked failed.",
    )
    designer: Coder = Field(
        default_factory=lambda: _coder(settings.designer.provider, settings.designer.model)
    )
    writer: Coder = Field(
        default_factory=lambda: _coder(settings.writer.provider, settings.writer.model)
    )
    reviewer: Coder = Field(
        default_factory=lambda: _coder(settings.reviewer.provider, settings.reviewer.model)
    )

    @field_validator("topic")
    @classmethod
    def topic_is_given(cls, topic: str) -> str:
        """No topic, no tutorial."""
        if not topic.strip():
            raise ValueError("topic must be non-empty")
        return topic

    @field_validator("name")
    @classmethod
    def name_is_a_folder(cls, name: str) -> str:
        """Empty, or one plain folder name."""
        problem = name_problem(name) if name else ""
        if problem:
            raise ValueError(problem)
        return name

    @field_validator("formats")
    @classmethod
    def formats_are_a_set(cls, formats: list[Format]) -> list[Format]:
        """At least one format, each named once."""
        if not formats:
            raise ValueError("formats must hold at least one of md, ipynb")
        if len(set(formats)) != len(formats):
            raise ValueError(f"formats named twice: {[item.value for item in formats]}")
        return formats

    @field_validator("level")
    @classmethod
    def level_is_known(cls, level: str) -> str:
        """One of the levels in settings."""
        if level not in settings.tutorial.levels:
            raise ValueError(f"level must be one of {settings.tutorial.levels}, got {level!r}")
        return level


def _coder(provider: str, model: str) -> Coder:
    return Coder(provider=provider, model=model)


class Named(BaseModel):
    """What the naming job states: the folder name it picked."""

    name: str


class Chapter(BaseModel):
    """One chapter as the designer planned it; paths are relative to the tutorial folder."""

    number: int = Field(ge=0, description="Its place in the reading order: 0 is `00_...`.")
    slug: str = Field(description="snake_case, the `<slug>` in `NN_<slug>.md`.")
    title: str
    spec_path: str = Field(description="`specs/NN_<slug>.md`: what the writer must produce.")
    formats: list[Format] = Field(description="What it is written as, of the allowed formats.")
    outputs: list[str] = Field(description="Every file the writer produces for it.")

    @property
    def label(self) -> str:
        """`01`: the chapter number as the file names and job names show it."""
        return f"{self.number:02d}"


class TutorialPlan(BaseModel):
    """What the designer states: the tutorial's title, whether it scaffolded
    `project/`, and its chapters in reading order."""

    title: str
    project: bool = Field(description="True when the designer scaffolded a shared project/.")
    chapters: list[Chapter]


class Review(BaseModel):
    """What a reviewer states about one chapter."""

    passed: bool = Field(description="True when the chapter meets its spec and runs.")
    problems: list[str] = Field(default=[], description="What must change; empty when passed.")


class Finished(BaseModel):
    """What the finish job states: the index it wrote and the small fixes it made."""

    index_path: str
    fixes: list[str] = []


class ChapterStatus(StrEnum):
    """Whether a chapter passed its review."""

    done = "done"
    failed = "failed"


class Spend(BaseModel):
    """What the jobs cost, summed from the job outcomes that carry it."""

    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    jobs: int = 0
    unknown: int = Field(default=0, description="Jobs that reported no usage, or a partial one.")

    def __add__(self, other: "Spend") -> "Spend":
        return Spend(
            cost_usd=self.cost_usd + other.cost_usd,
            input_tokens=self.input_tokens + other.input_tokens,
            output_tokens=self.output_tokens + other.output_tokens,
            jobs=self.jobs + other.jobs,
            unknown=self.unknown + other.unknown,
        )


class ChapterOutcome(BaseModel):
    """One chapter after its writer and reviewer jobs."""

    number: int
    slug: str
    title: str
    status: ChapterStatus
    rewrites: int = Field(default=0, description="Rewrite rounds it took.")
    problems: list[str] = Field(default=[], description="The last review's problems; empty done.")
    spend: Spend = Field(default_factory=Spend)


class TutorialOutcome(BaseModel):
    """What the workflow returns: where the tutorial landed and how each chapter ended."""

    folder: str
    index_path: str
    title: str
    chapters: list[ChapterOutcome]
    fixes: list[str] = Field(default=[], description="What the finish job fixed.")
    spend: Spend
