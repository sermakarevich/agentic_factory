"""Every template renders from one run's state with no placeholder left,
with absolute paths and the house style pasted in."""

import pytest

from tutorial.contract import (
    Chapter,
    ChapterOutcome,
    ChapterStatus,
    Format,
    TutorialPlan,
    TutorialRequest,
)
from tutorial.prompts.prompt import FOLDER, prompt
from tutorial.run import Tutorial

CHAPTER = Chapter(
    number=1,
    slug="query",
    title="Your first query",
    spec_path="specs/01_query.md",
    formats=[Format.md, Format.ipynb],
    outputs=["01_query.md", "01_query.ipynb", "project/src/demo/ch01_query.py"],
)
OTHER = Chapter(
    number=0,
    slug="setup",
    title="Setup",
    spec_path="specs/00_setup.md",
    formats=[Format.md],
    outputs=["00_setup.md"],
)
TUTORIAL = Tutorial(
    request=TutorialRequest(topic="DuckDB from zero", name="duckdb"),
    root="/kb/knowledge/tutorials",
    plan=TutorialPlan(title="DuckDB", project=True, chapters=[OTHER, CHAPTER]),
    chapters=[
        ChapterOutcome(
            number=1,
            slug="query",
            title="Your first query",
            status=ChapterStatus.failed,
            problems=["cell 3 raises"],
        ),
        ChapterOutcome(number=0, slug="setup", title="Setup", status=ChapterStatus.done),
    ],
)
NAMES = sorted(path.stem for path in FOLDER.glob("*.md"))


def test_every_job_has_a_template() -> None:
    assert NAMES == ["design", "finish", "house_style", "name", "review", "rewrite", "write"]


@pytest.mark.parametrize("name", NAMES)
def test_a_template_renders_with_no_placeholder_left(name: str) -> None:
    text = prompt(name, TUTORIAL, chapter=CHAPTER, problems=["x"])

    assert "$" not in text


@pytest.mark.parametrize("name", ["design", "write", "rewrite", "review", "finish"])
def test_every_job_gets_the_house_style(name: str) -> None:
    assert "House style of the knowledge-base tutorials" in prompt(name, TUTORIAL, CHAPTER)


def test_the_writer_gets_absolute_paths_and_what_not_to_touch() -> None:
    text = prompt("write", TUTORIAL, chapter=CHAPTER)

    assert "`/kb/knowledge/tutorials/duckdb/specs/01_query.md`" in text
    assert "- `/kb/knowledge/tutorials/duckdb/01_query.ipynb`" in text
    assert "- `/kb/knowledge/tutorials/duckdb/00_setup.md`" in text
    assert "nbconvert --to notebook --execute --inplace" in text


def test_the_rewrite_carries_the_reviewers_problems() -> None:
    text = prompt("rewrite", TUTORIAL, chapter=CHAPTER, problems=["cell 3 raises", "no recap"])

    assert "- cell 3 raises\n- no recap" in text


def test_the_finish_job_gets_the_status_table_and_both_indexes() -> None:
    text = prompt("finish", TUTORIAL)

    assert "| 00 | setup | Setup | done |  |" in text
    assert "| 01 | query | Your first query | failed | cell 3 raises |" in text
    assert text.index("| 00 |") < text.index("| 01 |")
    assert "/kb/knowledge/tutorials/duckdb/index.md" in text
    assert "/kb/knowledge/tutorials/index.md" in text


def test_the_designer_gets_the_allowed_formats_and_the_style_example() -> None:
    text = prompt("design", TUTORIAL)

    assert "Allowed chapter formats: md, ipynb" in text
    assert "/kb/knowledge/tutorials/grafana" in text
