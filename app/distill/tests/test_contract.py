"""A request names at most one home for the entry, and a named home is a full path."""

import pytest
from pydantic import ValidationError

from distill.contract import DistillRequest


def test_a_target_dir_must_be_absolute() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        DistillRequest(url="https://example.com/a", target_dir="notes/Paper")


def test_a_target_dir_and_a_topic_do_not_go_together() -> None:
    with pytest.raises(ValidationError, match="both"):
        DistillRequest(url="https://example.com/a", target_dir="/kb/notes/Paper", topic="agents")


def test_a_target_dir_alone_is_kept_as_given() -> None:
    assert DistillRequest(url="https://example.com/a", target_dir="/kb/notes/Paper").target_dir == (
        "/kb/notes/Paper"
    )
