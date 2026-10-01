"""A request names a topic, a folder name or none, the formats allowed and a
known level, and takes its defaults from settings unless told."""

import pytest
from pydantic import ValidationError

from tutorial.contract import Coder, Format, TutorialRequest, name_problem
from tutorial.settings.load import settings


def test_defaults_come_from_settings() -> None:
    request = TutorialRequest(topic="Grafana from zero")

    assert request.name == ""
    assert [item.value for item in request.formats] == settings.tutorial.formats
    assert request.level == settings.tutorial.level
    assert request.review_rounds == settings.tutorial.review_rounds
    assert request.designer == Coder(
        provider=settings.designer.provider, model=settings.designer.model
    )
    assert request.writer.provider == settings.writer.provider
    assert request.reviewer.model == settings.reviewer.model


def test_a_request_keeps_what_it_is_given() -> None:
    request = TutorialRequest(
        topic="DuckDB",
        name="duckdb",
        formats=[Format.ipynb],
        level="advanced",
        writer=Coder(provider="claude", model="sonnet"),
    )

    assert (request.name, request.formats, request.level) == ("duckdb", [Format.ipynb], "advanced")
    assert request.writer == Coder(provider="claude", model="sonnet")


@pytest.mark.parametrize("topic", ["", "   "])
def test_a_topic_is_required(topic: str) -> None:
    with pytest.raises(ValidationError, match="topic"):
        TutorialRequest(topic=topic)


@pytest.mark.parametrize("name", ["Has Space", "a/b", "..", ".hidden", "UPPER", "-dash"])
def test_a_name_is_one_plain_folder(name: str) -> None:
    with pytest.raises(ValidationError, match="name"):
        TutorialRequest(topic="t", name=name)


@pytest.mark.parametrize("name", ["grafana", "competitive_programming", "neo4j-basics", "x2"])
def test_plain_names_pass(name: str) -> None:
    assert name_problem(name) == ""
    assert TutorialRequest(topic="t", name=name).name == name


@pytest.mark.parametrize("formats", [[], ["md", "md"], ["pdf"]])
def test_formats_are_a_non_empty_set_of_known_ones(formats: list[str]) -> None:
    with pytest.raises(ValidationError, match="formats"):
        TutorialRequest.model_validate({"topic": "t", "formats": formats})


def test_an_unknown_level_is_refused() -> None:
    with pytest.raises(ValidationError, match="level"):
        TutorialRequest(topic="t", level="guru")


def test_review_rounds_cannot_be_negative() -> None:
    with pytest.raises(ValidationError, match="review_rounds"):
        TutorialRequest(topic="t", review_rounds=-1)
