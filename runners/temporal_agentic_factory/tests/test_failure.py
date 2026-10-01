from datetime import UTC, datetime, timedelta

from agentic_factory.failure import CoderCrashed, CoderNotFound, RateLimited, Stalled
from temporal_agentic_factory.failure import to_application_error


def test_rate_limit_tells_temporal_when_to_retry() -> None:
    err = to_application_error(RateLimited(datetime.now(UTC) + timedelta(minutes=10)))
    assert err.type == "RateLimited"
    assert err.next_retry_delay is not None
    assert timedelta(minutes=9) < err.next_retry_delay <= timedelta(minutes=10)


def test_crash_keeps_exit_code_and_stderr() -> None:
    err = to_application_error(CoderCrashed(3, "boom"))
    assert err.type == "CoderCrashed"
    assert err.details == (3, "boom")


def test_plain_failure_is_typed_by_class() -> None:
    err = to_application_error(Stalled("no output"))
    assert err.type == "Stalled" and err.next_retry_delay is None
    assert not err.non_retryable  # another try may help


def test_a_failure_another_try_cannot_help_stops_the_retries() -> None:
    err = to_application_error(CoderNotFound("opencode is not installed"))
    assert err.type == "CoderNotFound" and err.non_retryable
