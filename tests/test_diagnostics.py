"""Tests for Peek's diagnostics."""

import json

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.peek.diagnostics import async_get_config_entry_diagnostics

from .common import ACTIVE_QUERY, BOOTS, CLIENT_ID, PARCELS_URL, URL


async def test_redacted(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    """Diagnostics keep the parcels' shape, never their names, numbers, places or the tokens."""
    result = await async_get_config_entry_diagnostics(hass, setup_integration)
    text = json.dumps(result)
    for secret in (
        "synthetic-access-token",
        "synthetic-refresh-token",
        BOOTS["id"],
        "Hiking boots",
        "1Z4E7W960398127345",
        "Fjord Outdoor",
        "Zurich",
        "Relais Demo",
        "Out for delivery today",
    ):
        assert secret not in text, secret

    assert result["state"] == "loaded"
    assert result["peek"] == {"url": URL, "client_id": CLIENT_ID, "overridden": False}
    assert result["entry"]["url"] == URL
    assert result["entry"]["token"]["access_token"] == "**REDACTED**"
    assert result["entry"]["token"]["scope"] == "parcels:read parcels:write"
    assert result["coordinator"] == {
        "last_update_success": True,
        "last_exception": None,
        "update_interval": "0:10:00",
    }
    assert result["active_total"] == 6
    first = result["active"][0]
    assert first["carrier"] == "UPS"
    assert first["status"] == "out_for_delivery"
    assert first["expectedDelivery"] == "2026-11-17"
    assert first["name"] == first["trackingNumber"] == first["lastUpdate"]["location"] == "**REDACTED**"
    assert len(result["delivered"]) == 2


async def test_before_the_first_read(
    hass: HomeAssistant, config_entry: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """An entry still waiting for its first read gives what it has."""
    aioclient_mock.get(PARCELS_URL, params=ACTIVE_QUERY, status=502)
    config_entry.add_to_hass(hass)
    assert await async_setup_component(hass, "peek", {})
    await hass.async_block_till_done()
    result = await async_get_config_entry_diagnostics(hass, config_entry)
    assert result["state"] == "setup_retry"
    assert "coordinator" not in result
    assert "synthetic-refresh-token" not in json.dumps(result)
