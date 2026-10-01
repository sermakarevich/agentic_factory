"""The one renderer every distill prompt uses: a template file with its variables filled."""

from pathlib import Path
from string import Template


def rendered(folder: Path, name: str, values: dict[str, object]) -> str:
    """The template `name.md` in `folder` with `values` filled in."""
    text = (folder / f"{name}.md").read_text(encoding="utf-8")
    return Template(text).substitute(values)
