from pathlib import Path

from factory_settings.load import load

from autocode.settings.model import Settings

settings = load(Settings, Path(__file__).parent)
