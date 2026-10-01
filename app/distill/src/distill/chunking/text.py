import re

from distill.boilerplate import HEADING_RE, strip_boilerplate
from distill.chunking import Chunk
from distill.settings.load import settings

_TITLE_RE = re.compile(r"^#{1,3} +(.+?)\s*$", re.MULTILINE)


def chunk_text(text: str, target: int) -> list[Chunk]:
    """Cut text into structure-aligned chunks of roughly `target` characters."""
    body = strip_boilerplate(text)
    if not body:
        return []
    pieces: list[str] = []
    for section in _sections(body):
        pieces.extend(_split_long(section, target))
    packed = _merge_to_cap(_pack(pieces, target), settings.chunking.max_chunks)
    return [
        Chunk(index=i + 1, title=_title_of(piece, i + 1), text=piece.strip())
        for i, piece in enumerate(packed)
    ]


def _sections(text: str) -> list[str]:
    """Split on markdown headings when present, else on blank lines."""
    if len(HEADING_RE.findall(text)) > 1:
        starts = [match.start() for match in HEADING_RE.finditer(text)]
        if starts[0] > 0:
            starts.insert(0, 0)
        pieces = [text[a:b] for a, b in zip(starts, [*starts[1:], len(text)], strict=True)]
        return [piece for piece in pieces if piece.strip()]
    return [piece for piece in re.split(r"\n\s*\n", text) if piece.strip()]


def _pack(pieces: list[str], target: int) -> list[str]:
    """Greedily join neighbouring pieces up to `target` characters each."""
    packed: list[str] = []
    current = ""
    for piece in pieces:
        over = len(current) + len(piece) > target
        if current and over and len(current) >= settings.chunking.min_section_chars:
            packed.append(current)
            current = piece
        else:
            current = f"{current}\n\n{piece}" if current else piece
    if current:
        packed.append(current)
    return packed


def _split_long(piece: str, target: int) -> list[str]:
    """Cut one oversized piece at paragraph breaks so no chunk dwarfs the rest."""
    if len(piece) <= target * 2:
        return [piece]
    paragraphs = [part for part in re.split(r"\n\s*\n", piece) if part.strip()]
    if len(paragraphs) <= 1:
        return [piece]
    return _pack(paragraphs, target)


def _merge_to_cap(pieces: list[str], cap: int) -> list[str]:
    """Merge neighbouring pieces pairwise until at most `cap` remain."""
    while len(pieces) > cap:
        merged: list[str] = []
        for i in range(0, len(pieces), 2):
            merged.append("\n\n".join(pieces[i : i + 2]))
        pieces = merged
    return pieces


def _title_of(text: str, index: int) -> str:
    """Heading of the piece when it has one, else its first words."""
    match = _TITLE_RE.search(text)
    if match is not None:
        return match.group(1).strip("# ").strip().replace("\x00", "")
    words = text.strip().split()
    return " ".join(words[:6]).replace("\x00", "") if words else f"Part {index}"
