from pathlib import Path

from temporal_agentic_factory.options import absolute, given


def test_given_drops_none_values() -> None:
    assert given({"model": "muse-spark", "timeout_sec": None}) == {"model": "muse-spark"}


def test_absolute_expands_and_makes_absolute() -> None:
    assert Path(absolute(".")).is_absolute()
    assert absolute("~") == str(Path("~").expanduser().resolve())
