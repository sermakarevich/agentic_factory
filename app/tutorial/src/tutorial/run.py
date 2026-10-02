"""One tutorial run: where it lands, the folder made ready for the designer,
and the state the workflow grows as the jobs finish."""

from pathlib import Path

from pydantic import BaseModel, Field

from tutorial.contract import (
    Chapter,
    ChapterOutcome,
    Finished,
    Spend,
    TutorialOutcome,
    TutorialPlan,
    TutorialRequest,
    name_problem,
)
from tutorial.plan import SPECS

PROJECT = "project"  # the shared runnable project the designer scaffolds
PLAN = "plan.md"  # the designer's plan of the whole tutorial
INDEX = "index.md"  # the tutorial's own index, and the tutorials' index one level up


def located_dir(folder: Path) -> Path:
    """`folder` made ready for the designer, with its specs/ folder. Refused
    when its name is no plain folder name, or it is there and not empty: a
    tutorial is never written over another."""
    problem = name_problem(folder.name)
    if problem:
        raise ValueError(problem)
    if folder.exists() and any(folder.iterdir()):
        raise ValueError(f"{folder} already exists and is not empty")
    (folder / SPECS).mkdir(parents=True, exist_ok=True)
    return folder


class Tutorial(BaseModel):
    """The run so far: the request and the tutorials' folder, then the plan,
    the chapters and what the jobs cost as each stage fills them in."""

    request: TutorialRequest
    root: str = Field(description="The tutorials' folder; the tutorial is <root>/<name>.")
    plan: TutorialPlan = Field(
        default_factory=lambda: TutorialPlan(title="", project=False, chapters=[])
    )
    chapters: list[ChapterOutcome] = []
    spend: Spend = Field(default_factory=Spend)

    @property
    def folder(self) -> Path:
        """<root>/<name>: the tutorial's folder."""
        return Path(self.root) / self.request.name

    @property
    def tutorials_index(self) -> Path:
        """<root>/index.md: the list every tutorial is added to."""
        return Path(self.root) / INDEX

    def path_of(self, relative: str) -> Path:
        """A path the plan names, made absolute inside the tutorial folder."""
        return self.folder / relative

    def others_of(self, chapter: Chapter) -> list[str]:
        """Every output of the other chapters: what this chapter's writer must not touch."""
        return [
            path
            for item in self.plan.chapters
            if item.number != chapter.number
            for path in item.outputs
        ]

    def named(self, name: str) -> "Tutorial":
        """The run with the folder name the naming job picked."""
        request = self.request.model_copy(update={"name": name})
        return self.model_copy(update={"request": request})

    def outcome(self, finished: Finished) -> TutorialOutcome:
        """What the workflow returns: the chapters in reading order."""
        return TutorialOutcome(
            folder=str(self.folder),
            index_path=finished.index_path,
            title=self.plan.title,
            chapters=sorted(self.chapters, key=lambda item: item.number),
            fixes=finished.fixes,
            spend=self.spend,
        )
