import json
from pathlib import Path

import httpx2
import pytest
from pydantic import BaseModel

from agentic_factory.failure import BadOutput, ProviderError, RateLimited
from agentic_factory.settings.load import settings
from agentic_factory.step.contract import Step
from agentic_factory.step.providers.opencode.client import SESSION_HEADER, OpencodeGo

FIXTURES = Path(__file__).parent / "fixtures"


class Report(BaseModel):
    status: str
    summary: str


def step(**overrides: object) -> Step:
    base = {
        "prompt": "Report.",
        "output_schema": Report.model_json_schema(),
        "model": "deepseek-v4-flash",
    }
    return Step.model_validate({**base, **overrides})


class FakeGo:
    """Answers every request with one canned body and remembers what was asked."""

    def __init__(self, status: int = 200, body: str | dict[str, object] = "") -> None:
        self.requests: list[httpx2.Request] = []
        self._status = status
        self._body = json.dumps(body) if isinstance(body, dict) else body

    def handle(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        return httpx2.Response(self._status, content=self._body, headers=self._headers)

    _headers: dict[str, str] = {"content-type": "application/json"}

    def client(self) -> OpencodeGo:
        transport = httpx2.MockTransport(self.handle)
        return OpencodeGo("k", http_client=httpx2.AsyncClient(transport=transport))

    def sent(self) -> dict[str, object]:
        body: dict[str, object] = json.loads(self.requests[-1].content)
        return body


async def test_chat_model_goes_to_chat_completions_with_the_schema() -> None:
    go = FakeGo(body=(FIXTURES / "chat.json").read_text())
    result = await go.client().complete(step(system_prompt="You write reports."))

    request = go.requests[0]
    assert request.url.path.endswith("/zen/go/v1/chat/completions")
    assert request.headers["user-agent"] == settings.step.opencode.user_agent
    assert request.headers[SESSION_HEADER]
    sent = go.sent()
    assert sent["model"] == "deepseek-v4-flash"
    assert sent["messages"] == [
        {"role": "system", "content": "You write reports."},
        {"role": "user", "content": "Report."},
    ]
    assert sent["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "output", "strict": True, "schema": Report.model_json_schema()},
    }
    assert sent["reasoning_effort"] == "high"
    assert json.loads(result.text) == {
        "status": "done",
        "summary": "Job executed successfully and completed.",
    }
    assert (result.tokens.input, result.tokens.output) == (20, 636)


async def test_responses_model_goes_to_responses_with_the_schema() -> None:
    go = FakeGo(body=(FIXTURES / "responses.json").read_text())
    result = await go.client().complete(step(model="muse-spark-1.3-contributor"))

    assert go.requests[0].url.path.endswith("/zen/go/v1/responses")
    sent = go.sent()
    assert sent["input"] == "Report."
    assert sent["text"] == {
        "format": {
            "type": "json_schema",
            "name": "output",
            "strict": True,
            "schema": Report.model_json_schema(),
        }
    }
    assert sent["reasoning"] == {"effort": "high"}
    assert json.loads(result.text) == {
        "status": "done",
        "summary": "Job wrote hello.txt and said done.",
    }
    assert (result.tokens.input, result.tokens.output) == (83, 263)


def chat_body(content: str, finish_reason: str = "stop") -> dict[str, object]:
    body: dict[str, object] = json.loads((FIXTURES / "chat.json").read_text())
    choice = body["choices"][0]  # type: ignore[index]
    choice["message"]["content"] = content
    choice["finish_reason"] = finish_reason
    return body


async def test_cut_off_answer_is_bad_output() -> None:
    with pytest.raises(BadOutput, match="cut off: length"):
        await FakeGo(body=chat_body("{", "length")).client().complete(step())


async def test_provider_errors_map_to_failures() -> None:
    error = {"error": {"type": "server_error", "message": "Model is unavailable."}}
    with pytest.raises(ProviderError, match="400: .*Model is unavailable"):
        await FakeGo(status=400, body=error).client().complete(step())
    with pytest.raises(RateLimited):
        await FakeGo(status=429, body=error).client().complete(step())
