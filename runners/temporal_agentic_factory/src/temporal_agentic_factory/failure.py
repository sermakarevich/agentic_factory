from datetime import UTC, datetime, timedelta

from temporalio.exceptions import ApplicationError

from agentic_factory.failure import CoderCrashed, JobFailed, RateLimited
from temporal_agentic_factory.settings.load import settings


def to_application_error(failure: JobFailed) -> ApplicationError:
    """One `ApplicationError` per failure class, typed by the class name so
    retry policies can name them. A rate limit tells Temporal when to retry."""
    kind = type(failure).__name__
    if isinstance(failure, RateLimited):
        delay = _delay_until(failure.resets_at)
        return ApplicationError(str(failure), type=kind, next_retry_delay=delay)
    if isinstance(failure, CoderCrashed):
        return ApplicationError(str(failure), failure.exit_code, failure.stderr, type=kind)
    return ApplicationError(str(failure), type=kind)


def _delay_until(resets_at: datetime) -> timedelta:
    """How long until the limit lifts; at least `min_retry_delay_sec`, as it may have passed."""
    floor = timedelta(seconds=settings.job_activity.min_retry_delay_sec)
    return max(resets_at - datetime.now(UTC), floor)
