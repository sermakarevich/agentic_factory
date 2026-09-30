from functools import cache

from factory_store.store import Store

from agentic_factory.settings.load import settings


@cache
def store() -> Store:
    """The process's one store. Made on first use: creating the engine opens
    no connection, so importing this costs nothing."""
    return Store.from_url(settings.store.url)
