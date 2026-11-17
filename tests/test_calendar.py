"""Tests for Peek's "Deliveries" calendar."""

from datetime import datetime

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.calendar import DOMAIN as CALENDAR_DOMAIN, SERVICE_GET_EVENTS
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.peek.const import DOMAIN

from .common import ACTIVE_QUERY, BOOKS, DELIVERED_QUERY, JACKET, PARCELS_URL, URL, answer
from .conftest import token

CALENDAR = "calendar.peek_deliveries"


async def events(hass: HomeAssistant, start: str, end: str) -> list[dict]:
    """The calendar's events between two local days."""
    tz = dt_util.get_default_time_zone()
    response = await hass.services.async_call(
        CALENDAR_DOMAIN,
        SERVICE_GET_EVENTS,
        {
            "entity_id": CALENDAR,
            "start_date_time": datetime.fromisoformat(start).replace(tzinfo=tz),
            "end_date_time": datetime.fromisoformat(end).replace(tzinfo=tz),
        },
        blocking=True,
        return_response=True,
    )
    return response[CALENDAR]["events"]


@pytest.mark.usefixtures("setup_integration")
async def test_today(hass: HomeAssistant) -> None:
    """A parcel expected today, or delivered today, turns the calendar on."""
    state = hass.states.get(CALENDAR)
    assert state.state == STATE_ON
    assert state.attributes["message"] == "Hiking boots · UPS"
    assert state.attributes["all_day"] is True
    assert state.attributes["start_time"] == "2026-11-17 00:00:00"


@pytest.mark.usefixtures("setup_integration")
async def test_events(hass: HomeAssistant) -> None:
    """Parcels on their way sit on their expected day, delivered ones on the day they came."""
    found = await events(hass, "2026-11-16T00:00:00", "2026-11-19T00:00:00")
    assert [(event["start"], event["summary"]) for event in found] == [
        ("2026-11-16", "Ceramic bowls · La Poste / Colissimo"),
        ("2026-11-17", "Hiking boots · UPS"),
        ("2026-11-17", "USB-C dock · Swiss Post"),
        ("2026-11-18", "Garden hose · DPD Switzerland"),
        ("2026-11-18", "Winter jacket · DHL"),
    ]
    bowls = found[0]
    assert bowls["end"] == "2026-11-17"
    assert bowls["location"] == "Relais Demo"
    assert bowls["description"] == "Scanned at depot"


@pytest.mark.usefixtures("setup_integration")
async def test_titles_and_old_deliveries(hass: HomeAssistant) -> None:
    """A parcel without a name is called by its shop; archived deliveries stay in the calendar."""
    found = await events(hass, "2026-11-01T00:00:00", "2026-11-30T00:00:00")
    summaries = [event["summary"] for event in found]
    assert "Demo Books · PostNL" in summaries
    assert "Desk lamp · GLS Switzerland" in summaries
    assert len(found) == 8


@pytest.mark.usefixtures("setup_integration")
async def test_a_moment_inside_a_day(hass: HomeAssistant) -> None:
    """A window that starts in the middle of a day still holds that day's events."""
    found = await events(hass, "2026-11-23T18:00:00", "2026-11-23T19:00:00")
    assert [event["summary"] for event in found] == ["Phone case · AliExpress / Cainiao"]


async def test_later_or_none(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, freezer: FrozenDateTimeFactory
) -> None:
    """Nothing today: the calendar is off and shows the next delivery; nothing known: no event."""
    aioclient_mock.get(
        PARCELS_URL,
        params=ACTIVE_QUERY,
        json=answer(JACKET, BOOKS, dict(BOOKS, id="x", expectedDelivery=None)),
    )
    aioclient_mock.get(PARCELS_URL, params=DELIVERED_QUERY, json=answer(status="delivered"))
    entry = MockConfigEntry(domain=DOMAIN, data={"auth_implementation": DOMAIN, "token": token(), "url": URL})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    state = hass.states.get(CALENDAR)
    assert state.state == STATE_OFF
    assert state.attributes["message"] == "Winter jacket · DHL"

    aioclient_mock.clear_requests()
    aioclient_mock.get(PARCELS_URL, params=ACTIVE_QUERY, json=answer())
    aioclient_mock.get(PARCELS_URL, params=DELIVERED_QUERY, json=answer(status="delivered"))
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get(CALENDAR)
    assert state.state == STATE_OFF
    assert "message" not in state.attributes
