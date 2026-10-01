"""verify: the recipe check over a finished entry."""

from pathlib import Path

from distill.settings.load import settings
from distill.verify import verify_research_dir

_PAD = "lorem ipsum dolor sit amet. " * 40


def _write(path: Path, body: str, pad: bool = True) -> None:
    """Write a file, padded past settings.verify.min_bytes unless asked otherwise."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = body + ("\n" + _PAD if pad else "")
    assert len(text.encode("utf-8")) > settings.verify.min_bytes or not pad
    path.write_text(text, encoding="utf-8")


def _good_entry(root: Path) -> Path:
    """A complete entry that must pass verification."""
    entry = root / "research" / "SomePaper"
    _write(entry / "index.md", "# Some Paper\n\n> [[summary|Summary]] | [[digest|Digest]]\n")
    (entry / "index.md").write_text(
        "# Some Paper\n\n"
        "Orientation sentences here.\n\n"
        "## Read This Folder\n"
        "- [[summary|Summary]]\n"
        "- [[digest|Digest]]\n"
        "- [[explainer|Explainer]]\n"
        "- [[critical_thinking|Critical thinking]]\n"
        "- [[questions|Questions]]\n\n"
        "## Wiki table\n"
        "- [[wiki/01-first-claim|First claim]]\n"
        "- [[wiki/02-second-claim|Second claim]]\n\n"
        "## Original Source\n"
        "- [upstream](https://example.com/paper)\n"
        "- [local copy](source/source.md)\n" + _PAD + "\n",
        encoding="utf-8",
    )
    _write(entry / "summary.md", "# Some Paper\n\n## Human Readable TL;DR\n\nPlain words.\n")
    _write(
        entry / "digest.md",
        "# Some Paper — Digest\n\n"
        "## 1. [[wiki/01-first-claim|First claim]]\n"
        "**In one sentence:** The first claim holds.\n\n"
        "## 2. [[wiki/02-second-claim|Second claim]]\n"
        "**In one sentence:** The second claim follows.\n",
    )
    _write(entry / "explainer.md", "# Some Paper — In Plain Language\n\n## What is this?\n")
    _write(entry / "questions.md", "# Retrieval Practice: Some Paper\n\n### Q1. What?\n")
    _write(
        entry / "critical_thinking.md", "# Critical Analysis: Some Paper\n\n## Claims vs evidence\n"
    )
    _write(
        entry / "source" / "source.md",
        "# Some Paper\nSource: https://example.com/paper\nKind: article\n",
    )
    _write(
        entry / "wiki" / "01-first-claim.md",
        "# First claim\n**In one sentence:** The first claim holds.\n## Key points\n",
    )
    _write(
        entry / "wiki" / "02-second-claim.md",
        "# Second claim\n**In one sentence:** The second claim follows.\n## Key points\n",
    )
    return entry


def test_complete_entry_passes(tmp_path: Path) -> None:
    """A recipe-complete entry verifies clean, so the run may succeed."""
    assert verify_research_dir(_good_entry(tmp_path)) == []


def test_missing_explainer_fails(tmp_path: Path) -> None:
    """An entry without explainer.md fails the verify stage."""
    entry = _good_entry(tmp_path)
    (entry / "explainer.md").unlink()
    failures = verify_research_dir(entry)
    assert any("explainer.md" in failure for failure in failures)


def test_chrome_only_wiki_page_fails(tmp_path: Path) -> None:
    """An entry whose only wiki page is site chrome fails the verify stage."""
    entry = _good_entry(tmp_path)
    for page in (entry / "wiki").glob("*.md"):
        page.unlink()
    _write(
        entry / "wiki" / "01-latest-commit.md",
        "# Latest commit\n**In one sentence:** Nav chrome.\n",
    )
    (entry / "digest.md").write_text(
        "# Some Paper — Digest\n\n## 1. [[wiki/01-latest-commit|Latest commit]]\n"
        "**In one sentence:** Nav chrome.\n" + _PAD + "\n",
        encoding="utf-8",
    )
    failures = verify_research_dir(entry)
    assert any("01-latest-commit.md" in failure for failure in failures)


def test_rejects_all_chrome_names(tmp_path: Path) -> None:
    """skip-to-content and sign-in stems fail just like latest-commit."""
    entry = _good_entry(tmp_path)
    _write(entry / "wiki" / "03-skip-to-content.md", "# Skip\n**In one sentence:** Chrome.\n")
    _write(entry / "wiki" / "04-sign-in.md", "# Sign in\n**In one sentence:** Chrome.\n")
    failures = verify_research_dir(entry)
    assert any("03-skip-to-content.md" in failure for failure in failures)
    assert any("04-sign-in.md" in failure for failure in failures)


def test_rejects_boilerplate_wiki_pages(tmp_path: Path) -> None:
    """Sponsor/License/Star History pages fail like site chrome."""
    entry = _good_entry(tmp_path)
    _write(entry / "wiki" / "03-sponsor.md", "# Sponsor\n**In one sentence:** Thanks.\n")
    _write(entry / "wiki" / "04-license.md", "# License\n**In one sentence:** MIT.\n")
    _write(entry / "wiki" / "05-star-history.md", "# Star History\n**In one sentence:** Stars.\n")
    failures = verify_research_dir(entry)
    assert any("03-sponsor.md" in failure for failure in failures)
    assert any("04-license.md" in failure for failure in failures)
    assert any("05-star-history.md" in failure for failure in failures)


def test_trivial_file_fails(tmp_path: Path) -> None:
    """A 100-byte summary.md counts as missing, not done."""
    entry = _good_entry(tmp_path)
    (entry / "summary.md").write_text("# Tiny\n", encoding="utf-8")
    failures = verify_research_dir(entry)
    assert any("summary.md" in failure for failure in failures)


def test_source_without_provenance_fails(tmp_path: Path) -> None:
    """source.md without the `Source:` line fails, as does a missing one."""
    entry = _good_entry(tmp_path)
    (entry / "source" / "source.md").write_text(
        "# Some Paper\n\nNo provenance.\n" + _PAD, encoding="utf-8"
    )
    assert any("Source:" in failure for failure in verify_research_dir(entry))
    (entry / "source" / "source.md").unlink()
    assert any("source/source.md" in failure for failure in verify_research_dir(entry))


def test_empty_wiki_fails(tmp_path: Path) -> None:
    """No wiki pages at all is a failure, not a green run."""
    entry = _good_entry(tmp_path)
    for page in (entry / "wiki").glob("*.md"):
        page.unlink()
    assert any("wiki/" in failure for failure in verify_research_dir(entry))


def test_digest_missing_wiki_page_fails(tmp_path: Path) -> None:
    """A digest that drops a rung fails: rungs must actually differ."""
    entry = _good_entry(tmp_path)
    (entry / "digest.md").write_text(
        "# Some Paper — Digest\n\n## 1. [[wiki/01-first-claim|First claim]]\n"
        "**In one sentence:** The first claim holds.\n" + _PAD + "\n",
        encoding="utf-8",
    )
    failures = verify_research_dir(entry)
    assert any("02-second-claim.md" in failure for failure in failures)


def test_index_broken_link_fails(tmp_path: Path) -> None:
    """index.md links must resolve to files that exist."""
    entry = _good_entry(tmp_path)
    with (entry / "index.md").open("a", encoding="utf-8") as handle:
        handle.write("- [[wiki/99-never-written|Ghost]]\n")
    failures = verify_research_dir(entry)
    assert any("99-never-written" in failure for failure in failures)


def test_missing_every_derived_file_reports_each(tmp_path: Path) -> None:
    """An entry with no derived files reports every one, not just the first."""
    entry = tmp_path / "papers" / "Empty"
    (entry / "source").mkdir(parents=True)
    (entry / "wiki").mkdir(parents=True)
    failures = verify_research_dir(entry)
    for name in ("index.md", "summary.md", "digest.md", "explainer.md", "questions.md"):
        assert any(name in failure for failure in failures), failures


def test_escaped_pipe_in_table_resolves(tmp_path: Path) -> None:
    """Obsidian escapes the pipe inside a table; the target is still the file."""
    entry = _good_entry(tmp_path)
    index = entry / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "- [[wiki/01-first-claim|First claim]]",
            "| Page | What it covers |\n"
            "| --- | --- |\n"
            "| [[wiki/01-first-claim\\|First claim]] | the first claim |",
        ),
        encoding="utf-8",
    )
    assert verify_research_dir(entry) == []


def test_escaped_pipe_still_catches_a_missing_page(tmp_path: Path) -> None:
    """Stripping the escape must not hide a genuinely absent target."""
    entry = _good_entry(tmp_path)
    index = entry / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "- [[wiki/01-first-claim|First claim]]",
            "| [[wiki/99-absent\\|Absent]] |",
        ),
        encoding="utf-8",
    )
    failures = verify_research_dir(entry)
    assert any("wiki/99-absent" in f for f in failures)
    assert not any("\\" in f for f in failures)


def _with_source_link(entry: Path, link: str) -> Path:
    """Replace the local-copy bullet in index.md with `link`."""
    index = entry / "index.md"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "- [local copy](source/source.md)",
            f"- [local copy]({link})",
        ),
        encoding="utf-8",
    )
    return entry


def test_machine_absolute_link_is_ignored(tmp_path: Path) -> None:
    """A link to the operator's own disk is outside the entry, so it never blocks."""
    entry = _with_source_link(
        _good_entry(tmp_path), "/Users/sergii/Downloads/the-ai-economy-report.pdf"
    )
    assert verify_research_dir(entry) == []


def test_home_shorthand_link_is_ignored(tmp_path: Path) -> None:
    """`~/...` is the same machine-local case written differently."""
    entry = _with_source_link(_good_entry(tmp_path), "~/Downloads/the-ai-economy-report.pdf")
    assert verify_research_dir(entry) == []


def test_entry_relative_root_link_is_still_checked(tmp_path: Path) -> None:
    """Skipping machine paths must not blind the check to real broken links."""
    entry = _with_source_link(_good_entry(tmp_path), "/wiki/99-absent.md")
    assert any("99-absent" in failure for failure in verify_research_dir(entry))
