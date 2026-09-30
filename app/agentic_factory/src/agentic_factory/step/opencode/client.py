import os
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import cast
from uuid import uuid4

import httpx2
from openai import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AsyncOpenAI,
    RateLimitError,
)
from openai.types import CompletionUsage
from openai.types.chat import ChatCompletion, ChatCompletionMessageParam
from openai.types.responses import Response, ResponseFormatTextJSONSchemaConfigParam, ResponseUsage
from openai.types.shared_params import ReasoningEffort, ResponseFormatJSONSchema

from agentic_factory.failure import BadOutput, NetworkError, ProviderError, RateLimited, TimedOut
from agentic_factory.settings.load import settings
from agentic_factory.step.client import Answer, Client
from agentic_factory.step.contract import Step
from agentic_factory.tokens import Tokens

KEY_ENV = "OPENCODE_API_KEY"
SESSION_HEADER = "x-opencode-session"  # required; one id per conversation
SCHEMA_NAME = "output"


class Protocol(StrEnum):
    """Each Go model speaks one wire protocol; see the Endpoints table in the Go docs."""

    CHAT = "chat/completions"
    RESPONSES = "responses"


RESPONSES_MODEL_PREFIXES = ("muse-spark", "grok", "gpt")


def protocol_for(model: str) -> Protocol:
    if model.startswith(RESPONSES_MODEL_PREFIXES):
        return Protocol.RESPONSES
    return Protocol.CHAT


class OpencodeGo(Client):
    """Structured-output steps against the OpenCode Go API, paid by the subscription."""

    default_model = settings.step.opencode.default_model

    def __init__(self, api_key: str, http_client: httpx2.AsyncClient | None = None) -> None:
        self._client = AsyncOpenAI(
            api_key=api_key,
            base_url=settings.step.opencode.base_url,
            default_headers={"User-Agent": settings.step.opencode.user_agent},
            max_retries=0,  # retries are Temporal's job
            http_client=http_client,
        )

    @classmethod
    def from_env(cls) -> "OpencodeGo":
        key = os.environ.get(KEY_ENV, "")
        if not key:
            raise ValueError(f"{KEY_ENV} is not set; see .env.example")
        return cls(key)

    async def complete(self, step: Step) -> Answer:
        """The answer, with the API's errors as the job's failures."""
        try:
            return await self._answer_by_protocol(step)
        except RateLimitError as error:
            raise RateLimited(_resets_at(error)) from None
        except APITimeoutError:
            raise TimedOut(f"{step.model} gave no answer in {step.timeout_sec}s") from None
        except APIConnectionError as error:
            raise NetworkError(str(error)) from None
        except APIStatusError as error:
            raise ProviderError(f"{error.status_code}: {error.message}") from None

    async def _answer_by_protocol(self, step: Step) -> Answer:
        if protocol_for(step.model) is Protocol.RESPONSES:
            return await self._responses(step)
        return await self._chat(step)

    async def _chat(self, step: Step) -> Answer:
        completion = await self._client.chat.completions.create(
            model=step.model,
            messages=_chat_messages(step),
            response_format=_chat_response_format(step),
            reasoning_effort=_effort(step),
            max_tokens=step.max_tokens,
            timeout=step.timeout_sec,
            extra_headers={SESSION_HEADER: str(uuid4())},
        )
        return _answer_from_completion(completion)

    async def _responses(self, step: Step) -> Answer:
        response = await self._client.responses.create(
            model=step.model,
            instructions=step.system_prompt or None,
            input=step.prompt,
            text={"format": _text_format(step)},
            reasoning={"effort": _effort(step)},
            max_output_tokens=step.max_tokens,
            timeout=step.timeout_sec,
            extra_headers={SESSION_HEADER: str(uuid4())},
        )
        return _answer_from_response(response)


def _chat_messages(step: Step) -> list[ChatCompletionMessageParam]:
    messages: list[ChatCompletionMessageParam] = []
    if step.system_prompt:
        messages.append({"role": "system", "content": step.system_prompt})
    messages.append({"role": "user", "content": step.prompt})
    return messages


def _chat_response_format(step: Step) -> ResponseFormatJSONSchema:
    return {
        "type": "json_schema",
        "json_schema": {"name": SCHEMA_NAME, "strict": True, "schema": step.output_schema},
    }


def _answer_from_completion(completion: ChatCompletion) -> Answer:
    choice = completion.choices[0]
    if choice.finish_reason != "stop":
        raise BadOutput(f"answer cut off: {choice.finish_reason}")
    return Answer(text=choice.message.content or "", tokens=_chat_tokens(completion.usage))


def _text_format(step: Step) -> ResponseFormatTextJSONSchemaConfigParam:
    return {
        "type": "json_schema",
        "name": SCHEMA_NAME,
        "strict": True,
        "schema": step.output_schema,
    }


def _answer_from_response(response: Response) -> Answer:
    if response.status != "completed":
        reason = response.incomplete_details and response.incomplete_details.reason
        raise BadOutput(f"answer cut off: {reason or response.status}")
    return Answer(text=response.output_text, tokens=_responses_tokens(response.usage))


def _effort(step: Step) -> ReasoningEffort:
    return cast(ReasoningEffort, step.reasoning.value)


def _chat_tokens(usage: CompletionUsage | None) -> Tokens:
    if usage is None:
        return Tokens()
    details = usage.prompt_tokens_details
    return Tokens(
        input=usage.prompt_tokens,
        output=usage.completion_tokens,
        cache_read=(details and details.cached_tokens) or 0,
    )


def _responses_tokens(usage: ResponseUsage | None) -> Tokens:
    if usage is None:
        return Tokens()
    return Tokens(
        input=usage.input_tokens,
        output=usage.output_tokens,
        cache_read=usage.input_tokens_details.cached_tokens,
    )


def _resets_at(error: RateLimitError) -> datetime:
    retry_after = error.response.headers.get("retry-after", "")
    default = settings.step.opencode.retry_after_default_sec
    seconds = int(retry_after) if retry_after.isdigit() else default
    return datetime.now(tz=UTC) + timedelta(seconds=seconds)
