"""Tests for Peek's sensors."""

from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.const import ATTR_DEVICE_CLASS, ATTR_UNIT_OF_MEASUREMENT, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component

from custom_components.peek.const import DOMAIN
from custom_components.peek.sensor import PeekSensor

from .common import (
    ACTIVE_QUERY,
    BOOKS,
    BOOTS,
    BOWLS,
    CASE,
    DELIVERED_QUERY,
    DOCK,
    HOSE,
    JACKET,
    PARCELS_URL,
    URL,
    active_answer,
    answer,
    delivered_answer,
)
from .conftest import token


async def set_up(
    hass: HomeAssistant, mock: AiohttpClientMocker, active: dict | None = None, delivered: dict | None = None
) -> MockConfigEntry:
    """Set Peek up with these answers, signed in now."""
    mock.get(PARCELS_URL, params=ACTIVE_QUERY, json=active or active_answer())
    mock.get(PARCELS_URL, params=DELIVERED_QUERY, json=delivered or delivered_answer())
    entry = MockConfigEntry(domain=DOMAIN, data={"auth_implementation": DOMAIN, "token": token(), "url": URL})
    entry.add_to_hass(hass)
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()
    return entry


@pytest.mark.usefixtures("setup_integration")
async def test_counts(hass: HomeAssistant) -> None:
    """The counts follow Peek's sections, with "today" in Home Assistant's time zone."""
    expected = {
        "sensor.peek_on_the_way": "6",
        "sensor.peek_arriving_today": "1",
        "sensor.peek_needs_attention": "3",
        "sensor.peek_delivered_today": "1",
    }
    for entity_id, value in expected.items():
        state = hass.states.get(entity_id)
        assert state.state == value, entity_id
        assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "parcels"
        assert state.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT


@pytest.mark.usefixtures("setup_integration")
async def test_parcels_attributes(hass: HomeAssistant) -> None:
    """On the way lists every parcel with its section; delivered today lists today's deliveries."""
    parcels = hass.states.get("sensor.peek_on_the_way").attributes["parcels"]
    assert [(item["id"], item["section"]) for item in parcels] == [
        (BOOTS["id"], "today"),
        (BOWLS["id"], "attention"),
        (JACKET["id"], "active"),
        (HOSE["id"], "attention"),
        (BOOKS["id"], "active"),
        (CASE["id"], "attention"),
    ]
    assert parcels[0] == {
        "id": BOOTS["id"],
        "name": "Hiking boots",
        "carrier": "UPS",
        "tracking_number": "1Z4E7W960398127345",
        "status": "out_for_delivery",
        "status_text": "Out for delivery today",
        "needs_attention": None,
        "expected_delivery": "2026-11-17",
        "delivered_at": None,
        "last_update": "2026-11-17T09:00:00+00:00",
        "location": "Zurich",
        "pickup_point": None,
        "sender": "Fjord Outdoor",
        "archived": False,
        "section": "today",
    }
    assert parcels[4]["name"] is None
    assert parcels[4]["sender"] == "Demo Books"

    delivered = hass.states.get("sensor.peek_delivered_today").attributes["parcels"]
    assert [item["id"] for item in delivered] == [DOCK["id"]]
    assert "section" not in delivered[0]

    assert "parcels" not in hass.states.get("sensor.peek_arriving_today").attributes
    assert "parcels" not in hass.states.get("sensor.peek_needs_attention").attributes


@pytest.mark.usefixtures("setup_integration")
async def test_next_delivery(hass: HomeAssistant) -> None:
    """The next day a parcel comes, today or later, and the parcels expected then."""
    state = hass.states.get("sensor.peek_next_delivery")
    assert state.state == "2026-11-17"
    assert state.attributes[ATTR_DEVICE_CLASS] == "date"
    assert ATTR_UNIT_OF_MEASUREMENT not in state.attributes
    # The bowls were expected yesterday: not "next".
    assert [item["id"] for item in state.attributes["parcels"]] == [BOOTS["id"]]


