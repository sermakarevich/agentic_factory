from agentic_factory.step.client import Client
from agentic_factory.step.opencode.client import OpencodeGo

CLIENTS: dict[str, type[Client]] = {
    "opencode": OpencodeGo,
}


def client_for(provider: str) -> Client:
    try:
        return CLIENTS[provider].from_env()
    except KeyError:
        known = ", ".join(sorted(CLIENTS))
        raise ValueError(f"unknown provider {provider!r}; known: {known}") from None
