"""The locate activity: a fresh folder is made with its specs/, a folder in
use or a bad name fails at once."""

from pathlib import Path

import pytest
from temporalio.exceptions import ApplicationError
from temporalio.testing import ActivityEnvironment

from temporal_agentic_factory.workflows.tutorial.activities import locate_tutorial


async def test_a_fresh_folder_is_made_with_its_specs(tmp_path: Path) -> None:
    folder = tmp_path / "grafana"

    made = await ActivityEnvironment().run(locate_tutorial, str(folder))

    assert made == str(folder)
    assert (folder / "specs").is_dir()


async def test_a_folder_in_use_is_final(tmp_path: Path) -> None:
    folder = tmp_path / "grafana"
    folder.mkdir()
    (folder / "index.md").write_text("# taken\n")

    with pytest.raises(ApplicationError) as raised:
        await ActivityEnvironment().run(locate_tutorial, str(folder))

    assert raised.value.type == "BadFolder" and raised.value.non_retryable


async def test_a_bad_name_is_final(tmp_path: Path) -> None:
    with pytest.raises(ApplicationError) as raised:
        await ActivityEnvironment().run(locate_tutorial, str(tmp_path / "Not A Name"))

    assert raised.value.non_retryable
    assert not (tmp_path / "Not A Name").exists()
