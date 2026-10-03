"""Every template renders from one run's state with no placeholder left,
with absolute paths and the house style pasted in."""

from pathlib import Path

import factory_settings.vault
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


TEACHING = "knowledge/research_topics/evaluation_and_benchmarks/tutorials/evals"


@pytest.fixture
def vault_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """A fake vault workdir: the rules and the examples are read from it."""
    monkeypatch.setattr(factory_settings.vault, "workdir", lambda: tmp_path)
    return tmp_path


def test_the_designer_gets_the_allowed_formats_and_both_examples(vault_dir: Path) -> None:
    text = prompt("design", TUTORIAL)

    assert "Allowed chapter formats: md, ipynb" in text
    assert f"`{vault_dir}/knowledge/tutorials/grafana`" in text
    assert f"`{vault_dir}/{TEACHING}/project/notebooks/evals_primer.ipynb`" in text


@pytest.mark.parametrize("name", ["design", "write", "rewrite", "review", "finish"])
def test_every_teaching_job_reads_the_rules_from_the_vault(name: str, vault_dir: Path) -> None:
    assert f"`{vault_dir}/skills/tutorial/rules.md`" in prompt(name, TUTORIAL, CHAPTER)


def test_a_custom_root_does_not_move_the_rules_or_the_examples(vault_dir: Path) -> None:
    elsewhere = TUTORIAL.model_copy(update={"root": "/elsewhere/tutorials"})

    text = prompt("write", elsewhere, CHAPTER)

    assert "`/elsewhere/tutorials/duckdb/specs/01_query.md`" in text
    assert f"`{vault_dir}/skills/tutorial/rules.md`" in text
    assert f"`{vault_dir}/knowledge/tutorials/grafana`" in text
    assert f"`{vault_dir}/{TEACHING}/project/notebooks/evals_primer.ipynb`" in text
    assert "/elsewhere/tutorials/grafana" not in text


def test_the_designer_fixes_what_parallel_writers_share() -> None:
    text = prompt("design", TUTORIAL)

    assert "the levels tree" in text
    assert "the ONE running example" in text
    assert "Chapter 00 is the quick grasp" in text
    assert "the 2 to 4 ideas to carry forward" in text
    assert "The source's order is not\nthe outline" in text


def test_the_reviewer_checks_the_teaching() -> None:
    text = prompt("review", TUTORIAL, CHAPTER)

    assert "something used before it is explained" in text
    assert "a step that adds more than one new thing" in text
    assert "a result or a number left uninterpreted" in text
    assert "the plan's running example not used" in text
    assert "no closing 2 to 4 ideas to carry forward" in text
    assert "**Important:**" in text


def test_the_house_style_leaves_teaching_to_the_rules() -> None:
    text = prompt("house_style", TUTORIAL)

    assert "the 2-4 ideas to carry forward (see the rules)" in text
    assert "every claim is shown with code" not in text
    assert "short recap" not in text
