from agentic_factory.step.judge.client import JudgeClient
from agentic_factory.step.judge.typesafe import TypeSafeJev

JUDGES: dict[str, type[JudgeClient]] = {"typesafe": TypeSafeJev}


def judge_for(provider: str) -> JudgeClient:
    """The named judge client, built from the environment."""
    try:
        return JUDGES[provider].from_env()
    except KeyError:
        raise ValueError(f"unknown judge provider {provider!r}; one of {sorted(JUDGES)}") from None
