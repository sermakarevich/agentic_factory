"""Every tutorial prompt: one template per job, one function collecting the variables."""

from collections.abc import Sequence
from pathlib import Path
from string import Template

from factory_settings import vault

from tutorial.contract import Chapter, ChapterOutcome
from tutorial.plan import SPECS
from tutorial.run import INDEX, PLAN, PROJECT, Tutorial
from tutorial.settings.load import settings

FOLDER = Path(__file__).parent
HOUSE_STYLE = "house_style"  # the template pasted into every other one


def prompt(
    name: str, tutorial: Tutorial, chapter: Chapter | None = None, problems: Sequence[str] = ()
) -> str:
    """The template `name` (a job: name, design, write, rewrite, review,
    finish) filled for this run, with the chapter and the reviewer's
    problems where the job has them."""
    return _rendered(FOLDER, name, values(tutorial, chapter, problems))


def values(
    tutorial: Tutorial, chapter: Chapter | None = None, problems: Sequence[str] = ()
) -> dict[str, object]:
    """Every variable any template names, every path absolute: the jobs
    never see this repo, only what their prompt says. The rules, the
    notebook recipe and the examples are in the vault, whatever root the run lands under."""
    request = tutorial.request
    return {
        "topic": request.topic,
        "level": request.level,
        "formats": ", ".join(item.value for item in request.formats),
        "name": request.name,
        "root": tutorial.root,
        "folder": str(tutorial.folder),
        "specs_dir": str(tutorial.path_of(SPECS)),
        "project_dir": str(tutorial.path_of(PROJECT)),
        "plan_path": str(tutorial.path_of(PLAN)),
        "index_path": str(tutorial.path_of(INDEX)),
        "tutorials_index": str(tutorial.tutorials_index),
        "rules": str(vault.workdir() / settings.tutorial.rules),
        "notebook": str(vault.workdir() / settings.tutorial.notebook),
        "style_example": str(vault.workdir() / settings.tutorial.style_example),
        "teaching_example": str(vault.workdir() / settings.tutorial.teaching_example),
        "notebook_command": _notebook_command(),
        "house_style": _rendered(FOLDER, HOUSE_STYLE, {}),
        "title": tutorial.plan.title,
        "status_table": _status_table(tutorial.chapters),
        "number": chapter.label if chapter else "",
        "spec_path": str(tutorial.path_of(chapter.spec_path)) if chapter else "",
        "outputs": _bullets(tutorial, chapter.outputs if chapter else []),
        "others": _bullets(tutorial, tutorial.others_of(chapter) if chapter else []),
        "problems": "\n".join(f"- {problem}" for problem in problems) or "- (none)",
    }


def _notebook_command() -> str:
    """The command that runs a notebook end to end, each cell bounded by the timeout."""
    cfg = settings.tutorial
    return f"{cfg.notebook_command} --ExecutePreprocessor.timeout={cfg.notebook_cell_timeout_sec}"


def _bullets(tutorial: Tutorial, paths: list[str]) -> str:
    """One `- <absolute path>` line per path, or `- (none)`."""
    return "\n".join(f"- `{tutorial.path_of(path)}`" for path in paths) or "- (none)"


def _status_table(chapters: list[ChapterOutcome]) -> str:
    """One `| NN | slug | title | status | problems |` row per chapter, in reading order."""
    rows = [
        f"| {item.number:02d} | {item.slug} | {item.title} | {item.status.value} | "
        f"{'; '.join(item.problems)} |"
        for item in sorted(chapters, key=lambda item: item.number)
    ]
    return "\n".join(["| # | slug | title | status | problems |", "|---|---|---|---|---|", *rows])


def _rendered(folder: Path, name: str, values: dict[str, object]) -> str:
    """The template `name.md` in `folder` with `values` filled in."""
    text = (folder / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).substitute(values)
