import os
from datetime import UTC, datetime, timedelta

import httpx2
from typesafe_sdk import Answer as WireAnswer
from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    ChoiceAnswer,
    Noul,
    NoulAnswer,
    RetryPolicy,
    Score,
    ScoreAnswer,
    TypeSafeAPIConnectionError,
    TypeSafeAPIError,
    TypeSafeAPITimeoutError,
    TypeSafeError,
    TypeSafeRateLimitError,
)
from typesafe_sdk import Question as WireQuestion
from typesafe_sdk import Usage as WireUsage

from agentic_factory.failure import NetworkError, ProviderError, RateLimited, TimedOut
from agentic_factory.settings.load import settings
from agentic_factory.step.judge import answer as ours
from agentic_factory.step.judge import question
from agentic_factory.step.judge.client import JudgeClient, JudgeReply
from agentic_factory.step.judge.contract import Judgment
from agentic_factory.tokens import Tokens

KEY_ENV = "TYPESAFE_API_KEY"
QUESTION_KEY = "question"  # how a question with a focus is sent: {"question": ..., "focus": ...}
FOCUS_KEY = "focus"


class TypeSafeJev(JudgeClient):
    """Judgments against the TypeSafe API, whose jev models answer typed
    questions with probabilities. Paid per input token."""

    default_model = settings.step.judge.typesafe.default_model

    def __init__(self, api_key: str, http_client: httpx2.AsyncClient | None = None) -> None:
        self._client = AsyncTypeSafeClient(
            api_key=api_key,
            retry=RetryPolicy(max_retries=0),  # retries are Temporal's job
            http_client=http_client,
        )

    @classmethod
    def from_env(cls) -> "TypeSafeJev":
        key = os.environ.get(KEY_ENV, "")
        if not key:
            raise ValueError(f"{KEY_ENV} is not set; see .env.example")
        return cls(key)

    async def answer(self, judgment: Judgment) -> JudgeReply:
        """The reply, with the API's errors as the job's failures."""
        try:
            response = await self._client.system_one(
                judgment.state,
                _wire_questions(judgment),
                model=judgment.model,
                timeout=judgment.timeout_sec,
            )
        except TypeSafeRateLimitError as error:
            raise RateLimited(_resets_at(error)) from None
        except TypeSafeAPITimeoutError:
            raise TimedOut(f"{judgment.model} gave no answer in {judgment.timeout_sec}s") from None
        except TypeSafeAPIConnectionError as error:
            raise NetworkError(str(error)) from None
        except TypeSafeAPIError as error:
            raise ProviderError(f"{error.status}: {error}") from None
        except TypeSafeError as error:
            raise ProviderError(str(error)) from None
        return JudgeReply(
            answers={name: _our_answer(a) for name, a in response.answers.items()},
            tokens=_tokens(response.usage),
            cost_usd=_cost_usd(response.usage),
        )


def _wire_questions(judgment: Judgment) -> dict[str, WireQuestion]:
    return {name: _wire_question(q) for name, q in judgment.questions.items()}


def _wire_question(q: question.Choice | question.Score | question.Check) -> WireQuestion:
    """Our question as the SDK's: choice and score map one to one, a check is a noul."""
    instructions = _instructions(q.question, q.focus)
    if isinstance(q, question.Choice):
        return Choice(instructions=instructions, criteria=q.options)
    if isinstance(q, question.Score):
        return Score(instructions=instructions, criteria=q.levels)
    return Noul(instructions=instructions, criteria={"true": q.yes or None, "false": q.no or None})


def _instructions(text: str, focus: str) -> str | dict[str, str]:
    return {QUESTION_KEY: text, FOCUS_KEY: focus} if focus else text


def _our_answer(a: WireAnswer) -> ours.ChoiceAnswer | ours.ScoreAnswer | ours.CheckAnswer:
    if isinstance(a, ChoiceAnswer):
        return ours.ChoiceAnswer(
            choice=a.choice, confidence=a.confidence, probabilities=a.probabilities
        )
    if isinstance(a, ScoreAnswer):
        return ours.ScoreAnswer(
            score=a.score,
            confidence=a.confidence,
            probabilities=a.probabilities,
            legend=dict(a.legend),
        )
    assert isinstance(a, NoulAnswer)
    return ours.CheckAnswer(yes=a.noul)


def _tokens(usage: WireUsage) -> Tokens:
    return Tokens(input=_count(usage.input_tokens), output=_count(usage.output_tokens))


def _count(value: object) -> int:
    """A usage field the API may leave out; unset or null counts as zero."""
    return value if isinstance(value, int) else 0


def _cost_usd(usage: WireUsage) -> float:
    """jev bills input tokens only, at the price in settings."""
    price = settings.step.judge.typesafe.price_per_m_input_usd
    return round(_count(usage.input_tokens) / 1_000_000 * price, 6)


def _resets_at(error: TypeSafeRateLimitError) -> datetime:
    default_ms = settings.step.judge.typesafe.retry_after_default_sec * 1000
    wait_ms = error.retry_after_ms if error.retry_after_ms is not None else default_ms
    return datetime.now(tz=UTC) + timedelta(milliseconds=wait_ms)
