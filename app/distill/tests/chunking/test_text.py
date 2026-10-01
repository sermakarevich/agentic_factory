from distill.chunking.text import chunk_text


def _long(line: str, repeats: int = 40) -> str:
    return (line + " ") * repeats


def test_headings_become_chunks() -> None:
    text = f"# Hello\n\n{_long('Welcome.', 80)}\n\n## Install\n\n{_long('Install it.', 80)}\n"
    chunks = chunk_text(text, 800)
    assert [chunk.title for chunk in chunks] == ["Hello", "Install"]


def test_text_without_headings_splits_on_blank_lines() -> None:
    text = f"{_long('First paragraph here.')}\n\n{_long('Second paragraph here.')}\n"
    chunks = chunk_text(text, 100)
    assert len(chunks) >= 2


def test_boilerplate_only_yields_no_chunks() -> None:
    assert chunk_text("## Sponsor\n\n" + _long("Thanks to our sponsors.", 30), 2000) == []


def test_chunks_are_numbered_and_slugged() -> None:
    text = f"# Hello-World!\n\n{_long('Welcome.')}\n"
    (chunk,) = chunk_text(text, 60000)
    assert (chunk.index, chunk.slug, chunk.title) == (1, "01-hello-world", "Hello-World!")


def test_many_sections_merge_down_to_the_cap() -> None:
    sections = "".join(f"# Part {i}\n\n{_long('Content here.')}\n\n" for i in range(40))
    chunks = chunk_text(sections, 2000)
    assert len(chunks) <= 24
