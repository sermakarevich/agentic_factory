import os


def environment(workdir: str) -> dict[str, str]:
    """The coder's environment: ours, with PWD pointing at the job's workdir,
    because opencode reads PWD rather than the real cwd."""
    return {**os.environ, "PWD": workdir}
