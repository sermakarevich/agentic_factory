"""Whether the designer's plan can be built: every rule a chapter list must
meet before any writer starts, as plain checks over the paths it names."""

from collections import Counter
from pathlib import PurePosixPath

from tutorial.contract import Chapter, Format, TutorialPlan, name_problem

SPECS = "specs"  # the folder the designer writes the chapter specs into
RESERVED = ("index.md", "plan.md")  # the files the finish job and the designer write


def plan_problems(plan: TutorialPlan, allowed: list[Format]) -> list[str]:
    """Every reason the plan cannot be built; empty when it can."""
    if not plan.chapters:
        return ["the plan has no chapters"]
    return [
        *_repeated("chapter number", [f"{item.number:02d}" for item in plan.chapters]),
        *_repeated("chapter slug", [item.slug for item in plan.chapters]),
        *_repeated("spec path", [item.spec_path for item in plan.chapters]),
        *_repeated("output", [path for item in plan.chapters for path in item.outputs]),
        *(problem for item in plan.chapters for problem in chapter_problems(item, allowed)),
    ]


def chapter_problems(chapter: Chapter, allowed: list[Format]) -> list[str]:
    """Every reason one chapter cannot be written as planned."""
    label = f"chapter {chapter.label}"
    slug = name_problem(chapter.slug)
    return [
        *([f"{label}: slug: {slug}"] if slug else []),
        *_format_problems(label, chapter.formats, allowed),
        *_spec_problems(label, chapter.spec_path),
        *(f"{label}: {problem}" for path in chapter.outputs for problem in _output_problems(path)),
        *(
            f"{label}: outputs miss {file}"
            for file in chapter_files(chapter)
            if file not in chapter.outputs
        ),
    ]


def chapter_files(chapter: Chapter) -> list[str]:
    """`NN_<slug>.md`, `NN_<slug>.ipynb`: the chapter's own files, one per format."""
    return [f"{chapter.label}_{chapter.slug}.{item.value}" for item in chapter.formats]


def outside_problem(path: str) -> str:
    """Why `path` would land outside the tutorial folder; empty when it stays inside."""
    parts = PurePosixPath(path).parts
    if not parts or path.startswith("/") or ".." in parts or parts == (".",):
        return f"{path!r} is not a path inside the tutorial folder"
    return ""


def _format_problems(label: str, formats: list[Format], allowed: list[Format]) -> list[str]:
    """A chapter has at least one format, each allowed and named once."""
    if not formats:
        return [f"{label}: no format"]
    unknown = [item.value for item in formats if item not in allowed]
    problems = [f"{label}: format {value} is not allowed" for value in unknown]
    if len(set(formats)) != len(formats):
        problems.append(f"{label}: a format named twice")
    return problems


def _spec_problems(label: str, path: str) -> list[str]:
    """The spec sits inside, under specs/, as a .md file."""
    outside = outside_problem(path)
    if outside:
        return [f"{label}: spec {outside}"]
    spec = PurePosixPath(path)
    if spec.parts[0] != SPECS or spec.suffix != ".md":
        return [f"{label}: spec {path!r} is not a specs/*.md file"]
    return []


def _output_problems(path: str) -> list[str]:
    """An output sits inside, not among the specs, and is no file another stage writes."""
    outside = outside_problem(path)
    if outside:
        return [f"output {outside}"]
    if PurePosixPath(path).parts[0] == SPECS:
        return [f"output {path!r} is under specs/, which the designer owns"]
    if path in RESERVED:
        return [f"output {path!r} is written by another stage"]
    return []


def _repeated(what: str, values: list[str]) -> list[str]:
    """One problem per value named more than once."""
    return [
        f"{what} {value!r} is used {count} times"
        for value, count in Counter(values).items()
        if count > 1
    ]
