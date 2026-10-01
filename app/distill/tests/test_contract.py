import pytest
from pydantic import ValidationError

from distill.contract import DistillRequest, EntryType, FetchedSource, SourceKind


def test_a_target_dir_must_be_absolute() -> None:
    with pytest.raises(ValidationError, match="absolute"):
        DistillRequest(url="https://example.com/a", target_dir="notes/Paper")


def test_a_target_dir_and_a_topic_do_not_go_together() -> None:
    with pytest.raises(ValidationError, match="both"):
        DistillRequest(url="https://example.com/a", target_dir="/kb/notes/Paper", topic="agents")


def test_a_target_dir_alone_is_kept_as_given() -> None:
    assert DistillRequest(url="https://example.com/a", target_dir="/kb/notes/Paper").target_dir == (
        "/kb/notes/Paper"
    )


def _fetched(kind: SourceKind) -> FetchedSource:
    return FetchedSource(
        work_dir="/w",
        source_md="/w/source.md",
        title="T",
        kind=kind,
        fetched_at="2026-09-30T00:00:00+00:00",
        chunks=[],
    )


@pytest.mark.parametrize(
    ("kind", "type"),
    [
        (SourceKind.youtube, EntryType.video),
        (SourceKind.pdf, EntryType.paper),
        (SourceKind.x, EntryType.article),
        (SourceKind.article, EntryType.article),
        (SourceKind.repo, EntryType.codebase),
    ],
)
def test_the_entry_type_is_derived_from_the_kind(kind: SourceKind, type: EntryType) -> None:
    fetched = _fetched(kind)
    assert fetched.kind is kind
    assert fetched.type is type


def test_the_derived_type_serializes() -> None:
    assert _fetched(SourceKind.repo).model_dump()["type"] == EntryType.codebase
