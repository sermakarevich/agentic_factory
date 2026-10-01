from temporal_agentic_factory.watchers.beads.markers import (
    MARKER_PREFIX,
    attempt_of,
    marker,
    marker_for,
    retried,
)


def test_marker_round_trip() -> None:
    assert marker_for(["noise", marker("bead-bd-1-1")]) == "bead-bd-1-1"
    assert marker_for(["nothing here"]) is None
    assert MARKER_PREFIX in marker("bead-bd-1-1")


def test_latest_marker_names_the_current_attempt() -> None:
    comments = [marker("bead-bd-1-1"), retried("flaky"), marker("bead-bd-1-2")]
    assert marker_for(comments) == "bead-bd-1-2"


def test_a_retry_ends_the_previous_marker() -> None:
    assert marker_for([marker("bead-bd-1-1"), retried("")]) is None


def test_every_marker_counts_one_attempt() -> None:
    assert attempt_of([]) == 1
    assert attempt_of(["noise", marker("bead-bd-1-1"), retried("")]) == 2
