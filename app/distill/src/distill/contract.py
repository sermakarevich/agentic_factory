"""What the distill workflow passes around: the request that starts it,
the fetched source the jobs read, the plan the first job states, and the
final folder the filing job states."""

from enum import StrEnum

from pydantic import BaseModel, Field

from distill.settings.load import settings


class DistillRequest(BaseModel):
    """One source to turn into a knowledge-base entry."""

    url: str = Field(description="Source URL, or a local .pdf/.md/.txt path.")
    chunk_chars: int = Field(
        default_factory=lambda: settings.chunking.chars_default,
        description="Target characters per chunk, kept within the chunking bounds.",
    )
    topic: str = Field(
        default="",
        description="snake_case research topic; when set the entry is filed under it.",
    )
    research_target: str = Field(
        default="", description="Free text recorded as a Research-Target provenance line."
    )


class EntryType(StrEnum):
    """What kind of entry a source becomes; named in the summary's metadata line."""

    video = "Video"
    paper = "Paper"
    article = "Article"
    codebase = "Codebase"


class FetchedChunk(BaseModel):
    """One piece of the source, written to its own file for one wiki job."""

    index: int
    slug: str
    title: str
    path: str
    chars: int


class FetchedSource(BaseModel):
    """What the fetch step made: the source on disk with its provenance, and
    the chunks the wiki jobs write pages for."""

    work_dir: str
    source_md: str
    source_pdf: str = Field(default="", description="Empty when no PDF was downloaded.")
    repo_dir: str = Field(default="", description="Empty when the source is not a clone.")
    title: str
    kind: str
    type: EntryType
    fetched_at: str
    chunks: list[FetchedChunk]


class EntryPlan(BaseModel):
    """What the plan job states: where the entry lives and what it is called."""

    research_dir: str = Field(description="Absolute path of the entry folder.")
    slug: str = Field(description="The folder's PascalName.")
    title: str
    type: EntryType


class FiledEntry(BaseModel):
    """What the file job states: the entry's final folder under its topic."""

    path: str
