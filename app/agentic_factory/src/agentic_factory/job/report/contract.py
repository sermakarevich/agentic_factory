from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Verdict(StrEnum):
    DONE = "done"  # everything asked for was done and checked
    PARTIAL = "partial"  # some of it
    FAILED = "failed"  # nothing useful, or the run broke
    UNKNOWN = "unknown"  # no report arrived; recorded by the workflow, never sent by the coder


class JobReport(BaseModel):
    """What the coder says it did, submitted at the end of every job with
    `af output submit`. The field descriptions are what the coder reads.
    `extra="forbid"`, no defaults: every field is required in the schema."""

    model_config = ConfigDict(extra="forbid")
    task: str = Field(description="One sentence: what you were asked to do.")
    done: list[str] = Field(
        description="What you did, one item each, every item naming its evidence: a file you "
        "wrote, a command you ran with what it printed, or a test result. Empty when nothing."
    )
    not_done: list[str] = Field(
        description="What you were asked but did not do, or did but could not verify. Empty "
        "when nothing."
    )
    problems: list[str] = Field(
        description="What went wrong on the way: errors, retries, rate limits, wrong turns. "
        "Empty when nothing."
    )
    verdict: Literal[Verdict.DONE, Verdict.PARTIAL, Verdict.FAILED] = Field(
        description="done: everything asked was done and checked; partial: some of it; "
        "failed: nothing useful."
    )
