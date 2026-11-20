"""Tests for Peek's actions."""

from typing import Any

import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)
from yarl import URL as Url

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

from custom_components.peek.const import DOMAIN

from .common import BOOTS, BOWLS, HOSE, LAMP, MCP_URL, PARCELS_URL, answer, tool_answer, tool_refusal

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


# Each edit: the action's data, the arguments Peek's tool gets, and Peek's answer.
EDITS = [
    ("restore_parcel", {"parcel": "46523910834"}, {"parcel": "46523910834"}, {"id": LAMP["id"], "archived": False}),
    (
        "rename_parcel",
        {"parcel": "1Z4E7W960398127345", "name": "Trail boots"},
        {"parcel": "1Z4E7W960398127345", "name": "Trail boots"},
        {"id": BOOTS["id"], "name": "Trail boots"},
    ),
    (
        "change_carrier",
        {"parcel": HOSE["id"], "carrier": "dpd-de", "postcode": "10115"},
        {"parcel": HOSE["id"], "carrier": "dpd-de", "postcode": "10115"},
        {"id": HOSE["id"], "carrier": "DPD Germany", "carrierId": "dpd-de", "checking": True},
    ),
    (
        "set_parcel_notifications",
        {"parcel": "1Z4E7W960398127345", "notifications": False},
        {"parcel": "1Z4E7W960398127345", "notifications": False},
        {"id": BOOTS["id"], "notifications": False, "emails": True},
    ),
]
EDIT_TOOLS = {"rename_parcel", "change_carrier", "set_parcel_notifications", "restore_parcel"}
NO_EDIT = (
    "This connection to Peek may not edit parcels. Connect Peek again and allow it to change their name, carrier or "
    "notifications and restore archived ones."
)


def reads(mock: AiohttpClientMocker) -> int:
    """How many times the parcels were read."""
    return sum(1 for call in mock.mock_calls if str(call[1]).startswith(PARCELS_URL))


def tool_call(mock: AiohttpClientMocker) -> tuple[str, dict[str, Any]]:
    """The tool the last call to Peek's MCP server named, and its arguments."""
    call = [call for call in mock.mock_calls if str(call[1]) == MCP_URL][-1]
    return call[3]["Mcp-Name"], call[2]["params"]["arguments"]


async def signed_in_before_editing(method: str, url: Url, data: dict[str, Any]) -> AiohttpClientMockResponse:
    """Peek's MCP server for a connection signed in before editing came: it may add and archive, not edit."""
    name = data["params"]["name"]
    if name in EDIT_TOOLS:
        reply = tool_refusal(NO_EDIT, scope=True, request_id=data["id"])
    else:
        reply = tool_answer({"parcels": ADDED[:1]}, request_id=data["id"])
    return AiohttpClientMockResponse(method, url, json=reply)


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
        ("restore_parcel", {}),
        ("restore_parcel", {"parcel": "x" * 101}),
        ("rename_parcel", {"parcel": "1Z4E7W960398127345"}),
        ("rename_parcel", {"parcel": "1Z4E7W960398127345", "name": "x" * 81}),
        ("change_carrier", {"parcel": "01505024382917"}),
        ("change_carrier", {"parcel": "01505024382917", "carrier": ""}),
        ("change_carrier", {"parcel": "01505024382917", "carrier": "x" * 61}),
        ("change_carrier", {"parcel": "01505024382917", "carrier": "dpd-de", "postcode": "x" * 21}),
        ("set_parcel_notifications", {"parcel": "1Z4E7W960398127345"}),
        ("set_parcel_notifications", {"parcel": "1Z4E7W960398127345", "notifications": "maybe"}),
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
            DOMAIN, service, data, blocking=True, return_response=service in ("add_parcels", "get_parcels")
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
async def test_archive_refused(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """Any other refusal comes in Peek's words."""
    mock_parcels.post(MCP_URL, json=tool_refusal("Peek is busy with this parcel."))
    with pytest.raises(ServiceValidationError) as caught:
        await hass.services.async_call(DOMAIN, "archive_parcel", {"parcel": "1Z4E7W960398127345"}, blocking=True)
    assert caught.value.translation_key == "refused"
    assert str(caught.value) == "Peek refused this: Peek is busy with this parcel."


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(("service", "data", "arguments", "reply"), EDITS)
async def test_edit(
    hass: HomeAssistant, mock_parcels: AiohttpClientMocker, service: str, data: dict, arguments: dict, reply: dict
) -> None:
    """Each edit calls its own tool with the parcel and what changes, and the parcels are read again."""
    mock_parcels.post(MCP_URL, json=tool_answer(reply))
    before = reads(mock_parcels)
    assert await hass.services.async_call(DOMAIN, service, data, blocking=True) is None
    assert tool_call(mock_parcels) == (service, arguments)
    assert reads(mock_parcels) == before + 2


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("service", "data", "arguments"),
    [
        ("rename_parcel", {"parcel": BOOTS["id"], "name": ""}, {"parcel": BOOTS["id"], "name": ""}),
        (
            "change_carrier",
            {"parcel": "01505024382917", "carrier": "dpd-de"},
            {"parcel": "01505024382917", "carrier": "dpd-de"},
        ),
        (
            "change_carrier",
            {"parcel": "01505024382917", "carrier": "dpd-de", "postcode": 10115},
            {"parcel": "01505024382917", "carrier": "dpd-de", "postcode": "10115"},
        ),
        (
            "set_parcel_notifications",
            {"parcel": "1Z4E7W960398127345", "notifications": "on"},
            {"parcel": "1Z4E7W960398127345", "notifications": True},
        ),
    ],
)
async def test_edit_arguments(
    hass: HomeAssistant, mock_parcels: AiohttpClientMocker, service: str, data: dict, arguments: dict
) -> None:
    """An empty name clears it, a carrier without a postcode keeps the parcel's; values come as Peek takes them."""
    mock_parcels.post(MCP_URL, json=tool_answer({"id": BOOTS["id"]}))
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert tool_call(mock_parcels) == (service, arguments)


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(("service", "data", "arguments", "reply"), EDITS)
async def test_edit_unknown_parcel(
    hass: HomeAssistant, mock_parcels: AiohttpClientMocker, service: str, data: dict, arguments: dict, reply: dict
) -> None:
    """A parcel the account doesn't have is the user's mistake, said in their words, and nothing is read again."""
    mock_parcels.post(MCP_URL, json=tool_refusal("No such parcel in this Peek account."))
    before = reads(mock_parcels)
    with pytest.raises(ServiceValidationError) as caught:
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert caught.value.translation_key == "parcel_not_found"
    assert caught.value.translation_placeholders == {"parcel": data["parcel"]}
    assert reads(mock_parcels) == before
    assert reauth_flows(hass) == 0


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(
    ("service", "data", "refusal", "key", "message"),
    [
        (
            "restore_parcel",
            {"parcel": "46523910834"},
            "The account follows as many parcels as it may. Archive one before restoring another.",
            "refused",
            "Peek refused this: The account follows as many parcels as it may. Archive one before restoring another.",
        ),
        (
            "rename_parcel",
            {"parcel": "1Z4E7W960398127345", "name": "Trail boots"},
            "Parcel names can be at most 80 characters",
            "refused",
            "Peek refused this: Parcel names can be at most 80 characters",
        ),
        (
            "change_carrier",
            {"parcel": "01505024382917", "carrier": "dpd-moon"},
            "Peek has no carrier with this id: find_carriers gives the ids.",
            "carrier_not_found",
            "Peek has no carrier with the id dpd-moon",
        ),
        (
            "change_carrier",
            {"parcel": "01505024382917", "carrier": "dpd-de", "postcode": "1011"},
            "Enter a 5-digit postcode",
            "refused",
            "Peek refused this: Enter a 5-digit postcode",
        ),
        (
            "set_parcel_notifications",
            {"parcel": "1Z4E7W960398127345", "notifications": True},
            "Say whether to turn the notifications, the emails or both off or on.",
            "refused",
            "Peek refused this: Say whether to turn the notifications, the emails or both off or on.",
        ),
    ],
)
async def test_edit_refused(
    hass: HomeAssistant,
    mock_parcels: AiohttpClientMocker,
    service: str,
    data: dict,
    refusal: str,
    key: str,
    message: str,
) -> None:
    """Peek's other refusals are the user's to fix, in Peek's words unless the integration has its own."""
    mock_parcels.post(MCP_URL, json=tool_refusal(refusal))
    with pytest.raises(ServiceValidationError) as caught:
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert caught.value.translation_key == key
    # Home Assistant drops the last full stop of the integration's own messages, not of Peek's words.
    assert str(caught.value) == message
    assert reauth_flows(hass) == 0


