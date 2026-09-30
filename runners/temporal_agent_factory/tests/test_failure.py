from datetime import UTC, datetime, timedelta

from agent_factory.failure import CoderCrashed, RateLimited, Stalled
from temporal_agent_factory.failure import to_application_error


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
