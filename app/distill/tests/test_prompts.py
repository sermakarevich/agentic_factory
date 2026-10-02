from pathlib import Path

import pytest

from distill.contract import DistillRequest, EntryPlan, EntryType, FetchedChunk, FetchedSource
from distill.prompts import Entry, index_prompt, page_prompt, plan_prompt, wiki_prompt

REQUEST = DistillRequest(url="https://example.com/paper", topic="agents")
CHUNK = FetchedChunk(index=1, slug="01-intro", title="Intro", path="/w/chunks/01-intro.md", chars=9)
PLAN = EntryPlan(research_dir="/kb/research/Paper", slug="Paper", title="Paper", type="Paper")


def _entry(kind: str, request: DistillRequest = REQUEST) -> Entry:
    return Entry(request=request, fetched=_fetched(kind), plan=PLAN, run_date="2026-09-30")


def _fetched(kind: str) -> FetchedSource:
    return FetchedSource(
        work_dir="/w",
        source_md="/w/source.md",
        title="Paper",
        kind=kind,
        type=EntryType.codebase if kind == "repo" else EntryType.paper,
        fetched_at="2026-09-30T00:00:00+00:00",
        chunks=[CHUNK, CHUNK.model_copy(update={"index": 2, "slug": "02-more"})],
    )


def test_plan_reads_the_manifest_and_states_the_plan() -> None:
    text = plan_prompt(REQUEST, _fetched("pdf"), "2026-09-30")
    assert "/w/chunks.json" in text and "/w/source.md" in text
    assert "knowledge/research/*/source/source.md" in text
    assert "2026-09-30" in text and "State the plan" in text
    assert "Codebase track" not in text


def test_plan_with_a_target_dir_fixes_the_folder_instead_of_routing() -> None:
    request = DistillRequest(url="https://example.com/paper", target_dir="/kb/notes/Paper")
    text = plan_prompt(request, _fetched("pdf"), "2026-09-30")
    assert "<research_dir> is /kb/notes/Paper" in text and "Do NOT derive" in text
    assert "Investment/finance topic" not in text and "Provenance-first rule" not in text
    assert "State the plan" in text


def test_plan_adds_the_codebase_track_for_a_clone() -> None:
    assert "Codebase track" in plan_prompt(REQUEST, _fetched("repo"), "2026-09-30")


@pytest.mark.parametrize(("kind", "phrase"), [("pdf", "chunk 1/2"), ("repo", "macro component")])
def test_wiki_names_the_chunk_and_the_plan(kind: str, phrase: str) -> None:
    text = wiki_prompt(_entry(kind), CHUNK)
    assert phrase in text
    assert "/w/chunks/01-intro.md" in text and "/kb/research/Paper/source/plan.md" in text
    assert "Do not run git." in text


@pytest.mark.parametrize(
    ("kind", "closing"),
    [("pdf", "The argument in five moves"), ("repo", "The system in five moves")],
)
def test_digest_closes_by_kind(kind: str, closing: str) -> None:
    text = page_prompt("digest", _entry(kind))
    assert closing in text and "/kb/research/Paper/digest.md" in text


def test_summary_is_the_technical_analysis_for_a_clone() -> None:
    text = page_prompt("summary", _entry("repo"))
    assert "# Technical Analysis: Paper" in text and "**Date:** 2026-09-30" in text
    assert "Human Readable TL;DR" not in text


def test_summary_is_the_paper_layout_for_a_text() -> None:
    text = page_prompt("summary", _entry("pdf"))
    assert "## Human Readable TL;DR" in text and "type Paper" in text


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("explainer", "/kb/research/Paper/explainer.md"),
        ("questions", "/kb/research/Paper/questions.md"),
        ("critical_thinking", "/kb/research/Paper/critical_thinking.md"),
    ],
)
def test_later_jobs_read_the_digest_and_write_their_file(name: str, path: str) -> None:
    text = page_prompt(name, _entry("pdf"))
    assert "/kb/research/Paper/digest.md" in text and path in text


def test_index_lists_the_verifier_problems_only_when_there_are_some() -> None:
    clean = index_prompt(_entry("pdf"), [])
    assert "Verifier problems" not in clean and "{id: original" in clean
    fixing = index_prompt(_entry("pdf"), ["verify: missing digest.md"])
    assert "## Verifier problems" in fixing and "- verify: missing digest.md" in fixing


def test_file_moves_into_the_topic_under_the_root_asked_for(tmp_path: Path) -> None:
    request = DistillRequest(url="https://example.com/paper", topic="agents", root=str(tmp_path))
    text = page_prompt("file", _entry("pdf", request))
    assert f'mv "/kb/research/Paper" "{tmp_path}/agents/<Name>/"' in text


def test_file_moves_into_the_topic_without_asking() -> None:
    text = page_prompt("file", _entry("pdf"))
    assert 'mv "/kb/research/Paper"' in text and "research_topics/agents/<Name>/" in text
    assert "do NOT ask" in text and "State path" in text


def test_repo_variant_falls_back_to_the_base_template() -> None:
    assert "macro component" not in page_prompt("digest", _entry("repo"))
    assert "## Verifier problems" in index_prompt(_entry("repo"), ["verify: x"])
