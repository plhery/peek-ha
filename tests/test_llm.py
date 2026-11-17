"""Tests for the Assist tool."""

import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.components.llm import async_get_tools as async_get_all_tools
from homeassistant.core import Context, HomeAssistant
from homeassistant.helpers import llm
from homeassistant.setup import async_setup_component

from custom_components.peek.llm import PROMPT, ListParcelsTool, async_get_tools

from .common import BOOTS, PARCELS_URL, answer

CONTEXT = llm.LLMContext(platform="test", context=Context(), language="en", assistant="conversation", device_id=None)


@pytest.fixture
async def exposed(hass: HomeAssistant, setup_integration: MockConfigEntry) -> MockConfigEntry:
    """Peek set up, with its "On the way" sensor exposed to Assist."""
    assert await async_setup_component(hass, "homeassistant", {})
    async_expose_entity(hass, "conversation", "sensor.peek_on_the_way", True)
    return setup_integration


@pytest.mark.usefixtures("exposed")
async def test_offered_through_assist(hass: HomeAssistant) -> None:
    """Home Assistant's LLM component finds the tool and its prompt."""
    assert await async_setup_component(hass, "llm", {})
    tools = await async_get_all_tools(hass, CONTEXT, llm.LLM_API_ASSIST)
    assert "peek__list_parcels" in [tool.name for tool in tools.tools]
    assert PROMPT in tools.prompt


async def test_only_when_exposed(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    """Without an exposed Peek entity, nor for another API, nor without Peek, the tool isn't offered."""
    assert await async_setup_component(hass, "homeassistant", {})
    assert async_get_tools(hass, CONTEXT, llm.LLM_API_ASSIST) is None
    async_expose_entity(hass, "conversation", "calendar.peek_deliveries", True)
    assert async_get_tools(hass, CONTEXT, "another_api") is None
    assert async_get_tools(hass, CONTEXT, llm.LLM_API_ASSIST) is not None
    await hass.config_entries.async_unload(setup_integration.entry_id)
    assert async_get_tools(hass, CONTEXT, llm.LLM_API_ASSIST) is None


async def test_call(hass: HomeAssistant, exposed: MockConfigEntry, mock_parcels: AiohttpClientMocker) -> None:
    """The tool reads Peek with the model's arguments."""
    mock_parcels.get(PARCELS_URL, params={"status": "today", "limit": "5"}, json=answer(BOOTS, total=1))
    tool = async_get_tools(hass, CONTEXT, llm.LLM_API_ASSIST).tools[0]
    result = await tool.async_call(
        hass, llm.ToolInput(tool_name=tool.name, tool_args={"status": "today", "limit": 5}), CONTEXT
    )
    assert not result.error
    assert result.data["total"] == 1
    assert result.data["parcels"][0]["name"] == "Hiking boots"


async def test_call_fails(hass: HomeAssistant, exposed: MockConfigEntry, mock_parcels: AiohttpClientMocker) -> None:
    """Peek failing is an error result the model can read, not an exception."""
    mock_parcels.get(PARCELS_URL, params={"status": "all"}, status=503)
    tool = ListParcelsTool(exposed)
    result = await tool.async_call(hass, llm.ToolInput(tool_name=tool.name, tool_args={"status": "all"}), CONTEXT)
    assert result.error
    assert "error" in result.data


async def test_arguments_checked(hass: HomeAssistant, exposed: MockConfigEntry) -> None:
    """Arguments outside Peek's range are refused before asking Peek."""
    tool = ListParcelsTool(exposed)
    with pytest.raises(probatio.Invalid):
        await tool.async_call(hass, llm.ToolInput(tool_name=tool.name, tool_args={"limit": 500}), CONTEXT)


def test_schema_for_models() -> None:
    """The parameters convert to the JSON schema models read, with their descriptions."""
    schema = probatio.to_openapi(ListParcelsTool.parameters, custom_serializer=llm.selector_serializer)
    assert set(schema["properties"]) == {"status", "sort", "search", "limit"}
    assert "today" in schema["properties"]["status"]["enum"]
    assert schema["properties"]["limit"]["maximum"] == 50
    assert "description" in schema["properties"]["search"]
