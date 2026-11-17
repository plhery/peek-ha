"""Tests for Peek's actions."""

import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.peek.const import DOMAIN

from .common import BOOTS, BOWLS, MCP_URL, PARCELS_URL, answer, tool_answer, tool_refusal

ADDED = [
    {"trackingNumber": "1Z4E7W960398127345", "carrier": "UPS", "outcome": "added", "id": BOOTS["id"]},
    {
        "trackingNumber": "6A18273645095",
        "carrier": "La Poste / Colissimo",
        "outcome": "already_tracked",
        "id": BOWLS["id"],
    },
    {"trackingNumber": "XX0000", "carrier": None, "outcome": "invalid", "reason": "Not a tracking number"},
]


def reads(mock: AiohttpClientMocker) -> int:
    """How many times the parcels were read."""
    return sum(1 for call in mock.mock_calls if str(call[1]).startswith(PARCELS_URL))


def reauth_flows(hass: HomeAssistant) -> int:
    """How many sign-in flows wait for the user."""
    return sum(1 for flow in hass.config_entries.flow.async_progress() if flow["context"]["source"] == SOURCE_REAUTH)


@pytest.mark.usefixtures("setup_integration")
async def test_add_parcels(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """The numbers a text holds are added, each with its outcome, and the parcels are read again."""
    mock_parcels.post(MCP_URL, json=tool_answer({"parcels": ADDED}))
    before = reads(mock_parcels)
    response = await hass.services.async_call(
        DOMAIN,
        "add_parcels",
        {"text": "Your order from Fjord Outdoor shipped: UPS 1Z4E7W960398127345", "name": "Hiking boots"},
        blocking=True,
        return_response=True,
    )
    assert response == {
        "parcels": [
            {
                "tracking_number": "1Z4E7W960398127345",
                "carrier": "UPS",
                "outcome": "added",
                "id": BOOTS["id"],
            },
            {
                "tracking_number": "6A18273645095",
                "carrier": "La Poste / Colissimo",
                "outcome": "already_tracked",
                "id": BOWLS["id"],
            },
            {
                "tracking_number": "XX0000",
                "carrier": None,
                "outcome": "invalid",
                "reason": "Not a tracking number",
            },
        ]
    }
    call = next(call for call in mock_parcels.mock_calls if str(call[1]) == MCP_URL)
    assert call[2]["params"]["arguments"] == {
        "text": "Your order from Fjord Outdoor shipped: UPS 1Z4E7W960398127345",
        "name": "Hiking boots",
    }
    assert reads(mock_parcels) == before + 2


@pytest.mark.usefixtures("setup_integration")
async def test_add_parcels_without_response(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """An automation may add parcels without reading the outcome."""
    mock_parcels.post(MCP_URL, json=tool_answer({"parcels": ADDED}))
    assert await hass.services.async_call(DOMAIN, "add_parcels", {"text": "1Z4E7W960398127345"}, blocking=True) is None


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("service", "data"),
    [
        ("add_parcels", {"text": ""}),
        ("add_parcels", {"text": "x" * 16_001}),
        ("add_parcels", {"text": "1Z4E7W960398127345", "name": "x" * 81}),
        ("archive_parcel", {"parcel": ""}),
        ("get_parcels", {"status": "lost"}),
        ("get_parcels", {"sort": "random"}),
        ("get_parcels", {"limit": 51}),
        ("get_parcels", {"search": "x" * 101}),
    ],
)
async def test_invalid_input(hass: HomeAssistant, mock_parcels: AiohttpClientMocker, service: str, data: dict) -> None:
    """Input Peek would refuse is refused before asking Peek."""
    mock_parcels.clear_requests()
    with pytest.raises(probatio.Invalid):
        await hass.services.async_call(
            DOMAIN, service, data, blocking=True, return_response=service != "archive_parcel"
        )
    assert mock_parcels.call_count == 0


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("kwargs", "key", "reauth"),
    [
        ({"status": 401, "json": {"error": "invalid_token"}}, "auth_failed", 1),
        (
            {"json": tool_refusal("This connection to Peek may see parcels but not add them.", scope=True)},
            "missing_scope",
            1,
        ),
        ({"status": 429, "headers": {"Retry-After": "30"}}, "rate_limited", 0),
        ({"status": 503}, "request_failed", 0),
        ({"json": tool_refusal("Peek couldn't read this text.")}, "request_failed", 0),
    ],
)
async def test_add_parcels_fails(
    hass: HomeAssistant, mock_parcels: AiohttpClientMocker, kwargs: dict, key: str, reauth: int
) -> None:
    """Peek's refusals become errors the user can read; a refused token asks to sign in again."""
    mock_parcels.post(MCP_URL, **kwargs)
    with pytest.raises(HomeAssistantError) as caught:
        await hass.services.async_call(DOMAIN, "add_parcels", {"text": "1Z4E7W960398127345"}, blocking=True)
    assert caught.value.translation_domain == DOMAIN
    assert caught.value.translation_key == key
    assert not isinstance(caught.value, ServiceValidationError)
    assert reauth_flows(hass) == reauth


