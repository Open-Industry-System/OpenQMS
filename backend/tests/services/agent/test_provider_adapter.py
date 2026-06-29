import pytest

from app.services.agent import provider_adapter
from app.services.agent.provider_adapter import ProviderClient, tools_schema_for


@pytest.mark.asyncio
async def test_build_client_returns_provider_client(db):
    pc = await provider_adapter.build_client(db)
    assert pc.provider in ("openai", "anthropic")
    assert pc.client is not None
    assert pc.model  # non-empty model name


def test_tools_schema_shape_openai():
    from types import SimpleNamespace

    spec = SimpleNamespace(
        name="echo_factory",
        description="d",
        param_schema={"type": "object", "properties": {}},
    )
    pc = ProviderClient(provider="openai", client=None, model="m")
    schema = tools_schema_for(pc, [spec])
    assert schema[0]["type"] == "function"
    assert schema[0]["function"]["name"] == "echo_factory"


def test_tools_schema_shape_anthropic():
    from types import SimpleNamespace

    spec = SimpleNamespace(
        name="echo_factory",
        description="d",
        param_schema={"type": "object", "properties": {}},
    )
    pc = ProviderClient(provider="anthropic", client=None, model="m")
    schema = tools_schema_for(pc, [spec])
    assert schema[0]["name"] == "echo_factory"
    assert "input_schema" in schema[0]
