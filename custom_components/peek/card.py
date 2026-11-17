"""The Peek parcels card, served by the integration itself.

The card's files are served under a path holding the integration's version, so a browser fetches them again after an
update, and the card is loaded on every dashboard through `add_extra_js_url`: nothing is written to the dashboards'
resources.
"""

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from .const import CARD_FILE, DOMAIN

FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_setup_card(hass: HomeAssistant) -> str:
    """Serve the card and load it on the dashboards; its address."""
    integration = await async_get_integration(hass, DOMAIN)
    base = f"/{DOMAIN}/static/{integration.version}"
    await hass.http.async_register_static_paths([StaticPathConfig(base, str(FRONTEND_DIR), cache_headers=True)])
    url = f"{base}/{CARD_FILE}"
    # The frontend is set up first when it is set up at all (`after_dependencies`).
    if "frontend" in hass.config.components:
        add_extra_js_url(hass, url)
    return url
