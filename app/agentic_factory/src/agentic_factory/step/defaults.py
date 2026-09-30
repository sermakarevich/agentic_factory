from agentic_factory.step.client import Client
from agentic_factory.step.contract import Step


def with_default_model(step: Step, client: Client) -> Step:
    """The step with the model it will run: its own, or the client's default."""
    if step.model:
        return step
    return step.model_copy(update={"model": client.default_model})
