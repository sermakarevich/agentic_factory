import pytest
from temporalio.testing import ActivityEnvironment

from agentic_factory.job.contract import JobResult
from agentic_factory.job.outcome import JobOutcome
from temporal_agentic_factory.activities import record as activity
from tests.fakes import FakeStore


async def test_the_job_row_is_written_from_the_stored_tries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = FakeStore()
    monkeypatch.setattr(activity, "store", lambda: db)
    outcome = JobOutcome(session_id="s1", result=JobResult(session_id="s1"))

    await ActivityEnvironment().run(activity.record_job, outcome)

    assert [c[:2] for c in db.calls] == [("load_tries", "s1"), ("save_job", "s1")]
    record = db.calls[1][2]
    assert record.outcome.value == "done" and record.tries == 0
