from pathlib import Path

import pytest
from factory_settings.load import load

import autocode.settings.load
from autocode.settings.load import settings
from autocode.settings.model import Settings

FOLDER = Path(autocode.settings.load.__file__).parent


def test_toml_defaults_are_typed() -> None:
    cfg = settings.autocode
    assert cfg.provider
    assert cfg.implement_attempts >= 1
    assert cfg.gate_attempts >= 1
    assert cfg.test_timeout_sec > 0
    assert cfg.git_timeout_sec > 0
    assert cfg.output_tail_chars > 0


def test_env_overrides_a_nested_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AF_AUTOCODE__IMPLEMENT_ATTEMPTS", "7")
    assert load(Settings, FOLDER).autocode.implement_attempts == 7
    assert load(Settings, FOLDER).autocode.provider == settings.autocode.provider
