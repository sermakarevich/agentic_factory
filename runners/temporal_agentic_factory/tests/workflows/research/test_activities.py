"""The research activities: a bad topic or a bad candidates file fails at
once, a good topic makes the run's folder."""

from pathlib import Path

import pytest
from research.contract import ResearchRequest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from temporal_agentic_factory.workflows.research.activities import locate_target, read_candidates


def _request(topic: str, root: Path) -> ResearchRequest:
    return ResearchRequest(
        topics=["agents"], focus="What can agents do?", target="t1", topic=topic, root=str(root)
    )


async def test_a_bad_topic_is_final_and_names_the_root(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()

    with pytest.raises(ApplicationError) as err:
        await ActivityEnvironment().run(locate_target, _request("nope", tmp_path))

    assert err.value.non_retryable
    assert f"under {tmp_path}/" in err.value.message


async def test_a_good_topic_makes_the_target_folder(tmp_path: Path) -> None:
    (tmp_path / "agents").mkdir()

    found = await ActivityEnvironment().run(locate_target, _request("agents", tmp_path))

    assert found == str(tmp_path / "agents" / "research" / "t1")
    assert Path(found).is_dir()


async def test_the_candidates_file_is_read_back(tmp_path: Path) -> None:
    path = tmp_path / "candidates.json"
    path.write_text(
        '{"candidates": [{"url": "u", "title": "t", "kind": "paper", "authors": "a", '
        '"date": "2026-01-01", "venue": "v", "abstract": "x", "status": "candidate"}]}'
    )

    found = await ActivityEnvironment().run(read_candidates, str(path))

    assert [item.title for item in found.candidates] == ["t"]


async def test_a_missing_or_malformed_candidates_file_is_final(tmp_path: Path) -> None:
    broken = tmp_path / "broken.json"
    broken.write_text("{not json")

    for path in (tmp_path / "missing.json", broken):
        with pytest.raises(ApplicationError) as err:
            await ActivityEnvironment().run(read_candidates, str(path))
        assert err.value.non_retryable
