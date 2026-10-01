from datetime import UTC, datetime, timedelta

from temporal_agentic_factory.watchers.beads.last_check import FAILED_LINE, check_of, failed_check
from temporal_agentic_factory.watchers.beads.models import PollSummary

AT = datetime(2026, 10, 1, tzinfo=UTC)


def test_a_check_counts_what_the_tick_did() -> None:
    summary = PollSummary(
        spawned=["a", "b"],
        closed=["c"],
        blocked=["f"],
        reopened=["d"],
        skipped={"e": "why"},
        errors=["x"],
    )
    check = check_of(AT, summary)
    counts = (check.spawned, check.closed, check.blocked, check.released, check.skipped)
    assert (*counts, check.errors) == (2, 1, 1, 1, 1, 1)
    assert check.line() == "spawned 2 closed 1 blocked 1 released 1 skipped 1 errors 1"


def test_the_line_leaves_the_time_out_so_quiet_ticks_do_not_change_it() -> None:
    later = AT + timedelta(seconds=10)
    assert check_of(AT, PollSummary()).line() == check_of(later, PollSummary()).line()


def test_a_failed_check_keeps_the_text_and_has_a_short_line() -> None:
    check = failed_check(AT, "bd is down\nwith a long trace")
    assert check.error.startswith("bd is down")
    assert check.line() == FAILED_LINE
