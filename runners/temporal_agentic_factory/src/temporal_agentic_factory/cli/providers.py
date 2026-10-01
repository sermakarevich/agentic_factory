"""The submit commands' check that a coder provider has a queue someone polls."""

from temporal_agentic_factory.cli.errors import fail
from temporal_agentic_factory.settings.load import settings


def refuse_unconfigured(*providers: str) -> None:
    """Exit with a clean error for a provider with no `[providers.<name>]`
    table: `af coders` runs no worker for it, so its jobs would wait forever."""
    configured = sorted(settings.providers)
    for provider in providers:
        if provider not in settings.providers:
            fail(
                f"provider {provider!r} has no [providers.{provider}] table in settings,"
                f" so nothing runs its coder jobs; configured: {', '.join(configured)}"
            )
