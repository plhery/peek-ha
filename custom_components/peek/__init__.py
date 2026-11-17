"""The Peek integration: the parcels Peek follows, in Home Assistant."""

from functools import partial

from aiohttp import ClientError
import probatio

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    OAuth2TokenRequestReauthError,
)
from homeassistant.helpers import config_entry_oauth2_flow, config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import PeekAuthError, PeekClient, PeekError, PeekUnavailableError, revoke_token
from .card import async_setup_card
from .const import CONF_CLIENT_ID, CONF_URL, DEFAULT_URL, DOMAIN, LOGGER
from .coordinator import PeekConfigEntry, PeekCoordinator, PeekRuntime
from .oauth import PeekConfig, async_ensure_oauth, async_setup_oauth
from .services import async_setup_services

PLATFORMS = [Platform.CALENDAR, Platform.EVENT, Platform.SENSOR]

# Only for development: point the integration at another Peek, such as a local server.
CONFIG_SCHEMA = probatio.Schema(
    {
        DOMAIN: probatio.Schema(
            {
                probatio.Optional(CONF_URL): cv.url,
                probatio.Optional(CONF_CLIENT_ID): cv.url,
            }
        )
    },
    extra=probatio.ALLOW_EXTRA,
)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Offer Peek's sign-in, register the actions and serve the card."""
    config_ = PeekConfig.from_yaml(config.get(DOMAIN) or {})
    if config_.overridden:
        LOGGER.warning("Peek is read at %s, as configuration.yaml says", config_.url)
    async_setup_oauth(hass, config_)
    async_setup_services(hass)
    await async_setup_card(hass)
    return True


async def _access_token(session: config_entry_oauth2_flow.OAuth2Session) -> str:
    """A valid access token, refreshed when it is about to expire."""
    try:
        await session.async_ensure_token_valid()
    except OAuth2TokenRequestReauthError as err:
        raise PeekAuthError("Peek refused the refresh token") from err
    except (ClientError, TimeoutError) as err:
        raise PeekUnavailableError("Peek's token endpoint can't be reached") from err
    return str(session.token["access_token"])


async def async_setup_entry(hass: HomeAssistant, entry: PeekConfigEntry) -> bool:
    """Read the parcels and set up the entities."""
    config = async_ensure_oauth(hass)
    if entry.data.get(CONF_URL, DEFAULT_URL) != config.url:
        # The token belongs to another Peek than the one configured now.
        raise ConfigEntryAuthFailed(
            translation_domain=DOMAIN,
            translation_key="url_changed",
            translation_placeholders={"url": config.url},
        )
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    integration = await async_get_integration(hass, DOMAIN)
    client = PeekClient(
        async_get_clientsession(hass),
        config.url,
        partial(_access_token, session),
        str(integration.version),
    )
    coordinator = PeekCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    coordinator.async_track_midnight()
    entry.runtime_data = PeekRuntime(client=client, coordinator=coordinator)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: PeekConfigEntry) -> bool:
    """Unload the entities."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: PeekConfigEntry) -> None:
    """Give the token back, so that Peek forgets the connection too."""
    token = entry.data.get("token") or {}
    if not (secret := token.get("refresh_token") or token.get("access_token")):
        return
    config = async_ensure_oauth(hass)
    try:
        await revoke_token(
            async_get_clientsession(hass),
            entry.data.get(CONF_URL, config.url),
            config.client_id,
            secret,
        )
    except PeekError as err:
        LOGGER.warning("Peek did not take the token back (%s); remove Home Assistant in Peek's settings", err)
