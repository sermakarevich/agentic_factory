from agentic_factory.job.continuation import continue_job
from agentic_factory.job.contract import Job


def test_continuation_keeps_the_session_and_adds_a_header() -> None:
    job = Job(prompt="p", workdir="/w", session_id="s1")
    assert continue_job(job, 1) is job
    resumed = continue_job(job, 2, session_tokens=42)
    assert resumed.session_id == "s1" and resumed.session_tokens == 42
    assert resumed.prompt.startswith("Try 2:") and resumed.prompt.endswith("follow.\n\np")
