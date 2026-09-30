from agentic_factory.job.coders.claude.harness import ClaudeHarness
from agentic_factory.job.coders.harness import Harness
from agentic_factory.job.coders.opencode.harness import OpencodeHarness

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
