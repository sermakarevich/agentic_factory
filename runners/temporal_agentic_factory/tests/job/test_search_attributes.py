from agentic_factory.job.contract import Job, JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from temporal_agentic_factory.job import search_attributes as sa


def test_start_carries_who_runs_the_job_and_where() -> None:
    job = Job(prompt="p", workdir="/w", provider="claude", model="m")
    given = {pair.key.name: pair.value for pair in sa.at_start(job)}
    assert given == {"Provider": "claude", "Model": "m", "Workdir": "/w"}


def test_end_says_how_it_ended_and_what_the_report_judged() -> None:
    report = JobReport(task="t", done=[], not_done=[], problems=[], verdict=Verdict.PARTIAL)
    done = JobOutcome(session_id="s", result=JobResult(), report=report)
    failed = JobOutcome(session_id="s", failure="Stalled: no output")
    assert [u.value for u in sa.at_end(done)] == ["done", "partial"]
    assert [u.value for u in sa.at_end(failed)] == ["failed", ""]
    assert [u.key.name for u in sa.at_end(done)] == ["Outcome", "Verdict"]


def test_every_key_is_a_keyword_the_register_step_knows() -> None:
    names = {key.name for key in sa.KEYS}
    assert names == {"Provider", "Model", "Workdir", "Runner", "Outcome", "Verdict"}
