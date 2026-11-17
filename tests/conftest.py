"""Fixtures for the Peek tests."""

from collections.abc import AsyncGenerator, Generator
import time
from typing import Any

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.peek.const import DOMAIN

from .common import (
    ACTIVE_QUERY,
    DELIVERED_QUERY,
    PARCELS_URL,
    URL,
    active_answer,
    delivered_answer,
)

NOW = "2026-11-17T12:00:00+00:00"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture(autouse=True)
async def zurich(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Home Assistant in Zurich, on Tuesday 17 November 2026 at 13:00."""
    await hass.config.async_set_time_zone("Europe/Zurich")
    freezer.move_to(NOW)


def token(expires_in: float = 3600) -> dict[str, Any]:
    """A stored token."""
    return {
        "access_token": "synthetic-access-token",
        "refresh_token": "synthetic-refresh-token",
        "token_type": "Bearer",
        "scope": "parcels:read parcels:write",
        "expires_in": 3600,
        "expires_at": time.time() + expires_in,
    }


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A Peek entry, signed in."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Peek",
        data={"auth_implementation": DOMAIN, "token": token(), "url": URL},
    )


@pytest.fixture
def mock_parcels(aioclient_mock: AiohttpClientMocker) -> AiohttpClientMocker:
    """Peek's API answering both reads."""
    aioclient_mock.get(PARCELS_URL, params=ACTIVE_QUERY, json=active_answer())
    aioclient_mock.get(PARCELS_URL, params=DELIVERED_QUERY, json=delivered_answer())
    return aioclient_mock


@pytest.fixture
async def setup_integration(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_parcels: AiohttpClientMocker
) -> AsyncGenerator[MockConfigEntry]:
    """Peek set up, with the default parcels."""
    config_entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    yield config_entry


@pytest.fixture
def platforms() -> Generator[None]:
    """Every platform (a test may narrow them)."""
    yield
