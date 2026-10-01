from pathlib import Path

from factory_settings import vault
from factory_settings.shared import shared


def test_shared_vault_has_the_four_folders() -> None:
    assert shared.vault.workdir
    assert shared.vault.research
    assert shared.vault.investment
    assert shared.vault.research_topics


def test_each_folder_is_absolute_with_tilde_expanded() -> None:
    folders = {
        "workdir": vault.workdir(),
        "research": vault.research_dir(),
        "investment": vault.investment_dir(),
        "research_topics": vault.research_topics_dir(),
    }
    assert folders["workdir"] == Path(shared.vault.workdir).expanduser()
    assert folders["research"] == Path(shared.vault.research).expanduser()
    assert folders["investment"] == Path(shared.vault.investment).expanduser()
    assert folders["research_topics"] == Path(shared.vault.research_topics).expanduser()
    for folder in folders.values():
        assert folder.is_absolute()
        assert "~" not in str(folder)
