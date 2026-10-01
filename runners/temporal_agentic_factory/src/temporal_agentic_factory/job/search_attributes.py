"""The search attributes the job workflow carries: indexed by the server, so
the UI shows them as columns and filters (`Provider = 'claude' AND Outcome =
'failed'`). Registered once per server with `factory attributes`."""

from temporalio.api.enums.v1 import IndexedValueType
from temporalio.api.operatorservice.v1 import (
    AddSearchAttributesRequest,
    ListSearchAttributesRequest,
)
from temporalio.client import Client
from temporalio.common import (
    SearchAttributeKey,
    SearchAttributePair,
    SearchAttributeUpdate,
    TypedSearchAttributes,
)

from agentic_factory.job.contract import Job
from agentic_factory.job.outcome import JobOutcome

PROVIDER = SearchAttributeKey.for_keyword("Provider")
MODEL = SearchAttributeKey.for_keyword("Model")
WORKDIR = SearchAttributeKey.for_keyword("Workdir")
RUNNER = SearchAttributeKey.for_keyword("Runner")
OUTCOME = SearchAttributeKey.for_keyword("Outcome")
VERDICT = SearchAttributeKey.for_keyword("Verdict")
KEYS = [PROVIDER, MODEL, WORKDIR, RUNNER, OUTCOME, VERDICT]


def at_start(job: Job) -> TypedSearchAttributes:
    """What is known when the workflow starts: who runs the job and where."""
    return TypedSearchAttributes(
        [
            SearchAttributePair(PROVIDER, job.provider),
            SearchAttributePair(MODEL, job.model),
            SearchAttributePair(WORKDIR, job.workdir),
        ]
    )


def after_job(runner: str) -> list[SearchAttributeUpdate[str]]:
    """Which runner process ran the job's last try."""
    return [RUNNER.value_set(runner)]


def at_end(outcome: JobOutcome) -> list[SearchAttributeUpdate[str]]:
    """How the job ended (`done` or `failed`) and the report's verdict, if any."""
    verdict = outcome.report.verdict.value if outcome.report else ""
    return [
        OUTCOME.value_set("done" if outcome.result else "failed"),
        VERDICT.value_set(verdict),
    ]


async def register(client: Client, namespace: str) -> list[str]:
    """Every key of `KEYS` the server does not have yet, added as a Keyword;
    returns the names added. Adding is not idempotent on the server, so the
    existing ones are listed first."""
    registered = await _registered(client, namespace)
    missing = [key.name for key in KEYS if key.name not in registered]
    if missing:
        await add(client, namespace, missing)
    return missing


async def add(client: Client, namespace: str, names: list[str]) -> None:
    """`names` added to the server as Keyword attributes. Fails when one exists."""
    await client.operator_service.add_search_attributes(
        AddSearchAttributesRequest(
            namespace=namespace,
            search_attributes=dict.fromkeys(names, IndexedValueType.INDEXED_VALUE_TYPE_KEYWORD),
        )
    )


async def _registered(client: Client, namespace: str) -> set[str]:
    listed = await client.operator_service.list_search_attributes(
        ListSearchAttributesRequest(namespace=namespace)
    )
    return set(listed.custom_attributes) | set(listed.system_attributes)
