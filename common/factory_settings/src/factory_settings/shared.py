from pathlib import Path

from factory_settings.load import load
from factory_settings.table import Table


class StoreSettings(Table):
    url: str


class SharedSettings(Table):
    """The values more than one package needs; each package keeps its own
    settings.toml for the rest."""

    store: StoreSettings


shared = load(SharedSettings, Path(__file__).parent)
