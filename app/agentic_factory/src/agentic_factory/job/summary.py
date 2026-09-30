from pydantic import BaseModel, ConfigDict, Field

SUMMARY_KEY = "job_summary"


class JobSummary(BaseModel):
    """The coder's own account of the job, asked for by `summary_prompt.wrap_prompt`.
    A claim, not a verdict: the workflow checks it against the stats.
    `extra="forbid"` because the repair step sends this schema in strict mode."""

    model_config = ConfigDict(extra="forbid")
    task: str = Field(description="One sentence: what was asked.")
    plan: list[str] = Field(description="What the coder set out to do.")
    execution: list[str] = Field(description="What it actually did.")
    result: str = Field(description="One sentence: the state now.")
    success: bool
