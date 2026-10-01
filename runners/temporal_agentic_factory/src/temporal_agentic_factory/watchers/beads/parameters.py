"""The job parameters a bead carries: the fields of `Job` a bead may set, the
same for its `af_job` metadata and its description's front matter.

Only what a source gives is kept, so merging sources lowest first leaves the
highest one's value: Job's defaults < front matter < `af_job`.
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

from agentic_factory.job.structured_output.contract import Schema


class InvalidParameters(ValueError):
    """Job parameters with an unknown key or a value of the wrong kind."""


class JobParameters(BaseModel):
    """`Job` fields a bead may set, every one optional; `prompt` is never one
    (it is the bead's title and description). `structured_output` is the
    schema that makes the bead a job with structured output."""

    model_config = ConfigDict(extra="forbid")
    provider: str | None = None
    model: str | None = None
    name: str | None = None
    workdir: str | None = None
    tools: list[str] | None = None
    timeout_sec: int | None = None
    stall_sec: int | None = None
    context_limit_tokens: int | None = None
    structured_output: Schema | None = None

    @field_validator("tools", mode="before")
    @classmethod
    def _tools_from_text(cls, value: Any) -> Any:
        """`Read,Edit` as written in front matter, as a list."""
        if isinstance(value, str):
            return [tool.strip() for tool in value.split(",") if tool.strip()]
        return value


def parameters_of(raw: Any, source: str) -> dict[str, Any]:
    """The fields `raw` gives, validated; InvalidParameters naming `source` when
    it is not an object of known keys with valid values."""
    if not isinstance(raw, dict):
        raise InvalidParameters(f"{source} is not an object: {raw!r}")
    try:
        given = JobParameters.model_validate(raw)
    except ValidationError as error:
        raise InvalidParameters(f"{source}: {errors_line(error)}") from error
    return given.model_dump(exclude_unset=True)


def errors_line(error: ValidationError) -> str:
    """Each failed field and why, on one line."""
    return "; ".join(
        f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}" for item in error.errors()
    )
