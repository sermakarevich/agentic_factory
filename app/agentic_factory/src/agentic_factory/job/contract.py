from pydantic import BaseModel, Field

from agentic_factory.job.stats import JobStats
from agentic_factory.job.summary.contract import JobSummary
from agentic_factory.settings.load import settings
from agentic_factory.tokens import Tokens


class Job(BaseModel):
    """What to run. Built by a job definition, sent to the activity."""

    provider: str = Field(
        default_factory=lambda: settings.job.provider,
        description="Which harness runs it: claude | opencode.",
    )
    model: str = Field(default="", description="Empty = the harness's default model.")
    name: str = Field(
        default="",
        description="What the job is for, in a word or two (`wiki/3`, `digest`): the label of "
        "its activities in the UI and of its failure. Empty = unnamed.",
    )
    prompt: str
    workdir: str
    tools: list[str] = Field(
        default_factory=list, description="Allowed tools; empty = coder default."
    )
    timeout_sec: int = Field(default_factory=lambda: settings.job.timeout_sec)
    stall_sec: int = Field(
        default_factory=lambda: settings.job.stall_sec,
        description="No output for this long = kill.",
    )
    context_limit_tokens: int = Field(
        default_factory=lambda: settings.job.context_limit_tokens,
        description="Context size at which the run is killed and retried.",
    )
    session_id: str = Field(
        default="",
        description="The session every try runs in, made before try 1 (`job.session`). "
        "Empty = the engine makes one; only for direct runs, retries would not share it.",
    )
    session_tokens: int = Field(
        default=0, description="Context size of that session when it was last seen, if known."
    )


class JobResult(BaseModel):
    """What the run produced. Whether the work is done is not decided here:
    `summary` is the coder's claim and `stats` the evidence; the worker judges."""

    session_id: str = Field(default="", description="Handle to continue in a later job.")
    tokens: Tokens = Field(default_factory=Tokens)
    cost_usd: float = 0.0
    usage_known: bool = Field(
        default=False,
        description="True when the coder reported its totals. False means tokens and cost "
        "are a partial sum or zero (opencode drops its last line now and then), not a real 0.",
    )
    duration_sec: float = 0.0
    stats: JobStats = Field(default_factory=JobStats)
    summary_text: str = Field(
        default="", description="The summary block as the coder wrote it, if any; for repair."
    )
    summary: JobSummary | None = Field(
        default=None, description="That block parsed, when it was valid."
    )
