from agentic_factory.job.contract import Job
from agentic_factory.job.harness import Harness


def with_default_model(job: Job, harness: Harness) -> Job:
    """The job with the model it will run: its own, or the harness's default."""
    if job.model:
        return job
    return job.model_copy(update={"model": harness.default_model})
