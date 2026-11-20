"""Signing in to Peek: a public OAuth client with PKCE, built into the integration.

Peek publishes a Client ID Metadata Document for Home Assistant, so the client id is a URL and there is no secret: the
user never sees Home Assistant's Application Credentials screen. The implementation is offered through an
implementation provider, which hands each sign-in a fresh instance and so a fresh PKCE verifier.
"""

from dataclasses import dataclass
from typing import Any, Self, override

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_entry_oauth2_flow
from homeassistant.util.hass_dict import HassKey

from .const import (
    AUTHORIZE_PATH,
    CLIENT_ID_PATH,
    CONF_CLIENT_ID,
    CONF_URL,
    DEFAULT_URL,
    DOMAIN,
    SCOPES,
    TOKEN_PATH,
)


@dataclass(frozen=True, slots=True)
class PeekConfig:
    """Where Peek is, and the client id the integration signs in with."""

    url: str = DEFAULT_URL
    client_id: str = f"{DEFAULT_URL}{CLIENT_ID_PATH}"

    @classmethod
    def from_yaml(cls, conf: dict[str, Any]) -> Self:
        """The `peek:` block of configuration.yaml; without one, Peek's own address."""
        url = str(conf.get(CONF_URL, DEFAULT_URL)).rstrip("/")
        return cls(url=url, client_id=str(conf.get(CONF_CLIENT_ID, f"{url}{CLIENT_ID_PATH}")))

    @property
    def overridden(self) -> bool:
        """Whether configuration.yaml points the integration elsewhere than Peek's own address."""
        return self != PeekConfig()


DATA_CONFIG: HassKey[PeekConfig] = HassKey(f"{DOMAIN}_config")


class PeekImplementation(config_entry_oauth2_flow.LocalOAuth2ImplementationWithPkce):
    """Peek's authorization server, asked for every scope, answering through My Home Assistant."""

    def __init__(self, hass: HomeAssistant, config: PeekConfig) -> None:
        """Point the implementation at Peek."""
        super().__init__(
            hass,
            DOMAIN,
            config.client_id,
            f"{config.url}{AUTHORIZE_PATH}",
            f"{config.url}{TOKEN_PATH}",
        )

    @property
    @override
    def name(self) -> str:
        """Name of the implementation."""
        return "Peek"

    @property
    @override
    def redirect_uri(self) -> str:
        """My Home Assistant's address, the only one Peek's client document allows.

        It works whether or not the `my` integration is loaded: My Home Assistant sends the browser back to the
        instance the user chose there.
        """
        return config_entry_oauth2_flow.MY_AUTH_CALLBACK_PATH

    @property
    @override
    def extra_authorize_data(self) -> dict[str, Any]:
        """Ask for every scope, with PKCE's challenge."""
        return {"scope": SCOPES, **super().extra_authorize_data}


@callback
def async_setup_oauth(hass: HomeAssistant, config: PeekConfig) -> None:
    """Offer Peek's implementation to the integration's sign-in flows."""
    hass.data[DATA_CONFIG] = config

    async def provide(hass: HomeAssistant, domain: str) -> list[config_entry_oauth2_flow.AbstractOAuth2Implementation]:
        if domain != DOMAIN:
            return []
        return [PeekImplementation(hass, hass.data[DATA_CONFIG])]

    config_entry_oauth2_flow.async_add_implementation_provider(hass, DOMAIN, provide)


@callback
def async_ensure_oauth(hass: HomeAssistant) -> PeekConfig:
    """Peek's settings, offering the implementation first if nothing has yet.

    A config flow runs without the integration being set up when no entry exists, and so without `async_setup`.
    """
    if DATA_CONFIG not in hass.data:
        async_setup_oauth(hass, PeekConfig())
    return hass.data[DATA_CONFIG]
