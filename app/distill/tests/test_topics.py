from pathlib import Path

import pytest

from distill import topics


@pytest.fixture
def research_topics(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for name in ("agents", "storage"):
        (tmp_path / name).mkdir()
    (tmp_path / "index.md").write_text("")
    monkeypatch.setattr(topics, "research_topics_dir", lambda: tmp_path)
    return tmp_path


def test_existing_topics_are_the_folders(research_topics: Path) -> None:
    assert topics.existing_topics() == ["agents", "storage"]


def test_a_known_topic_passes(research_topics: Path) -> None:
    assert topics.validate_topic(" agents ") == "agents"


@pytest.mark.parametrize("value", ["", "Agents", "agent-tools"])
def test_a_badly_formed_topic_is_refused(research_topics: Path, value: str) -> None:
    with pytest.raises(ValueError, match="topic"):
        topics.validate_topic(value)


def test_an_unknown_topic_lists_the_known_ones(research_topics: Path) -> None:
    with pytest.raises(ValueError, match="agents, storage"):
        topics.validate_topic("compute")
