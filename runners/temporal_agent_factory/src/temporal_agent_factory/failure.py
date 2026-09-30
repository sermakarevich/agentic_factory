from datetime import UTC, datetime, timedelta

from temporalio.exceptions import ApplicationError

from agent_factory.failure import CoderCrashed, JobFailed, RateLimited


def to_application_error(failure: JobFailed) -> ApplicationError:
    """One `ApplicationError` per failure class, typed by the class name so
    retry policies can name them. A rate limit tells Temporal when to retry."""
    kind = type(failure).__name__
    if isinstance(failure, RateLimited):
        wait = max(failure.resets_at - datetime.now(UTC), timedelta(seconds=1))
        return ApplicationError(str(failure), type=kind, next_retry_delay=wait)
    if isinstance(failure, CoderCrashed):
        return ApplicationError(str(failure), failure.exit_code, failure.stderr, type=kind)
    return ApplicationError(str(failure), type=kind)
