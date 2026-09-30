from enum import StrEnum


class Reasoning(StrEnum):
    """How much the model thinks before answering."""

    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
