from pathlib import Path

from agentic_factory.job.contract import Job


def ensure_workdir(job: Job) -> None:
    """The directory the coder works in, made when it is not there yet."""
    Path(job.workdir).mkdir(parents=True, exist_ok=True)
