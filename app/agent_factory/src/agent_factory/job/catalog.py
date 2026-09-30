from agent_factory.job.claude.harness import ClaudeHarness
from agent_factory.job.harness import Harness
from agent_factory.job.opencode.harness import OpencodeHarness

HARNESSES: dict[str, type[Harness]] = {
    "claude": ClaudeHarness,
    "opencode": OpencodeHarness,
}


def harness_for(provider: str) -> Harness:
    try:
        return HARNESSES[provider]()
    except KeyError:
        known = ", ".join(sorted(HARNESSES))
        raise ValueError(f"unknown provider {provider!r}; known: {known}") from None
