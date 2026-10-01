"""fetch_source: a local markdown in, the manifest and files out; failures are typed."""

import json
from pathlib import Path

import pytest

from distill import topics
from distill.contract import DistillRequest, EntryType
from distill.fetch import fetch_source
from distill.sources import SourceError


def _source_md(path: Path) -> Path:
    """A local markdown source: two headings, well past the min_text_chars floor."""
    path.write_text(
        "# Widget Manual\n\n"
        + ("The widget spins clockwise under load. " * 40)
        + "\n\n## Alpha\n\n"
        + ("Alpha mode conserves power during idle hours. " * 40)
        + "\n\n## Beta\n\n"
        + ("Beta mode doubles throughput when queued. " * 40)
        + "\n",
        encoding="utf-8",
    )
    return path


def test_local_md_gives_the_manifest_and_the_files(tmp_path: Path) -> None:
    src = _source_md(tmp_path / "notes.md")
    work = tmp_path / "work"

    fetched = fetch_source(DistillRequest(url=str(src), chunk_chars=2000), work)

    assert fetched.kind == "article" and fetched.type is EntryType.article
    assert fetched.work_dir == str(work) and fetched.source_pdf == "" and fetched.repo_dir == ""
    assert fetched.chunks
    for position, chunk in enumerate(fetched.chunks, start=1):
        assert chunk.index == position
        assert chunk.slug.startswith(f"{position:02d}-")
        assert Path(chunk.path).is_file()
    listing = json.loads((work / "chunks.json").read_text(encoding="utf-8"))
    assert listing == [chunk.model_dump() for chunk in fetched.chunks]
    header = (work / "source.md").read_text(encoding="utf-8")
    assert f"Source: {src}" in header and "Kind: article" in header


def test_the_provenance_header_records_topic_and_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "topics" / "widgets").mkdir(parents=True)
    monkeypatch.setattr(topics, "research_topics_dir", lambda: tmp_path / "topics")
    request = DistillRequest(
        url=str(_source_md(tmp_path / "notes.md")), topic="widgets", research_target="spin"
    )

    fetch_source(request, tmp_path / "work")

    header = (tmp_path / "work" / "source.md").read_text(encoding="utf-8")
    assert "Research-Target: spin\nTopic: widgets\n" in header


def test_a_missing_file_is_a_permanent_source_error(tmp_path: Path) -> None:
    request = DistillRequest(url=str(tmp_path / "missing.md"))
    with pytest.raises(SourceError) as caught:
        fetch_source(request, tmp_path / "work")
    assert caught.value.transient is False


def test_an_unknown_topic_is_refused_before_any_fetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(topics, "research_topics_dir", lambda: tmp_path / "topics")
    request = DistillRequest(url=str(_source_md(tmp_path / "notes.md")), topic="not_a_topic")
    with pytest.raises(ValueError, match="not_a_topic"):
        fetch_source(request, tmp_path / "work")
    assert not (tmp_path / "work").exists()


def test_a_source_with_only_boilerplate_is_refused(tmp_path: Path) -> None:
    src = tmp_path / "readme.md"
    src.write_text("## Sponsor\n\n" + ("Thanks to our sponsors. " * 30), encoding="utf-8")
    with pytest.raises(SourceError, match="no substantive content") as caught:
        fetch_source(DistillRequest(url=str(src)), tmp_path / "work")
    assert caught.value.transient is False