@pytest.mark.usefixtures("setup_integration")
@pytest.mark.parametrize(("service", "data", "arguments", "reply"), EDITS)
async def test_edit_signed_in_before_editing(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_parcels: AiohttpClientMocker,
    service: str,
    data: dict,
    arguments: dict,
    reply: dict,
) -> None:
    """A connection signed in before editing came asks to sign in again once, and still reads and adds."""
    assert "parcels:edit" not in setup_integration.data["token"]["scope"]
    mock_parcels.post(MCP_URL, side_effect=signed_in_before_editing)
    with pytest.raises(HomeAssistantError) as caught:
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert caught.value.translation_key == "missing_edit_scope"
    assert not isinstance(caught.value, ServiceValidationError)
    assert str(caught.value) == (
        "Home Assistant may not edit your parcels in Peek yet. Sign in to Peek again once to allow it: "
        "select Reconfigure next to Peek in Settings › Devices & services"
    )
    assert reauth_flows(hass) == 1

    # Another edit waits for the same sign-in.
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert reauth_flows(hass) == 1

    # Reading and adding go on meanwhile.
    assert setup_integration.state is ConfigEntryState.LOADED
    before = reads(mock_parcels)
    response = await hass.services.async_call(
        DOMAIN, "add_parcels", {"text": "1Z4E7W960398127345"}, blocking=True, return_response=True
    )
    assert response["parcels"][0]["outcome"] == "added"
    assert reads(mock_parcels) == before + 2
    assert hass.states.get("sensor.peek_on_the_way").state == "6"


@pytest.mark.usefixtures("setup_integration", "current_request_with_host")
async def test_edit_sign_in_asks_for_editing(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """The sign-in an edit asks for asks Peek for editing, with what the connection could already do."""
    mock_parcels.post(MCP_URL, side_effect=signed_in_before_editing)
    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            DOMAIN, "rename_parcel", {"parcel": "1Z4E7W960398127345", "name": "Trail boots"}, blocking=True
        )
    flow = next(
        flow for flow in hass.config_entries.flow.async_progress() if flow["context"]["source"] == SOURCE_REAUTH
    )
    result = await hass.config_entries.flow.async_configure(flow["flow_id"], {})
    assert Url(result["url"]).query["scope"] == "parcels:read parcels:write parcels:edit"


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
        ("restore_parcel", {"parcel": "46523910834"}, False),
        ("rename_parcel", {"parcel": "1Z4E7W960398127345", "name": "Trail boots"}, False),
        ("change_carrier", {"parcel": "01505024382917", "carrier": "dpd-de"}, False),
        ("set_parcel_notifications", {"parcel": "1Z4E7W960398127345", "notifications": False}, False),
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
