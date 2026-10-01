import re

from temporal_agentic_factory.other_coders import CODERS_COMMAND, others


def test_own_pids_are_not_others() -> None:
    assert others([10, 11, 12], {11, 12}) == [10]


def test_the_pattern_matches_a_coders_process_and_not_a_prompt_naming_it() -> None:
    for command in (
        "/repo/.venv/bin/python3 /repo/.venv/bin/factory coders",
        "uv run factory coders",
        "/repo/.venv/bin/af coders --debug",
    ):
        assert re.search(CODERS_COMMAND, command), command
    for command in (
        "/repo/.venv/bin/af run Run `factory coders` once",
        "/repo/.venv/bin/factory runner",
        "sh -c nohup uv run factory coders > coders.log 2>&1 &",
        "/bin/zsh -c uv run factory coders",
    ):
        assert not re.search(CODERS_COMMAND, command), command
