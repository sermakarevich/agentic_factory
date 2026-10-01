"""The designer's plan is refused for a format that is not allowed, a number
or path used twice, a path that leaves the tutorial folder, or a chapter
whose own files are missing from its outputs."""

import pytest

from tutorial.contract import Chapter, Format, TutorialPlan
from tutorial.plan import chapter_files, outside_problem, plan_problems

BOTH = [Format.md, Format.ipynb]


def _chapter(number: int, slug: str, **overrides: object) -> Chapter:
    values: dict[str, object] = {
        "number": number,
        "slug": slug,
        "title": slug.title(),
        "spec_path": f"specs/{number:02d}_{slug}.md",
        "formats": [Format.md],
        "outputs": [f"{number:02d}_{slug}.md"],
    }
    values.update(overrides)
    return Chapter.model_validate(values)


def _plan(*chapters: Chapter) -> TutorialPlan:
    return TutorialPlan(title="T", project=True, chapters=list(chapters))


def test_a_good_plan_has_no_problem() -> None:
    plan = _plan(
        _chapter(0, "setup"),
        _chapter(
            1,
            "explore",
            formats=BOTH,
            outputs=["01_explore.md", "01_explore.ipynb", "project/src/demo/ch01_load.py"],
        ),
    )

    assert plan_problems(plan, BOTH) == []


def test_an_empty_plan_is_refused() -> None:
    assert plan_problems(_plan(), BOTH) == ["the plan has no chapters"]


def test_a_format_not_allowed_is_refused() -> None:
    plan = _plan(_chapter(0, "setup", formats=[Format.ipynb], outputs=["00_setup.ipynb"]))

    assert plan_problems(plan, [Format.md]) == ["chapter 00: format ipynb is not allowed"]


def test_a_chapter_with_no_format_is_refused() -> None:
    plan = _plan(_chapter(0, "setup", formats=[], outputs=["00_setup.md"]))

    assert "chapter 00: no format" in plan_problems(plan, BOTH)


def test_a_duplicate_number_and_output_are_refused() -> None:
    plan = _plan(
        _chapter(1, "one", outputs=["01_one.md", "project/shared.py"]),
        _chapter(1, "two", outputs=["01_two.md", "project/shared.py"]),
    )

    problems = plan_problems(plan, BOTH)

    assert "chapter number '01' is used 2 times" in problems
    assert "output 'project/shared.py' is used 2 times" in problems


def test_a_duplicate_spec_path_is_refused() -> None:
    plan = _plan(_chapter(0, "a", spec_path="specs/x.md"), _chapter(1, "b", spec_path="specs/x.md"))

    assert "spec path 'specs/x.md' is used 2 times" in plan_problems(plan, BOTH)


@pytest.mark.parametrize("path", ["../escape.md", "/etc/passwd", "project/../../x.py", "", "."])
def test_an_output_outside_the_folder_is_refused(path: str) -> None:
    plan = _plan(_chapter(0, "setup", outputs=["00_setup.md", path]))
    problems = plan_problems(plan, BOTH)

    assert any("not a path inside the tutorial folder" in item for item in problems)


@pytest.mark.parametrize("path", ["../specs/00_setup.md", "notes/00_setup.md", "specs/00.txt"])
def test_a_spec_outside_specs_is_refused(path: str) -> None:
    plan = _plan(_chapter(0, "setup", spec_path=path))

    assert any(item.startswith("chapter 00: spec") for item in plan_problems(plan, BOTH))


@pytest.mark.parametrize("path", ["index.md", "plan.md", "specs/00_setup.md"])
def test_an_output_another_stage_writes_is_refused(path: str) -> None:
    plan = _plan(_chapter(0, "setup", outputs=["00_setup.md", path]))

    assert len(plan_problems(plan, BOTH)) >= 1


def test_the_chapter_file_of_every_format_must_be_an_output() -> None:
    chapter = _chapter(2, "charts", formats=BOTH, outputs=["02_charts.md"])

    assert chapter_files(chapter) == ["02_charts.md", "02_charts.ipynb"]
    assert plan_problems(_plan(chapter), BOTH) == ["chapter 02: outputs miss 02_charts.ipynb"]


def test_a_bad_slug_is_refused() -> None:
    plan = _plan(_chapter(0, "Set Up", outputs=["00_Set Up.md"]))

    assert any("slug" in item for item in plan_problems(plan, BOTH))


def test_a_plain_relative_path_stays_inside() -> None:
    assert outside_problem("project/src/demo/ch01.py") == ""
