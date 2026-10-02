from pathlib import Path

import pytest

from distill import topics


@pytest.fixture
def research_topics(tmp_path: Path) -> Path:
    for name in ("agents", "storage", ".obsidian"):
        (tmp_path / name).mkdir()
    (tmp_path / "index.md").write_text("")
    return tmp_path


def test_existing_topics_are_the_folders(research_topics: Path) -> None:
    assert topics.existing_topics(research_topics) == ["agents", "storage"]


def test_a_known_topic_passes(research_topics: Path) -> None:
    assert topics.validate_topic(" agents ", research_topics) == "agents"


@pytest.mark.parametrize("value", ["", "Agents", "agent-tools"])
def test_a_badly_formed_topic_is_refused(research_topics: Path, value: str) -> None:
    with pytest.raises(ValueError, match="topic"):
        topics.validate_topic(value, research_topics)


def test_an_unknown_topic_lists_the_known_ones(research_topics: Path) -> None:
    with pytest.raises(ValueError, match="agents, storage"):
        topics.validate_topic("compute", research_topics)


def test_an_unknown_topic_says_how_to_create_it(research_topics: Path) -> None:
    with pytest.raises(ValueError, match="ai add topic compute --desc"):
        topics.validate_topic("compute", research_topics)


def test_a_topic_is_looked_for_under_the_root_given(tmp_path: Path) -> None:
    (tmp_path / "custom" / "agents").mkdir(parents=True)
    (tmp_path / "other").mkdir()

    assert topics.validate_topic("agents", tmp_path / "custom") == "agents"
    with pytest.raises(ValueError, match=f"under {tmp_path / 'other'}/"):
        topics.validate_topic("agents", tmp_path / "other")
