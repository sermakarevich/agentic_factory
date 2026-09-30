from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.contract import Job


def with_default_model(job: Job, harness: Harness) -> Job:
    """The job with the model it will run: its own, or the harness's default."""
    if job.model:
        return job
    return job.model_copy(update={"model": harness.default_model})
