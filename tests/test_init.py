"""Tests for setting Peek up and removing it."""

from http import HTTPStatus
from unittest.mock import patch

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.peek.const import DOMAIN

from .common import (
    ACTIVE_QUERY,
    CLIENT_ID,
    DELIVERED_QUERY,
    PARCELS_URL,
    REVOKE_URL,
    TOKEN_URL,
    active_answer,
    delivered_answer,
)
from .conftest import token


def reauth_flows(hass: HomeAssistant) -> list:
    """The sign-in flows waiting for the user."""
    return [flow for flow in hass.config_entries.flow.async_progress() if flow["context"]["source"] == SOURCE_REAUTH]


async def test_setup_and_unload(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    """The entry loads, with its entities, and unloads."""
    entry = setup_integration
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.peek_on_the_way").state == "6"
    assert hass.services.has_service(DOMAIN, "add_parcels")

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED
    assert hass.states.get("sensor.peek_on_the_way").state == "unavailable"
    # The actions stay: they answer that Peek isn't set up.
    assert hass.services.has_service(DOMAIN, "add_parcels")


async def test_token_for_another_peek(hass: HomeAssistant, mock_parcels: AiohttpClientMocker) -> None:
    """A token signed in at another address asks to sign in again, without reading Peek."""
    entry = MockConfigEntry(
        domain=DOMAIN, data={"auth_implementation": DOMAIN, "token": token(), "url": "http://localhost:3000"}
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert len(reauth_flows(hass)) == 1
    assert mock_parcels.call_count == 0


async def test_refreshes_token(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_parcels: AiohttpClientMocker
) -> None:
    """An expired access token is refreshed before reading, and stored."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, data={**config_entry.data, "token": token(expires_in=-60)})
    mock_parcels.post(
        TOKEN_URL,
        json={
            "access_token": "synthetic-fresh-token",
            "refresh_token": "synthetic-fresh-refresh",
            "expires_in": 3600,
        },
    )
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert config_entry.data["token"]["access_token"] == "synthetic-fresh-token"
    refresh = next(call for call in mock_parcels.mock_calls if str(call[1]) == TOKEN_URL)
    assert refresh[2] == {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": "synthetic-refresh-token",
    }
    read = next(call for call in mock_parcels.mock_calls if str(call[1]).startswith(PARCELS_URL))
    assert read[3]["Authorization"] == "Bearer synthetic-fresh-token"


@pytest.mark.parametrize(
    ("kwargs", "state", "reauth"),
    [
        ({"status": 400, "json": {"error": "invalid_grant"}}, ConfigEntryState.SETUP_ERROR, 1),
        ({"status": 503}, ConfigEntryState.SETUP_RETRY, 0),
        ({"exc": ClientError("down")}, ConfigEntryState.SETUP_RETRY, 0),
        ({"exc": TimeoutError()}, ConfigEntryState.SETUP_RETRY, 0),
    ],
)
async def test_refresh_fails(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_parcels: AiohttpClientMocker,
    kwargs: dict,
    state: ConfigEntryState,
    reauth: int,
) -> None:
    """A refused refresh token asks to sign in again; an unreachable token endpoint retries."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, data={**config_entry.data, "token": token(expires_in=-60)})
    mock_parcels.post(TOKEN_URL, **kwargs)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert config_entry.state is state
    assert len(reauth_flows(hass)) == reauth


@pytest.mark.parametrize(
    ("kwargs", "state", "reauth"),
    [
        ({"status": 401, "json": {"error": "invalid_token"}}, ConfigEntryState.SETUP_ERROR, 1),
        (
            {
                "status": 403,
                "json": {"error": "scope"},
                "headers": {"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
            },
            ConfigEntryState.SETUP_ERROR,
            1,
        ),
        ({"status": 429, "headers": {"Retry-After": "120"}}, ConfigEntryState.SETUP_RETRY, 0),
        ({"status": 500}, ConfigEntryState.SETUP_RETRY, 0),
    ],
)
async def test_first_read_fails(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict,
    state: ConfigEntryState,
    reauth: int,
) -> None:
    """A refused token asks to sign in again; anything else retries."""
    aioclient_mock.get(PARCELS_URL, params=ACTIVE_QUERY, **kwargs)
    config_entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert config_entry.state is state
    assert len(reauth_flows(hass)) == reauth


async def test_remove_revokes(
    hass: HomeAssistant, setup_integration: MockConfigEntry, aioclient_mock: AiohttpClientMocker
) -> None:
    """Removing Peek gives the refresh token back."""
    aioclient_mock.post(REVOKE_URL)
    await hass.config_entries.async_remove(setup_integration.entry_id)
    await hass.async_block_till_done()
    revoke = next(call for call in aioclient_mock.mock_calls if str(call[1]) == REVOKE_URL)
    assert revoke[2] == {
        "token": "synthetic-refresh-token",
        "client_id": CLIENT_ID,
        "token_type_hint": "refresh_token",
    }


async def test_remove_when_revoke_fails(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Peek not taking the token back still removes the entry, and says where to finish."""
    aioclient_mock.post(REVOKE_URL, status=503)
    await hass.config_entries.async_remove(setup_integration.entry_id)
    await hass.async_block_till_done()
    assert not hass.config_entries.async_entries(DOMAIN)
    assert "remove Home Assistant in Peek's settings" in caplog.text


async def test_remove_without_token(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """An entry without a token has nothing to give back."""
    entry = MockConfigEntry(domain=DOMAIN, data={"auth_implementation": DOMAIN, "token": {}})
    entry.add_to_hass(hass)
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert aioclient_mock.call_count == 0


async def test_card_is_served(hass: HomeAssistant, hass_client: ClientSessionGenerator) -> None:
    """The card's files are served under the integration's version, cached."""
    assert await async_setup_component(hass, DOMAIN, {})
    client = await hass_client()
    for name in ("peek-parcels-card.js", "peek-pip.js", "peek-trucks.js"):
        response = await client.get(f"/peek/static/0.1.1/{name}")
        assert response.status == HTTPStatus.OK
        assert "javascript" in response.headers["Content-Type"]
        assert "max-age" in response.headers.get("Cache-Control", "")
    assert (await client.get("/peek/static/0.1.1/missing.js")).status == HTTPStatus.NOT_FOUND


async def test_card_on_dashboards(hass: HomeAssistant) -> None:
    """With the frontend loaded, every dashboard loads the card."""
    hass.config.components.add("frontend")
    with patch("custom_components.peek.card.add_extra_js_url") as add:
        assert await async_setup_component(hass, DOMAIN, {})
    add.assert_called_once_with(hass, "/peek/static/0.1.1/peek-parcels-card.js")


async def test_card_without_frontend(hass: HomeAssistant) -> None:
    """Without the frontend, nothing is added to the dashboards."""
    with patch("custom_components.peek.card.add_extra_js_url") as add:
        assert await async_setup_component(hass, DOMAIN, {})
    add.assert_not_called()


async def test_yaml_override_reads_there(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """configuration.yaml sends the reads to another Peek."""
    local = "http://localhost:3000"
    aioclient_mock.get(f"{local}/api/parcels", params=ACTIVE_QUERY, json=active_answer())
    aioclient_mock.get(f"{local}/api/parcels", params=DELIVERED_QUERY, json=delivered_answer())
    entry = MockConfigEntry(domain=DOMAIN, data={"auth_implementation": DOMAIN, "token": token(), "url": local})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: {"url": local}})
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert all(str(call[1]).startswith(local) for call in aioclient_mock.mock_calls)
