"""What the research workflow passes around: the request that starts it,
the candidates the discover job writes and the ranking marks, the plan the
assign job states, and the result the workflow returns."""

import re
from enum import StrEnum

from factory_settings import vault
from pydantic import BaseModel, Field, field_validator

from research.settings.load import settings

TOPIC_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


def _folder_slug(value: str, field: str) -> str:
    """A folder slug: a name with no path in it and not a dot folder."""
    if not value or "/" in value or value in (".", ".."):
        raise ValueError(f"{field} must be a folder slug, got {value!r}")
    return value


class ResearchRequest(BaseModel):
    """One focus question to research into a folder of digests."""

    topics: list[str] = Field(description="Sub-topic slugs the sources are assigned to.")
    focus: str = Field(description="What question the research must answer, for whom.")
    target: str = Field(description="Folder slug under <root>/<topic>/research/.")
    topic: str = Field(description="snake_case research topic folder; must exist.")
    root: str = Field(
        default_factory=lambda: str(vault.research_topics_dir()),
        description="Absolute research_topics root this run lands under.",
    )
    n_sources: int = Field(
        default_factory=lambda: settings.research.n_sources,
        description="How many sources the shortlist holds.",
    )
    lenses: list[str] = Field(
        default_factory=lambda: settings.research.lenses,
        description="Audiences for the top-level lens views.",
    )
    date_from: str = Field(default="", description="Ignore sources older than this; empty none.")
    kinds: list[str] = Field(
        default=[], description="Restrict to some of paper, article, video, repo, thread."
    )

    @field_validator("topics")
    @classmethod
    def topics_are_slugs(cls, topics: list[str]) -> list[str]:
        """At least one sub-topic, each a name with no path in it."""
        if not topics:
            raise ValueError("topics must hold at least one sub-topic")
        return [_folder_slug(topic, "topics") for topic in topics]

    @field_validator("focus")
    @classmethod
    def focus_is_given(cls, focus: str) -> str:
        """No question, no run."""
        if not focus.strip():
            raise ValueError("focus must be non-empty")
        return focus

    @field_validator("target")
    @classmethod
    def target_is_a_folder(cls, target: str) -> str:
        """The target is one folder, not a path."""
        return _folder_slug(target, "target")

    @field_validator("topic")
    @classmethod
    def topic_is_snake_case(cls, topic: str) -> str:
        """The topic folder is snake_case."""
        if not TOPIC_PATTERN.match(topic):
            raise ValueError(f"topic must be snake_case, got {topic!r}")
        return topic

    @field_validator("root")
    @classmethod
    def root_is_absolute(cls, root: str) -> str:
        """The root, `~` expanded, an absolute path."""
        return vault.chosen_root(root)


class Status(StrEnum):
    """Where a candidate stands: as discovered, then as ranked."""

    candidate = "candidate"
    in_kb = "in_kb"
    shortlist = "shortlist"
    reserve = "reserve"
    rejected = "rejected"


class Scores(BaseModel):
    """What the judge step answered about one candidate."""

    relevance: float = Field(ge=0, le=1, description="How directly it answers the focus.")
    kind: str = Field(description="The kind the judge picked.")
    authority: str = Field(description="The authority the judge picked.")


class Candidate(BaseModel):
    """One source from discovery to ranking: metadata, then its scores and place."""

    url: str
    title: str
    kind: str
    authors: str
    date: str
    venue: str
    abstract: str
    origin: str = Field(
        default="", description="Matched folder relative to the knowledge folder; empty new."
    )
    status: Status
    scores: Scores | None = Field(default=None, description="Empty until the judge answered.")

    @field_validator("authors", mode="before")
    @classmethod
    def authors_as_one_line(cls, value: object) -> object:
        """A list of names, as coders often write it, joined into `A, B, C`."""
        if isinstance(value, list):
            return ", ".join(str(name) for name in value)
        return value


class Discovered(BaseModel):
    """What the discover job writes to <target_dir>/candidates.json."""

    candidates: list[Candidate]


class DiscoveredPath(BaseModel):
    """What the discover job states: the file is big, only its path is stated."""

    candidates_path: str


class PlannedSource(BaseModel):
    """One shortlisted source: fresh to distill, or linked when it has an origin."""

    key: str
    url: str
    title: str
    kind: str
    subtopic: str
    origin: str = Field(default="", description="Folder in the knowledge base; empty means fresh.")


class Subtopic(BaseModel):
    """One sub-topic with its fresh keys and its in-KB origins."""

    nn: str
    subtopic: str
    title: str
    sources: list[str]
    linked: list[str]


class Lens(BaseModel):
    """One audience for a top-level view."""

    lens: str
    audience: str


class ResearchPlan(BaseModel):
    """What the assign job states: the sources, their sub-topics, the lenses."""

    sources: list[PlannedSource]
    subtopics: list[Subtopic]
    lenses: list[Lens]

    @property
    def fresh(self) -> list[PlannedSource]:
        """The sources to distill, in build order."""
        return [source for source in self.sources if not source.origin]

    @property
    def linked(self) -> list[PlannedSource]:
        """The sources already in the knowledge base."""
        return [source for source in self.sources if source.origin]


class SourceStatus(StrEnum):
    """Whether a distill child run filed its source."""

    succeeded = "succeeded"
    skipped = "skipped"


class SourceOutcome(BaseModel):
    """One fresh source after its distill child run."""

    key: str
    url: str
    title: str
    status: SourceStatus
    path: str = Field(default="", description="Folder the child run filed; empty skipped.")
    reason: str = Field(default="", description="Why a skipped source never landed.")


class IndexPath(BaseModel):
    """What the index job states: the hub index it wrote."""

    index_path: str


class ResearchedTopic(BaseModel):
    """What the workflow returns: where the run landed and what it made."""

    target_dir: str
    index_path: str
    plan: ResearchPlan
    sources: list[SourceOutcome]
    candidates: list[Candidate]
