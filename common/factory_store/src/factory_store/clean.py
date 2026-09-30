"""factory_store.clean — keep caller text storable in Postgres.

Postgres rejects the NUL character inside text and JSONB. Tool output can
contain it, so every write cleans caller text first: NUL becomes the visible
text ``\\u0000`` and nothing is lost silently.
"""

from typing import Any, overload

NUL = "\x00"
VISIBLE_NUL = "\\u0000"


@overload
def without_nul(value: str) -> str: ...


@overload
def without_nul(value: dict[str, Any]) -> dict[str, Any]: ...


@overload
def without_nul(value: list[Any]) -> list[Any]: ...


@overload
def without_nul(value: Any) -> Any: ...


def without_nul(value: Any) -> Any:
    """A copy of `value` with every NUL replaced by its visible text."""
    if isinstance(value, str):
        return _string_without_nul(value)
    if isinstance(value, dict):
        return _dict_without_nul(value)
    if isinstance(value, list):
        return _list_without_nul(value)
    return value


def _string_without_nul(text: str) -> str:
    return text.replace(NUL, VISIBLE_NUL)


def _dict_without_nul(mapping: dict[str, Any]) -> dict[str, Any]:
    return {_string_without_nul(key): without_nul(item) for key, item in mapping.items()}


def _list_without_nul(items: list[Any]) -> list[Any]:
    return [without_nul(item) for item in items]
