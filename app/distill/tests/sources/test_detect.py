import pytest

from distill.contract import SourceKind
from distill.sources import SourceError, detect


@pytest.mark.parametrize(
    ("url", "kind"),
    [
        ("https://github.com/acme/widgets", SourceKind.repo),
        ("https://github.com/acme/widgets/", SourceKind.repo),
        ("https://github.com/acme/widgets/tree/main/src", SourceKind.repo),
        ("https://www.github.com/acme/widgets", SourceKind.repo),
        ("https://github.com/acme/widgets/blob/main/README.md", SourceKind.article),
        ("https://github.com/acme/widgets/issues/12", SourceKind.article),
        ("https://github.com/acme", SourceKind.article),
        ("https://gist.github.com/acme/abc123", SourceKind.article),
        ("https://acme.github.io/widgets/", SourceKind.article),
        ("https://example.com/some/article", SourceKind.article),
        ("https://www.youtube.com/watch?v=abc", SourceKind.youtube),
        ("https://youtu.be/abc", SourceKind.youtube),
        ("https://x.com/user/status/123", SourceKind.x),
        ("https://arxiv.org/abs/2601.00001", SourceKind.pdf),
        ("https://example.com/paper.pdf", SourceKind.pdf),
    ],
)
def test_detect_routes_by_host_and_path(url: str, kind: SourceKind) -> None:
    assert detect.detect(url) is kind


@pytest.mark.parametrize(
    ("path", "kind"),
    [
        ("/tmp/notes/paper.pdf", SourceKind.pdf),
        ("/tmp/notes/paper.md", SourceKind.article),
        ("~/notes/paper.txt", SourceKind.article),
        ("file:///tmp/notes/paper.md", SourceKind.article),
    ],
)
def test_detect_routes_local_files_by_suffix(path: str, kind: SourceKind) -> None:
    assert detect.detect(path) is kind


def test_detect_rejects_junk_suffixes_and_bare_words() -> None:
    with pytest.raises(SourceError, match="local files must be"):
        detect.detect("/tmp/notes/paper.docx")
    with pytest.raises(SourceError, match="http"):
        detect.detect("not a url")


def test_repo_root_names_landing_pages_only() -> None:
    assert detect.repo_root("https://github.com/octo/Hello-World") == ("octo", "Hello-World")
    assert detect.repo_root("https://github.com/octo/Hello-World/tree/main") is None
    assert detect.repo_root("https://github.com/octo") is None
    assert detect.repo_root("https://example.com/octo/Hello-World") is None
