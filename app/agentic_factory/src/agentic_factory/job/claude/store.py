import os
from pathlib import Path

CONFIG_DIR_VAR = "CLAUDE_CONFIG_DIR"
PROJECTS = "projects"


def config_dir() -> Path:
    return Path(os.environ.get(CONFIG_DIR_VAR) or Path.home() / ".claude")


def session_exists(session_id: str) -> bool:
    """Whether claude has a transcript for this session in any project. It decides
    the flag: a run in a new session takes `--session-id`, an existing one
    `--resume`, and claude refuses each flag in the other case."""
    return any((config_dir() / PROJECTS).glob(f"*/{session_id}.jsonl"))
