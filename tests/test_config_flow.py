"""Tests for signing in to Peek."""

import base64
import hashlib
from http import HTTPStatus
from unittest.mock import patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator
from yarl import URL as Url

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers.config_entry_oauth2_flow import MY_AUTH_CALLBACK_PATH, async_get_implementations
from homeassistant.setup import async_setup_component

from custom_components.peek.const import DOMAIN

from .common import CLIENT_ID, TOKEN_URL, URL

LOCAL = "http://localhost:3000"

NEW_TOKEN = {
    "access_token": "synthetic-new-access-token",
    "refresh_token": "synthetic-new-refresh-token",
    "token_type": "Bearer",
    "scope": "parcels:read parcels:write",
    "expires_in": 3600,
}


@pytest.fixture(autouse=True)
def no_setup():
    """Create entries without reading Peek.

    The card's static path is left out too: aiohttp's test server freezes the router, which Home Assistant's own
    server never does.
    """
    with (
        patch("custom_components.peek.async_setup_entry", return_value=True) as setup,
        patch("custom_components.peek.async_setup_card"),
    ):
        yield setup


async def _authorize(hass: HomeAssistant, result, client_no_auth: ClientSessionGenerator, query: str) -> Url:
    """Follow the browser through Peek's sign-in, back to Home Assistant with `query`."""
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    url = Url(result["url"])
    client = await client_no_auth()
    response = await client.get(f"/auth/external/callback?{query}&state={url.query['state']}")
    assert response.status == HTTPStatus.OK
    return url


@pytest.mark.usefixtures("current_request_with_host")
async def test_full_flow(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    no_setup,
) -> None:
    """Peek's sign-in, with PKCE, through My Home Assistant, creates the entry; no setup has run before."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    url = await _authorize(hass, result, hass_client_no_auth, "code=synthetic-code")

    assert f"{url.scheme}://{url.host}{url.path}" == f"{URL}/oauth/authorize"
    query = dict(url.query)
    assert query["response_type"] == "code"
    assert query["client_id"] == CLIENT_ID
    assert query["redirect_uri"] == MY_AUTH_CALLBACK_PATH
    assert query["scope"] == "parcels:read parcels:write"
    assert query["code_challenge_method"] == "S256"

    aioclient_mock.post(TOKEN_URL, json=NEW_TOKEN)
    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Peek"
    assert result["data"]["auth_implementation"] == DOMAIN
    assert result["data"]["url"] == URL
    assert result["data"]["token"]["access_token"] == "synthetic-new-access-token"
    assert result["data"]["token"]["refresh_token"] == "synthetic-new-refresh-token"
    assert len(no_setup.mock_calls) == 1

    sent = aioclient_mock.mock_calls[0][2]
    assert sent["grant_type"] == "authorization_code"
    assert sent["code"] == "synthetic-code"
    assert sent["redirect_uri"] == MY_AUTH_CALLBACK_PATH
    assert sent["client_id"] == CLIENT_ID
    assert "client_secret" not in sent
    challenge = base64.urlsafe_b64encode(hashlib.sha256(sent["code_verifier"].encode()).digest()).rstrip(b"=")
    assert challenge.decode() == query["code_challenge"]


@pytest.mark.usefixtures("current_request_with_host")
async def test_each_sign_in_has_its_own_verifier(hass: HomeAssistant) -> None:
    """Two sign-ins don't share a PKCE verifier."""
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    hass.config_entries.flow.async_abort(first["flow_id"])
    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert Url(first["url"]).query["code_challenge"] != Url(second["url"]).query["code_challenge"]


async def test_single_entry(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    """Peek is set up once."""
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


@pytest.mark.usefixtures("current_request_with_host")
async def test_user_rejects(hass: HomeAssistant, hass_client_no_auth: ClientSessionGenerator) -> None:
    """Declining in Peek ends the flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    await _authorize(hass, result, hass_client_no_auth, "error=access_denied")
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "user_rejected_authorize"


@pytest.mark.usefixtures("current_request_with_host")
@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"status": 500}, "oauth_failed"),
        ({"status": 400, "json": {"error": "invalid_grant"}}, "oauth_unauthorized"),
        ({"json": {"access_token": "synthetic", "token_type": "Bearer"}}, "oauth_error"),
    ],
)
async def test_token_refused(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    kwargs: dict,
    reason: str,
) -> None:
    """A token endpoint that fails ends the flow."""
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    await _authorize(hass, result, hass_client_no_auth, "code=synthetic-code")
    aioclient_mock.post(TOKEN_URL, **kwargs)
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == reason


@pytest.mark.usefixtures("current_request_with_host")
async def test_reauth(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    config_entry: MockConfigEntry,
    no_setup,
) -> None:
    """Signing in again replaces the token and reloads the entry."""
    config_entry.add_to_hass(hass)
    result = await config_entry.start_reauth_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    await _authorize(hass, result, hass_client_no_auth, "code=synthetic-code")
    aioclient_mock.post(TOKEN_URL, json=NEW_TOKEN)
    result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert config_entry.data["token"]["access_token"] == "synthetic-new-access-token"
    assert config_entry.data["url"] == URL
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.usefixtures("current_request_with_host")
@pytest.mark.parametrize(
    ("conf", "client_id"),
    [
        ({"url": f"{LOCAL}/"}, f"{LOCAL}/oauth/clients/home-assistant.json"),
        (
            {"url": LOCAL, "client_id": "http://localhost:8123/peek-client.json"},
            "http://localhost:8123/peek-client.json",
        ),
    ],
)
async def test_yaml_override(
    hass: HomeAssistant,
    hass_client_no_auth: ClientSessionGenerator,
    aioclient_mock: AiohttpClientMocker,
    caplog: pytest.LogCaptureFixture,
    conf: dict,
    client_id: str,
) -> None:
    """configuration.yaml points the sign-in at another Peek, such as a local one."""
    assert await async_setup_component(hass, DOMAIN, {DOMAIN: conf})
    assert f"Peek is read at {LOCAL}" in caplog.text

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    url = await _authorize(hass, result, hass_client_no_auth, "code=synthetic-code")
    assert str(url).startswith(f"{LOCAL}/oauth/authorize?")
    assert url.query["client_id"] == client_id

    aioclient_mock.post(f"{LOCAL}/oauth/token", json=NEW_TOKEN)
    result = await hass.config_entries.flow.async_configure(result["flow_id"])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["url"] == LOCAL
    assert aioclient_mock.mock_calls[0][2]["client_id"] == client_id


async def test_implementation(hass: HomeAssistant) -> None:
    """Peek offers its own sign-in, to its own flows only."""
    assert await async_setup_component(hass, DOMAIN, {})
    implementations = await async_get_implementations(hass, DOMAIN)
    assert [implementation.name for implementation in implementations.values()] == ["Peek"]
    assert await async_get_implementations(hass, "another_integration") == {}
