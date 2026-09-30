from datetime import datetime


class JobFailed(Exception):
    """Base of all job failures."""


class RateLimited(JobFailed):
    def __init__(self, resets_at: datetime) -> None:
        super().__init__(f"rate limited until {resets_at.isoformat()}")
        self.resets_at = resets_at


class ContextPressure(JobFailed):
    """Context window filled past the limit; killed."""


class Stalled(JobFailed):
    """No output for longer than the stall limit; killed."""


class TimedOut(JobFailed):
    """Ran longer than the job timeout; killed."""


class ProviderError(JobFailed):
    """The model provider answered with an error."""


class NetworkError(JobFailed):
    """Could not reach the provider."""


class CoderCrashed(JobFailed):
    def __init__(self, exit_code: int, stderr: str = "") -> None:
        super().__init__(f"coder exited with code {exit_code}\n{stderr}".rstrip())
        self.exit_code = exit_code
        self.stderr = stderr


class SessionNotCreated(JobFailed):
    """The coder's session command ran but named no session."""


class BadOutput(JobFailed):
    """The answer of a call was cut off, not JSON, or did not match the schema."""
