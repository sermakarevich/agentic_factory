from distill.boilerplate import (
    BOILERPLATE_WIKI_SUBSTRINGS,
    is_boilerplate_heading,
    strip_boilerplate,
)


def test_paper_contributions_stem_is_not_boilerplate() -> None:
    stem = "01-introduction-and-contributions"
    assert not any(banned in stem for banned in BOILERPLATE_WIKI_SUBSTRINGS)
    assert any(banned in "05-contributing" for banned in BOILERPLATE_WIKI_SUBSTRINGS)


def test_boilerplate_headings_are_named() -> None:
    assert is_boilerplate_heading("Sponsor")
    assert is_boilerplate_heading("## Star History")
    assert is_boilerplate_heading("Code of Conduct")
    assert not is_boilerplate_heading("Related work")
    assert not is_boilerplate_heading("Introduction")


def test_strip_boilerplate_drops_sponsor_and_license() -> None:
    text = strip_boilerplate(
        "# Widgets\n\nA widget factory.\n\n## Sponsor\n\nThanks.\n\n## License\n\nMIT.\n"
    )
    assert "widget factory" in text
    assert "Sponsor" not in text and "MIT" not in text


def test_strip_boilerplate_keeps_the_substance_in_order() -> None:
    text = strip_boilerplate("# A\n\nFirst.\n\n# B\n\nSecond.\n")
    assert text.index("First.") < text.index("Second.")


def test_badges_only_text_is_dropped() -> None:
    badges = "[![x](https://shields.io/a)](https://example.com)\n"
    assert strip_boilerplate(badges) == ""
