from typing import Any

from factory_store.clean import without_nul


def test_replaces_nul_in_a_string() -> None:
    assert without_nul("a\x00b") == "a\\u0000b"


def test_leaves_a_plain_string_untouched() -> None:
    assert without_nul("hello") == "hello"


def test_replaces_nul_in_nested_lists_and_dicts() -> None:
    payload: dict[str, Any] = {"msg": "a\x00b", "items": ["x\x00y", 1, {"n": "\x00"}]}
    assert without_nul(payload) == {
        "msg": "a\\u0000b",
        "items": ["x\\u0000y", 1, {"n": "\\u0000"}],
    }


def test_replaces_nul_in_dict_keys() -> None:
    assert without_nul({"a\x00b": 1}) == {"a\\u0000b": 1}


def test_returns_a_copy_and_keeps_the_original() -> None:
    payload: dict[str, Any] = {"msg": "a\x00b", "items": ["x"]}
    cleaned = without_nul(payload)
    assert cleaned == {"msg": "a\\u0000b", "items": ["x"]}
    assert payload == {"msg": "a\x00b", "items": ["x"]}
    assert cleaned is not payload


def test_leaves_other_values_alone() -> None:
    assert without_nul(3) == 3
    assert without_nul(None) is None
