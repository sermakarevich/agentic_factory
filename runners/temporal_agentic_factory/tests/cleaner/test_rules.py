import pytest
from pydantic import ValidationError
from temporalio.client import WorkflowExecutionStatus

from temporal_agentic_factory.cleaner.rules import runs_to_delete
from temporal_agentic_factory.settings.model import CleanRule
from tests.cleaner.listed import COMPLETED, FAILED, RUNNING, Listed, at

RULE = CleanRule(workflow_type="beads_poll", keep_completed=1, keep_failed=3)


def _ids(runs: list[Listed]) -> list[str]:
    return sorted(run.run_id for run in runs)


def test_keeps_the_newest_completed_run_and_the_newest_three_failed() -> None:
    completed = [Listed(f"c{m}", status=COMPLETED, close_time=at(m)) for m in (2, 5, 1, 4)]
    failed = [Listed(f"f{m}", status=FAILED, close_time=at(m)) for m in (3, 1, 5, 2, 4)]
    selected = runs_to_delete(completed + failed, RULE)
    assert _ids(selected.completed) == ["c1", "c2", "c4"]
    assert _ids(selected.failed) == ["f1", "f2"]


@pytest.mark.parametrize(
    "status",
    [
        WorkflowExecutionStatus.FAILED,
        WorkflowExecutionStatus.TIMED_OUT,
        WorkflowExecutionStatus.TERMINATED,
        WorkflowExecutionStatus.CANCELED,
    ],
)
def test_every_failure_status_counts_as_failed(status: WorkflowExecutionStatus) -> None:
    runs = [Listed(f"r{m}", status=status, close_time=at(m)) for m in range(5)]
    selected = runs_to_delete(runs, RULE)
    assert (_ids(selected.completed), _ids(selected.failed)) == ([], ["r0", "r1"])


def test_continued_as_new_counts_as_completed() -> None:
    runs = [
        Listed("new", status=WorkflowExecutionStatus.CONTINUED_AS_NEW, close_time=at(2)),
        Listed("old", status=COMPLETED, close_time=at(1)),
    ]
    selected = runs_to_delete(runs, RULE)
    assert (_ids(selected.completed), selected.failed) == (["old"], [])


def test_a_running_run_or_one_without_status_is_never_selected() -> None:
    runs = [Listed("live", status=RUNNING), Listed("unknown", status=None)]
    rule = CleanRule(workflow_type="beads_poll", keep_completed=0, keep_failed=0)
    selected = runs_to_delete(runs, rule)
    assert (selected.completed, selected.failed) == ([], [])


def test_runs_of_other_types_are_never_selected() -> None:
    runs = [
        Listed("job", workflow_type="job", close_time=at(0)),
        Listed("distill", workflow_type="distill", status=FAILED, close_time=at(0)),
        Listed("poll", close_time=at(1)),
    ]
    rule = CleanRule(workflow_type="beads_poll", keep_completed=0, keep_failed=0)
    selected = runs_to_delete(runs, rule)
    assert (_ids(selected.completed), selected.failed) == (["poll"], [])


def test_keep_zero_selects_every_closed_run() -> None:
    runs = [Listed("c", close_time=at(1)), Listed("f", status=FAILED, close_time=at(2))]
    rule = CleanRule(workflow_type="beads_poll", keep_completed=0, keep_failed=0)
    selected = runs_to_delete(runs, rule)
    assert (_ids(selected.completed), _ids(selected.failed)) == (["c"], ["f"])


def test_a_run_without_close_time_sorts_by_its_start() -> None:
    runs = [
        Listed("closed", close_time=at(5)),
        Listed("unclosed", close_time=None, start_time=at(10)),
    ]
    assert _ids(runs_to_delete(runs, RULE).completed) == ["closed"]


@pytest.mark.parametrize("name", ["beads_poll' OR 'x' = 'x", "two words", ""])
def test_a_type_that_could_change_the_query_is_refused(name: str) -> None:
    with pytest.raises(ValidationError):
        CleanRule(workflow_type=name, keep_completed=1, keep_failed=1)
