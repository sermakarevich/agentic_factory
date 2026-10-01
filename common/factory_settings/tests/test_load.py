from pathlib import Path

import pytest

from factory_settings.load import load
from factory_settings.shared import SharedSettings, shared
from factory_settings.table import Table


class Demo(Table):
    size: int


class DemoSettings(Table):
    demo: Demo


def folder_with(tmp_path: Path, text: str) -> Path:
    (tmp_path / "settings.toml").write_text(text)
    return tmp_path


def test_the_file_then_the_local_file_then_the_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    folder = folder_with(tmp_path, "[demo]\nsize = 1\n")
    assert load(DemoSettings, folder).demo.size == 1
    (folder / "settings.local.toml").write_text("[demo]\nsize = 2\n")
    assert load(DemoSettings, folder).demo.size == 2
    monkeypatch.setenv("AF_DEMO__SIZE", "3")
    assert load(DemoSettings, folder).demo.size == 3


def test_a_misspelled_key_is_refused(tmp_path: Path) -> None:
    folder = folder_with(tmp_path, "[demo]\nsize = 1\nsise = 2\n")
    with pytest.raises(ValueError, match="sise"):
        load(DemoSettings, folder)


def test_the_shared_values_are_typed() -> None:
    assert isinstance(shared, SharedSettings)
    assert shared.store.url.startswith("postgresql+asyncpg://")


def test_another_package_table_in_the_environment_is_ignored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("AF_STORE__URL", "sqlite:///elsewhere")
    assert load(DemoSettings, folder_with(tmp_path, "[demo]\nsize = 1\n")).demo.size == 1
