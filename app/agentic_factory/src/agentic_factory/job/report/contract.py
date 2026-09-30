from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class Verdict(StrEnum):
    DONE = "done"  # everything asked for was done and checked
    PARTIAL = "partial"  # some of it
    FAILED = "failed"  # nothing useful, or the run broke
    UNKNOWN = "unknown"  # the conversation does not say


class JobReport(BaseModel):
    """What a model concluded from the whole conversation. Independent of the
    coder's own summary, which is a claim. `extra="forbid"`, no defaults: the
    schema goes to the model in strict mode."""

    model_config = ConfigDict(extra="forbid")
    task: str = Field(description="One sentence: what was asked.")
    done: list[str] = Field(
        description="What was done, with the evidence seen (files, commands, test results)."
    )
    not_done: list[str] = Field(description="What was asked but not done, or not verified.")
    problems: list[str] = Field(description="Errors, retries, rate limits, wrong turns.")
    verdict: Verdict