async def test_nothing_expected(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """No day known: the next delivery is unknown, and nothing is counted."""
    undated = dict(JACKET, expectedDelivery=None)
    await set_up(hass, aioclient_mock, answer(undated), answer(status="delivered"))
    state = hass.states.get("sensor.peek_next_delivery")
    assert state.state == STATE_UNKNOWN
    assert state.attributes["parcels"] == []
    assert hass.states.get("sensor.peek_arriving_today").state == "0"
    assert hass.states.get("sensor.peek_delivered_today").state == "0"
    assert hass.states.get("sensor.peek_delivered_today").attributes["parcels"] == []


async def test_on_the_way_counts_beyond_the_list(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """More parcels than one read lists: the count is Peek's total."""
    await set_up(hass, aioclient_mock, answer(BOOTS, JACKET, total=73))
    state = hass.states.get("sensor.peek_on_the_way")
    assert state.state == "73"
    assert len(state.attributes["parcels"]) == 2


@pytest.mark.parametrize(
    ("time_zone", "arriving", "delivered", "next_day"),
    [
        # 04:00 on Wednesday the 18th: the jacket is expected today, the dock came yesterday.
        ("Europe/Zurich", "2", "0", "2026-11-18"),
        # 22:00 on Tuesday the 17th: the dock, delivered at 05:05, came today.
        ("America/New_York", "1", "1", "2026-11-17"),
    ],
)
async def test_today_is_local(
    hass: HomeAssistant,
    aioclient_mock: AiohttpClientMocker,
    freezer: FrozenDateTimeFactory,
    time_zone: str,
    arriving: str,
    delivered: str,
    next_day: str,
) -> None:
    """The same moment is another day in another time zone."""
    await hass.config.async_set_time_zone(time_zone)
    freezer.move_to("2026-11-18T03:00:00+00:00")
    await set_up(hass, aioclient_mock)
    assert hass.states.get("sensor.peek_arriving_today").state == arriving
    assert hass.states.get("sensor.peek_delivered_today").state == delivered
    assert hass.states.get("sensor.peek_next_delivery").state == next_day


async def test_delivered_day_forms(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """A carrier that gives only a day, or a local time, counts on that day; an unreadable time does not count."""
    only_day = dict(DOCK, id="a1", deliveredAt="2026-11-17")
    local_time = dict(DOCK, id="a2", deliveredAt="2026-11-17T08:30:00")
    unreadable = dict(DOCK, id="a3", deliveredAt="yesterday")
    missing = dict(DOCK, id="a4", deliveredAt=None)
    returned = dict(DOCK, id="a5", status="returned")
    await set_up(
        hass,
        aioclient_mock,
        delivered=answer(only_day, local_time, unreadable, missing, returned, status="delivered"),
    )
    state = hass.states.get("sensor.peek_delivered_today")
    assert state.state == "2"
    assert [item["id"] for item in state.attributes["parcels"]] == ["a1", "a2"]


async def test_french(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, entity_registry: er.EntityRegistry
) -> None:
    """In French, the names are French; Home Assistant keeps units in English, so that statistics don't change."""
    hass.config.language = "fr"
    entry = await set_up(hass, aioclient_mock)
    entity_id = entity_registry.async_get_entity_id("sensor", DOMAIN, f"{entry.entry_id}_on_the_way")
    assert entity_id == "sensor.peek_en_route"
    state = hass.states.get(entity_id)
    assert state.attributes["friendly_name"] == "Peek En route"
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == "parcels"


async def test_device(
    hass: HomeAssistant, setup_integration: MockConfigEntry, device_registry: dr.DeviceRegistry
) -> None:
    """The entities belong to one service device, "Peek", linking to Peek."""
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, setup_integration.entry_id), setup_integration.entry_id
    )
    assert device.name == "Peek"
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.configuration_url == URL


def test_parcels_not_recorded() -> None:
    """The recorder keeps the counts, not the parcels' details."""
    assert "parcels" in PeekSensor._unrecorded_attributes
