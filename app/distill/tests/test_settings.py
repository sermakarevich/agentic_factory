from pathlib import Path

import pytest
from factory_settings.load import load

import distill.settings.load
from distill.settings.load import settings
from distill.settings.model import Settings

FOLDER = Path(distill.settings.load.__file__).parent


def test_toml_defaults_are_typed() -> None:
    chunking = settings.chunking
    assert chunking.chars_min < chunking.chars_default < chunking.chars_max
    assert settings.fetch.throttle.youtube.at_once == 1


def test_env_overrides_a_nested_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AF_VERIFY__MIN_BYTES", "5")
    assert load(Settings, FOLDER).verify.min_bytes == 5
    assert load(Settings, FOLDER).fetch.http_timeout_sec == settings.fetch.http_timeout_sec


def test_every_knob_is_a_setting() -> None:
    assert settings.vault.pdf_copy_max_bytes > 0
    assert settings.fetch.work_root
    assert settings.repo.max_file_bytes > 0
    assert settings.chunking.slug_chars > 0
