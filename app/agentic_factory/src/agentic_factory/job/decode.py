import json
from typing import Any

from pydantic import BaseModel, ValidationError


def decoded_line[L: BaseModel](text: str, shape: type[L]) -> tuple[L, dict[str, Any]] | None:
    """One line of a coder's stream as the harness's line shape, plus the json
    it came from; None when it is not json or not that shape."""
    try:
        raw = json.loads(text)
        return shape.model_validate(raw), raw
    except (ValueError, ValidationError):
        return None
