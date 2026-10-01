"""The one renderer every distill prompt uses."""

from pathlib import Path

import pytest

from distill.prompts.template import rendered


def test_rendered_fills_a_placeholder_from_a_file(tmp_path: Path) -> None:
    (tmp_path / "greeting.md").write_text("Hello $name.", encoding="utf-8")
    assert rendered(tmp_path, "greeting", {"name": "Ada"}) == "Hello Ada."


def test_rendered_raises_on_a_missing_variable(tmp_path: Path) -> None:
    (tmp_path / "greeting.md").write_text("Hello $name.", encoding="utf-8")
    with pytest.raises(KeyError):
        rendered(tmp_path, "greeting", {})
