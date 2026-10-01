from agentic_factory.step.judge.client import JudgeClient
from agentic_factory.step.judge.contract import Judgment


def with_default_model(judgment: Judgment, client: JudgeClient) -> Judgment:
    """The judgment with the model it will run: its own, or the judge's default."""
    if judgment.model:
        return judgment
    return judgment.model_copy(update={"model": client.default_model})
