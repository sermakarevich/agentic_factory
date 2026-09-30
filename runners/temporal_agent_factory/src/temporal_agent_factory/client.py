from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from temporal_agent_factory.settings.load import settings


async def connect() -> Client:
    """A client on the configured server. Pydantic models travel as they are."""
    return await Client.connect(
        settings.temporal.address,
        namespace=settings.temporal.namespace,
        data_converter=pydantic_data_converter,
    )
