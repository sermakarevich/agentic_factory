"""chunking.BOILERPLATE_WIKI_SUBSTRINGS: paper sections are not README boilerplate."""

from distill.chunking import BOILERPLATE_WIKI_SUBSTRINGS


def test_paper_contributions_stem_is_not_boilerplate() -> None:
    stem = "01-introduction-and-contributions"
    assert not any(banned in stem for banned in BOILERPLATE_WIKI_SUBSTRINGS)
    assert any(banned in "05-contributing" for banned in BOILERPLATE_WIKI_SUBSTRINGS)
