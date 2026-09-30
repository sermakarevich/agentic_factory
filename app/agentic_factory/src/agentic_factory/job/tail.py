from agentic_factory.settings.load import settings


def tail_of(output: bytes) -> str:
    """The end of a process's output, as much as a failure message keeps."""
    return output[-settings.job.failure_tail_chars :].decode(errors="replace").strip()
