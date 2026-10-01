import re

from factory_settings.vault import research_topics_dir

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")


def existing_topics() -> list[str]:
    """Sorted names of the topic folders on disk, hidden ones (`.obsidian`)
    left out; empty when unreadable."""
    base = research_topics_dir()
    try:
        entries = [
            path for path in base.iterdir() if path.is_dir() and not path.name.startswith(".")
        ]
    except OSError:
        return []
    return sorted(path.name for path in entries)


def validate_topic(value: str | None) -> str:
    """Return the stripped topic or raise ValueError naming what is wrong."""
    topic = (value or "").strip()
    if not topic:
        raise ValueError("input topic is required")
    if not _SNAKE_CASE_RE.match(topic):
        raise ValueError(
            f"input topic {topic!r} must be snake_case (lowercase letters, digits, underscores)"
        )
    if not (research_topics_dir() / topic).is_dir():
        known = existing_topics()
        known_str = ", ".join(known) if known else "none found on disk"
        raise ValueError(
            f"input topic {topic!r} does not exist under research_topics/ "
            f"(existing topics: {known_str}); "
            f'create one with `ai add topic {topic} --desc "<one line>"`'
        )
    return topic
