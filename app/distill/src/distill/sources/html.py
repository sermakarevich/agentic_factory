import html
import re
from html.parser import HTMLParser

BLOCK_TAGS = frozenset(
    {"p", "div", "br", "li", "ul", "ol", "tr", "table", "section", "article", "blockquote", "pre"}
)
HEADING_TAGS = {"h1": "#", "h2": "##", "h3": "###", "h4": "####"}
SKIP_TAGS = frozenset({"script", "style", "noscript", "nav", "footer", "header", "aside", "svg"})


class MarkdownExtractor(HTMLParser):
    """Visible page text with headings kept as markdown and block breaks kept."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._parts: list[str] = []
        self._heading: str | None = None
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in SKIP_TAGS:
            self._skip += 1
        elif tag == "title":
            self._in_title = True
        elif tag in HEADING_TAGS and self._skip == 0:
            self._heading = HEADING_TAGS[tag]
            self._parts.append(f"\n\n{self._heading} ")
        elif tag in BLOCK_TAGS and self._skip == 0:
            self._parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in SKIP_TAGS:
            self._skip = max(0, self._skip - 1)
        elif tag == "title":
            self._in_title = False
        elif tag in HEADING_TAGS:
            self._heading = None
            self._parts.append("\n\n")
        elif tag in BLOCK_TAGS:
            self._parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._skip == 0 and data.strip():
            self._parts.append(re.sub(r"\s+", " ", data) if self._heading else data)

    def text(self) -> str:
        joined = "".join(self._parts)
        joined = re.sub(r"[ \t]+\n", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        return html.unescape(joined).strip()


class SubtreeExtractor(HTMLParser):
    """Raw inner HTML of the `#readme` element, else the first `article` element."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.title = ""
        self._in_title = False
        self._capture: list[str] | None = None
        self._capture_tag = ""
        self._capture_readme = False
        self._depth = 0
        self.readme: list[str] | None = None
        self.article: list[str] | None = None

    def subtree(self) -> str | None:
        """The preferred captured subtree, including a truncated trailing one."""
        if self.readme is not None:
            return "".join(self.readme)
        if self.article is not None:
            return "".join(self.article)
        if self._capture is not None:
            return "".join(self._capture)
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "title" and self._capture is None:
            self._in_title = True
            return
        if self._capture is not None:
            self._capture.append(self.get_starttag_text() or "")
            if tag == self._capture_tag:
                self._depth += 1
            return
        if dict(attrs).get("id") == "readme":
            self._start_capture(tag, is_readme=True)
        elif tag == "article" and self.article is None and self.readme is None:
            self._start_capture(tag, is_readme=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._capture is not None:
            self._capture.append(self.get_starttag_text() or "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._in_title:
            self._in_title = False
            return
        if self._capture is None:
            return
        self._capture.append(f"</{tag}>")
        if tag == self._capture_tag:
            self._depth -= 1
            if self._depth <= 0:
                self._finish_capture()

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title += data
        if self._capture is not None:
            self._capture.append(data)

    def handle_entityref(self, name: str) -> None:
        if self._capture is not None:
            self._capture.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        if self._capture is not None:
            self._capture.append(f"&#{name};")

    def _start_capture(self, tag: str, *, is_readme: bool) -> None:
        self._capture = [self.get_starttag_text() or ""]
        self._capture_tag = tag
        self._capture_readme = is_readme
        self._depth = 1

    def _finish_capture(self) -> None:
        if self._capture_readme:
            self.readme = self._capture
        else:
            self.article = self._capture
        self._capture = None
        self._capture_tag = ""
        self._depth = 0
