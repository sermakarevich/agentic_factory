import pytest

from temporal_agentic_factory.watchers.beads.front_matter import (
    FrontMatterError,
    split_front_matter,
)


def test_no_front_matter_leaves_the_description() -> None:
    assert split_front_matter("Just text.\n---\nnot a block") == (
        {},
        "Just text.\n---\nnot a block",
    )


def test_front_matter_is_read_and_stripped() -> None:
    description = '---\nprovider: claude\ntimeout_sec: 60\ntools: ["Read"]\n---\n\nThe body.\n'
    fields, body = split_front_matter(description)
    assert fields == {"provider": "claude", "timeout_sec": "60", "tools": ["Read"]}
    assert body == "The body."


def test_unclosed_front_matter_is_an_error() -> None:
    with pytest.raises(FrontMatterError):
        split_front_matter("---\nprovider: claude\nThe body.")


def test_a_line_without_a_key_is_an_error() -> None:
    with pytest.raises(FrontMatterError):
        split_front_matter("---\njust words\n---\nbody")
