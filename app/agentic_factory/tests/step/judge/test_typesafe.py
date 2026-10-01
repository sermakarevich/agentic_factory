import json

import httpx2
import pytest

from agentic_factory.failure import NetworkError, ProviderError, RateLimited
from agentic_factory.settings.load import settings
from agentic_factory.step.judge.contract import Judgment
from agentic_factory.step.judge.typesafe import TypeSafeJev
from agentic_factory.tokens import Tokens

REPLY = {
    "model": "jev-latest",
    "answers": {
        "tone": {
            "type": "choice",
            "choice": "calm",
            "confidence": 0.9,
            "probabilities": {"calm": 0.9, "angry": 0.1},
        },
        "risk": {
            "type": "score",
            "score": 0.7,
            "confidence": 0.6,
            "legend": {"0": "low", "1": "high"},
            "probabilities": {"0": 0.3, "1": 0.7},
        },
        "billing": {"type": "noul", "noul": 0.8},
    },
    "usage": {"billing_units": 1, "input_tokens": 1_000_000, "output_tokens": 0},
}


def judgment() -> Judgment:
    return Judgment.model_validate(
        {
            "state": {"message": "I was charged twice."},
            "model": "jev-latest",
            "questions": {
                "tone": {
                    "kind": "choice",
                    "question": "Tone?",
                    "options": {"calm": "at ease", "angry": None},
                    "focus": "the wording",
                },
                "risk": {"kind": "score", "question": "Churn risk?", "levels": ["low", "high"]},
                "billing": {"kind": "check", "question": "About billing?", "yes": "money"},
            },
        }
    )


class FakeTypeSafe:
    """Answers every request with one canned body and remembers what was asked."""

    def __init__(self, status: int = 200, body: dict[str, object] | None = None) -> None:
        self.requests: list[httpx2.Request] = []
        self._status = status
        self._body = json.dumps(body or REPLY)
        self.headers: dict[str, str] = {"content-type": "application/json"}

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(self._status, content=self._body, headers=self.headers)

    def client(self) -> TypeSafeJev:
        transport = httpx2.MockTransport(self.handle)
        return TypeSafeJev("k", http_client=httpx2.AsyncClient(transport=transport))

    def sent(self) -> dict[str, object]:
        body: dict[str, object] = json.loads(self.requests[-1].content)
        return body


async def test_questions_go_out_as_typesafe_primitives_and_answers_come_back_typed() -> None:
    api = FakeTypeSafe()
    reply = await api.client().answer(judgment())

    sent = api.sent()
    assert api.requests[0].url.path == "/v1/systemone"
    assert sent["state"] == {"message": "I was charged twice."} and sent["model"] == "jev-latest"
    questions = sent["questions"]
    assert isinstance(questions, dict)
    assert questions["tone"] == {
        "type": "choice",
        "instructions": {"question": "Tone?", "focus": "the wording"},
        "criteria": {"calm": "at ease", "angry": None},
    }
    assert questions["risk"] == {
        "type": "score",
        "instructions": "Churn risk?",
        "criteria": ["low", "high"],
    }
    assert questions["billing"] == {
        "type": "noul",
        "instructions": "About billing?",
        "criteria": {"true": "money", "false": None},
    }
    assert reply.answers["tone"].kind == "choice" and reply.answers["billing"].kind == "check"
    score = reply.answers["risk"]
    assert score.kind == "score" and score.probabilities == {0: 0.3, 1: 0.7}
    assert score.legend == {0: "low", 1: "high"}
    assert reply.tokens == Tokens(input=1_000_000)
    assert reply.cost_usd == settings.step.judge.typesafe.price_per_m_input_usd


async def test_api_errors_become_the_jobs_failures() -> None:
    api = FakeTypeSafe(status=429, body={"detail": "slow down"})
    api.headers["retry-after"] = "7"
    with pytest.raises(RateLimited) as limited:
        await api.client().answer(judgment())
    assert limited.value.resets_at is not None

    with pytest.raises(ProviderError, match="500"):
        await FakeTypeSafe(status=500, body={"detail": "boom"}).client().answer(judgment())


async def test_a_dead_connection_is_a_network_error() -> None:
    def refuse(request: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    transport = httpx2.MockTransport(refuse)
    client = TypeSafeJev("k", http_client=httpx2.AsyncClient(transport=transport))
    with pytest.raises(NetworkError):
        await client.answer(judgment())


def test_from_env_needs_the_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="TYPESAFE_API_KEY"):
        TypeSafeJev.from_env()
