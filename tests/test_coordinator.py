"""Tests for reading Peek: how often, and what a failed read does."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.peek.const import DOMAIN, FAST_INTERVAL, SLOW_INTERVAL

from .common import (
    ACTIVE_QUERY,
    BOOKS,
    DELIVERED_QUERY,
    JACKET,
    PARCELS_URL,
    TOKEN_URL,
    URL,
    active_answer,
    answer,
    delivered_answer,
)
from .conftest import token

ON_THE_WAY = "sensor.peek_on_the_way"


def serve(mock: AiohttpClientMocker, active: dict | None = None, **kwargs) -> None:
    """Peek answering the next reads; with `kwargs`, refusing the first."""
    mock.clear_requests()
    if kwargs:
        mock.get(PARCELS_URL, params=ACTIVE_QUERY, **kwargs)
        return
    mock.get(PARCELS_URL, params=ACTIVE_QUERY, json=active or active_answer())
    mock.get(PARCELS_URL, params=DELIVERED_QUERY, json=delivered_answer())


async def later(hass: HomeAssistant, freezer: FrozenDateTimeFactory, delta: timedelta) -> None:
    """Let time pass."""
    freezer.tick(delta)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_fast_on_a_delivery_day(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_parcels: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A parcel out for delivery: Peek is read every 10 minutes."""
    assert setup_integration.runtime_data.coordinator.update_interval == FAST_INTERVAL
    serve(mock_parcels)
    await later(hass, freezer, FAST_INTERVAL)
    assert mock_parcels.call_count == 2


async def test_slow_otherwise(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Nothing arrives today: Peek is read every 30 minutes, and faster once a parcel does."""
    serve(aioclient_mock, answer(JACKET, BOOKS))
    config_entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    coordinator = config_entry.runtime_data.coordinator
    assert coordinator.update_interval == SLOW_INTERVAL

    serve(aioclient_mock, answer(JACKET, BOOKS))
    await later(hass, freezer, FAST_INTERVAL)
    assert aioclient_mock.call_count == 0
    await later(hass, freezer, SLOW_INTERVAL - FAST_INTERVAL)
    assert aioclient_mock.call_count == 2

    # The next morning, the jacket is expected today; the access token has expired by then.
    serve(aioclient_mock, answer(JACKET, BOOKS))
    aioclient_mock.post(TOKEN_URL, json={"access_token": "synthetic-fresh-token", "expires_in": 3600})
    await later(hass, freezer, timedelta(hours=12))
    assert coordinator.update_interval == FAST_INTERVAL


@pytest.mark.parametrize(
    "kwargs",
    [
        {"status": 401, "json": {"error": "invalid_token"}},
        {
            "status": 403,
            "json": {"error": "scope"},
            "headers": {"WWW-Authenticate": 'Bearer error="insufficient_scope"'},
        },
    ],
)
async def test_refused_token_asks_to_sign_in(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_parcels: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    kwargs: dict,
) -> None:
    """Peek refusing the token, or a missing scope, starts signing in again."""
    serve(mock_parcels, **kwargs)
    await later(hass, freezer, FAST_INTERVAL)
    flows = [flow for flow in hass.config_entries.flow.async_progress() if flow["context"]["source"] == SOURCE_REAUTH]
    assert len(flows) == 1
    assert hass.states.get(ON_THE_WAY).state == STATE_UNAVAILABLE


async def test_rate_limited_waits_as_asked(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_parcels: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A 429 waits Retry-After before the next read, then reads at the usual pace."""
    serve(mock_parcels, status=429, headers={"Retry-After": "120"})
    await later(hass, freezer, FAST_INTERVAL)
    assert hass.states.get(ON_THE_WAY).state == STATE_UNAVAILABLE
    assert setup_integration.state is ConfigEntryState.LOADED

    serve(mock_parcels)
    await later(hass, freezer, timedelta(seconds=60))
    assert mock_parcels.call_count == 0
    await later(hass, freezer, timedelta(seconds=61))
    assert mock_parcels.call_count == 2
    assert hass.states.get(ON_THE_WAY).state == "6"


async def test_recovers_after_an_outage(
    hass: HomeAssistant,
    setup_integration: MockConfigEntry,
    mock_parcels: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A server error leaves the entities unavailable until the next read works."""
    serve(mock_parcels, status=502, text="Bad gateway")
    await later(hass, freezer, FAST_INTERVAL)
    assert hass.states.get(ON_THE_WAY).state == STATE_UNAVAILABLE

    serve(mock_parcels)
    await later(hass, freezer, FAST_INTERVAL)
    assert hass.states.get(ON_THE_WAY).state == "6"


async def test_midnight_without_a_read(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    """At midnight in Home Assistant's time zone, "today" moves on without asking Peek."""
    serve(aioclient_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={"auth_implementation": DOMAIN, "token": token(), "url": URL},
        pref_disable_polling=True,
    )
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    assert hass.states.get("sensor.peek_arriving_today").state == "1"
    assert hass.states.get("sensor.peek_delivered_today").state == "1"

    aioclient_mock.clear_requests()
    freezer.move_to("2026-11-17T23:00:00+00:00")  # Midnight in Zurich.
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert aioclient_mock.call_count == 0
    # The boots are still out for delivery, and the jacket is expected on the 18th.
    assert hass.states.get("sensor.peek_arriving_today").state == "2"
    assert hass.states.get("sensor.peek_delivered_today").state == "0"
    assert hass.states.get("sensor.peek_next_delivery").state == "2026-11-18"
