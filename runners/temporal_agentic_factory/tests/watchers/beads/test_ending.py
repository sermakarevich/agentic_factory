from agentic_factory.job.contract import JobResult
from agentic_factory.job.outcome import JobOutcome
from agentic_factory.job.report.contract import JobReport, Verdict
from temporal_agentic_factory.watchers.beads.ending import ending_of_completed, ending_of_stopped


def _outcome(verdict: Verdict | None, result: bool = True) -> JobOutcome:
    report = (
        None
        if verdict is None
        else JobReport(task="t", done=[], not_done=["the tests"], problems=[], verdict=verdict)
    )
    return JobOutcome(
        session_id="ses_1",
        result=JobResult(session_id="ses_1") if result else None,
        failure="" if result else "rate limited",
        report=report,
    )


def test_done_verdict_closes() -> None:
    ending = ending_of_completed(_outcome(Verdict.DONE))
    assert ending.close
    assert "verdict done" in ending.note


def test_partial_verdict_blocks_with_what_is_missing() -> None:
    ending = ending_of_completed(_outcome(Verdict.PARTIAL))
    assert not ending.close
    assert ending.note == "verdict partial: the tests"


def test_failed_run_blocks() -> None:
    ending = ending_of_completed(_outcome(Verdict.DONE, result=False))
    assert not ending.close
    assert "rate limited" in ending.note


def test_missing_report_blocks_with_verdict_unknown() -> None:
    ending = ending_of_completed(_outcome(None))
    assert not ending.close
    assert ending.note == "verdict unknown: session ses_1 submitted no report"


def test_a_failed_report_made_by_code_blocks_with_its_problem() -> None:
    outcome = _outcome(None).model_copy(
        update={
            "report": JobReport(
                task="t", done=[], not_done=[], problems=["Stalled: x"], verdict=Verdict.FAILED
            )
        }
    )
    assert ending_of_completed(outcome).note == "verdict failed: Stalled: x"


def test_stopped_workflow_blocks() -> None:
    ending = ending_of_stopped("bead-bd-1-1", "TIMED_OUT")
    assert not ending.close
    assert "TIMED_OUT" in ending.note
