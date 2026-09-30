from agentic_factory.callback import Callback


class Silent(Callback):
    """The callback of a step run inside a job (summary repair, the report):
    its events stay out of the job's stream, where a heartbeat callback would
    read the step's tokens as the coder's context."""
