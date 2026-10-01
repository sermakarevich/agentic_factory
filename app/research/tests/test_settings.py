from pathlib import Path

import pytest
from factory_settings.load import load

import research.settings.load
from research.settings.load import settings
from research.settings.model import Settings

FOLDER = Path(research.settings.load.__file__).parent


def test_toml_defaults_are_typed() -> None:
    research = settings.research
    assert research.n_sources == 10
    assert research.reserve_share == 0.3
    assert research.lenses == ["tech", "ai"]
    assert research.candidates_per_source_min < research.candidates_per_source_max
    assert research.abstract_chars == 1200


def test_env_overrides_a_nested_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AF_RESEARCH__N_SOURCES", "4")
    assert load(Settings, FOLDER).research.n_sources == 4
    assert load(Settings, FOLDER).research.abstract_chars == settings.research.abstract_chars


def test_every_knob_is_a_setting() -> None:
    assert settings.research.n_sources > 0
    assert settings.research.reserve_share > 0
    assert settings.research.lenses
    assert settings.research.candidates_per_source_min > 0
    assert settings.research.candidates_per_source_max > 0
    assert settings.research.abstract_chars > 0