@pytest.mark.usefixtures("setup_integration")
async def test_archive_parcel(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """A parcel is archived by tracking number or id, and the parcels are read again."""
    mock_parcels.post(MCP_URL, json=tool_answer({"id": BOOTS["id"], "archived": True}))
    before = reads(mock_parcels)
    await hass.services.async_call(DOMAIN, "archive_parcel", {"parcel": "1Z4E7W960398127345"}, blocking=True)
    call = next(call for call in mock_parcels.mock_calls if str(call[1]) == MCP_URL)
    assert call[3]["Mcp-Name"] == "archive_parcel"
    assert call[2]["params"]["arguments"] == {"parcel": "1Z4E7W960398127345"}
    assert reads(mock_parcels) == before + 2


@pytest.mark.usefixtures("setup_integration")
async def test_archive_unknown_parcel(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """A parcel the account doesn't have is the user's mistake, said in their words."""
    mock_parcels.post(MCP_URL, json=tool_refusal("No such parcel in this Peek account."))
    with pytest.raises(ServiceValidationError) as caught:
        await hass.services.async_call(DOMAIN, "archive_parcel", {"parcel": "QJ123456785GB"}, blocking=True)
    assert caught.value.translation_key == "parcel_not_found"
    assert caught.value.translation_placeholders == {"parcel": "QJ123456785GB"}
    # Home Assistant drops the message's last full stop.
    assert str(caught.value) == "Peek has no parcel QJ123456785GB"


@pytest.mark.usefixtures("setup_integration")
async def test_get_parcels(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """The parcels that match, read now, as the integration names their fields."""
    # The mock matches a query that holds these parameters: the narrower one first.
    mock_parcels.get(
        PARCELS_URL,
        params={"status": "delivered", "sort": "delivered", "search": "boots", "limit": "1"},
        json=answer(dict(BOOTS, status="delivered"), status="delivered", sort="delivered"),
    )
    mock_parcels.get(PARCELS_URL, params={"search": "boots"}, json=answer(BOOTS, total=1))
    response = await hass.services.async_call(
        DOMAIN, "get_parcels", {"search": "boots"}, blocking=True, return_response=True
    )
    assert response["total"] == 1
    assert response["parcels"][0]["tracking_number"] == "1Z4E7W960398127345"
    assert "section" not in response["parcels"][0]

    response = await hass.services.async_call(
        DOMAIN,
        "get_parcels",
        {"status": "delivered", "sort": "delivered", "search": "boots", "limit": "1"},
        blocking=True,
        return_response=True,
    )
    assert response["parcels"][0]["status"] == "delivered"


@pytest.mark.usefixtures("setup_integration")
async def test_get_parcels_fails(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """A failed read is an error."""
    mock_parcels.get(PARCELS_URL, params={"status": "all"}, status=500)
    with pytest.raises(HomeAssistantError) as caught:
        await hass.services.async_call(DOMAIN, "get_parcels", {"status": "all"}, blocking=True, return_response=True)
    assert caught.value.translation_key == "request_failed"


@pytest.mark.parametrize(
    ("service", "data", "response"),
    [
        ("add_parcels", {"text": "1Z4E7W960398127345"}, False),
        ("archive_parcel", {"parcel": "1Z4E7W960398127345"}, False),
        ("get_parcels", {}, True),
    ],
)
async def test_not_loaded(
    hass: HomeAssistant, setup_integration: MockConfigEntry, service: str, data: dict, response: bool
) -> None:
    """Without a loaded entry, the actions say so."""
    await hass.config_entries.async_unload(setup_integration.entry_id)
    with pytest.raises(ServiceValidationError) as caught:
        await hass.services.async_call(DOMAIN, service, data, blocking=True, return_response=response)
    assert caught.value.translation_key == "not_loaded"
