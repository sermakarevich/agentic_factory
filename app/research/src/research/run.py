"""One research run: where it lands, and the state the workflow grows as the
jobs finish, with the questions the prompts ask of it."""

from pathlib import Path
from typing import Any

from factory_settings import vault
from pydantic import BaseModel, Field

from research.contract import (
    Candidate,
    PlannedSource,
    ResearchedTopic,
    ResearchPlan,
    ResearchRequest,
    SourceOutcome,
    SourceStatus,
    Status,
    Subtopic,
)


def target_dir(request: ResearchRequest) -> Path:
    """research_topics/<topic>/research/<target>: the run's folder."""
    return vault.research_topics_dir() / request.topic / "research" / request.target


def ensured_target_dir(request: ResearchRequest) -> Path:
    """The run's folder, made, ready for the jobs to write into."""
    folder = target_dir(request)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


class Research(BaseModel):
    """The run so far: the request and its folder, then the candidates,
    the plan and the distilled sources as each stage fills them in."""

    request: ResearchRequest
    target_dir: str
    candidates: list[Candidate] = []
    plan: ResearchPlan = Field(
        default_factory=lambda: ResearchPlan(sources=[], subtopics=[], lenses=[])
    )
    sources: list[SourceOutcome] = []

    @property
    def topic_page(self) -> Path:
        """research_topics/<topic>/<topic>.md: the page that registers the run."""
        return vault.research_topics_dir() / self.request.topic / f"{self.request.topic}.md"

    @property
    def source_count(self) -> int:
        """How many sources the run covers: the filed fresh ones and the linked ones."""
        filed = [item for item in self.sources if item.status == SourceStatus.succeeded]
        return len(filed) + len(self.plan.linked)

    @property
    def date_range(self) -> str:
        """The candidates' dates as `YYYY-MM to YYYY-MM`, or `undated`."""
        dates = sorted({item.date for item in self.candidates if item.date})
        if not dates:
            return "undated"
        if len(dates) == 1:
            return dates[0][:7]
        return f"{dates[0][:7]} to {dates[-1][:7]}"

    def known(self) -> list[Candidate]:
        """The candidates already in the knowledge base: never scored."""
        return [item for item in self.candidates if item.status == Status.in_kb]

    def to_judge(self) -> list[Candidate]:
        """The candidates the judge has to score: those not already in the knowledge base."""
        return [item for item in self.candidates if item.status != Status.in_kb]

    def ranked_rows(self) -> dict[str, list[dict[str, Any]]]:
        """The shortlist and reserve rows as plain dicts: what the assign job reads."""
        return {
            status.value: [item.model_dump() for item in self.candidates if item.status == status]
            for status in (Status.shortlist, Status.reserve)
        }

    def fresh_of(self, subtopic: Subtopic) -> list[PlannedSource]:
        """The fresh sources of one sub-topic, in build order."""
        return [source for source in self.plan.fresh if source.key in subtopic.sources]

    def outcomes_of(self, subtopic: Subtopic) -> list[SourceOutcome]:
        """The distill outcomes of one sub-topic's fresh sources, in build order."""
        return [item for item in self.sources if item.key in subtopic.sources]

    def researched(self, index_path: str) -> ResearchedTopic:
        """What the workflow returns: where the run landed and what it made."""
        return ResearchedTopic(
            target_dir=self.target_dir,
            index_path=index_path,
            plan=self.plan,
            sources=self.sources,
            candidates=self.candidates,
        )
