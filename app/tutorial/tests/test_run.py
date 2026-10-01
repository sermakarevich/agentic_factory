"""Where a tutorial lands, the folder check that refuses to write over one,
and the state the prompts read."""

from pathlib import Path

import factory_settings.vault
import pytest

from tutorial.contract import (
    Chapter,
    ChapterOutcome,
    ChapterStatus,
    Finished,
    Format,
    TutorialPlan,
    TutorialRequest,
)
from tutorial.run import Tutorial, located_dir, tutorials_dir

CHAPTERS = [
    Chapter(
        number=n,
        slug=slug,
        title=slug,
        spec_path=f"specs/{n:02d}_{slug}.md",
        formats=[Format.md],
        outputs=[f"{n:02d}_{slug}.md", f"project/ch{n:02d}.py"],
    )
    for n, slug in [(0, "setup"), (1, "query")]
]
TUTORIAL = Tutorial(
    request=TutorialRequest(topic="DuckDB", name="duckdb"),
    root="/kb/knowledge/tutorials",
    plan=TutorialPlan(title="DuckDB", project=True, chapters=CHAPTERS),
)


def test_tutorials_land_under_the_vault(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(factory_settings.vault, "workdir", lambda: tmp_path)

    assert tutorials_dir() == tmp_path / "knowledge" / "tutorials"


def test_a_new_folder_is_made_with_its_specs(tmp_path: Path) -> None:
    folder = located_dir(tmp_path / "duckdb")

    assert folder == tmp_path / "duckdb"
    assert (folder / "specs").is_dir()


def test_an_empty_folder_is_reused(tmp_path: Path) -> None:
    (tmp_path / "duckdb").mkdir()

    assert (located_dir(tmp_path / "duckdb") / "specs").is_dir()


def test_a_folder_with_files_is_refused(tmp_path: Path) -> None:
    (tmp_path / "duckdb").mkdir()
    (tmp_path / "duckdb" / "index.md").write_text("# taken")

    with pytest.raises(ValueError, match="not empty"):
        located_dir(tmp_path / "duckdb")


def test_a_bad_folder_name_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="name"):
        located_dir(tmp_path / "Bad Name")
    assert not (tmp_path / "Bad Name").exists()


def test_paths_are_absolute_inside_the_folder() -> None:
    assert TUTORIAL.folder == Path("/kb/knowledge/tutorials/duckdb")
    assert TUTORIAL.tutorials_index == Path("/kb/knowledge/tutorials/index.md")
    assert TUTORIAL.path_of("specs/00_setup.md") == TUTORIAL.folder / "specs" / "00_setup.md"


def test_the_others_of_a_chapter_are_every_other_output() -> None:
    assert TUTORIAL.others_of(CHAPTERS[0]) == ["01_query.md", "project/ch01.py"]


def test_naming_fills_the_request() -> None:
    unnamed = TUTORIAL.model_copy(update={"request": TutorialRequest(topic="DuckDB")})

    assert unnamed.named("duck").folder.name == "duck"


def test_the_outcome_lists_chapters_in_reading_order() -> None:
    late_first = TUTORIAL.model_copy(
        update={
            "chapters": [
                ChapterOutcome(number=1, slug="query", title="q", status=ChapterStatus.failed),
                ChapterOutcome(number=0, slug="setup", title="s", status=ChapterStatus.done),
            ]
        }
    )

    outcome = late_first.outcome(Finished(index_path="/i.md", fixes=["a link"]))

    assert [item.number for item in outcome.chapters] == [0, 1]
    assert (outcome.folder, outcome.index_path, outcome.fixes) == (
        str(TUTORIAL.folder),
        "/i.md",
        ["a link"],
    )
