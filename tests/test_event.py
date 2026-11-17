"""Tests for Peek's "Parcel updates" event entity."""

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from custom_components.peek.model import parcel_changes

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
    LAMP,
    PARCELS_URL,
    answer,
    parcel,
)

UPDATES = "event.peek_parcel_updates"
SCARF = parcel(
    "5d1b2f9e-8a43-4d5e-9c0b-2f7e6a1d3c48",
    "Wool scarf",
    "Royal Mail",
    "QJ123456785GB",
    "accepted",
    "2026-11-20",
    sender="Highland Knits Demo",
)


@pytest.fixture
def fired(hass: HomeAssistant) -> list[tuple[str, dict[str, Any]]]:
    """The events the entity fires, as (type, data)."""
    found: list[tuple[str, dict[str, Any]]] = []

    @callback
    def listen(event: Event[EventStateChangedData]) -> None:
        state = event.data["new_state"]
        if state and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            attributes = dict(state.attributes)
            found.append((attributes.pop("event_type"), attributes))

    async_track_state_change_event(hass, [UPDATES], listen)
    return found


async def read(
    hass: HomeAssistant,
    entry: MockConfigEntry,
    mock: AiohttpClientMocker,
    active: dict,
    delivered: dict | None = None,
    **kwargs,
) -> None:
    """One more read of Peek, answered with these lists."""
    mock.clear_requests()
    if kwargs:
        mock.get(PARCELS_URL, params=ACTIVE_QUERY, **kwargs)
    else:
        mock.get(PARCELS_URL, params=ACTIVE_QUERY, json=active)
        mock.get(PARCELS_URL, params=DELIVERED_QUERY, json=delivered or answer(DOCK, LAMP, status="delivered"))
    await entry.runtime_data.coordinator.async_refresh()
    await hass.async_block_till_done()


async def test_first_read_fires_nothing(hass: HomeAssistant, setup_integration: MockConfigEntry) -> None:
    """The read at setup is the baseline."""
    state = hass.states.get(UPDATES)
    assert state.state == STATE_UNKNOWN
    assert state.attributes["event_types"] == [
        "added",
        "status_changed",
        "out_for_delivery",
        "delivered",
        "needs_attention",
        "expected_delivery_changed",
    ]


async def test_changes(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_parcels: AiohttpClientMocker, fired: list
) -> None:
    """Each change is one event, in the read's order."""
    await read(
        hass,
        setup_integration,
        mock_parcels,
        answer(
            dict(JACKET, status="out_for_delivery", expectedDelivery="2026-11-17"),
            BOWLS,
            dict(HOSE, status="in_transit", needsAttention=None),
            dict(BOOKS, expectedDelivery="2026-11-20"),
            dict(CASE, needsAttention="customs_documents"),
            SCARF,
        ),
        answer(
            dict(BOOTS, status="delivered", deliveredAt="2026-11-17T12:00:00+00:00"),
            DOCK,
            LAMP,
            status="delivered",
        ),
    )
    assert [kind for kind, _ in fired] == [
        "out_for_delivery",
        "status_changed",
        "expected_delivery_changed",
        "needs_attention",
        "added",
        "delivered",
    ]
    assert fired[4][1] == {
        "event_types": fired[4][1]["event_types"],
        "friendly_name": "Peek Parcel updates",
        "id": SCARF["id"],
        "name": "Wool scarf",
        "carrier": "Royal Mail",
        "status": "accepted",
        "status_text": "Scanned at depot",
        "needs_attention": None,
        "expected_delivery": "2026-11-20",
        "location": "Bern",
    }
    # Without a name, the shop names the parcel.
    assert fired[2][1]["name"] == "Demo Books"


async def test_no_change_fires_nothing(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_parcels: AiohttpClientMocker, fired: list
) -> None:
    """The same parcels again: nothing to tell."""
    await read(hass, setup_integration, mock_parcels, answer(BOOTS, BOWLS, JACKET, HOSE, BOOKS, CASE))
    assert fired == []
    assert hass.states.get(UPDATES).state == STATE_UNKNOWN


async def test_changes_during_an_outage(
    hass: HomeAssistant, setup_integration: MockConfigEntry, mock_parcels: AiohttpClientMocker, fired: list
) -> None:
    """What changed while Peek couldn't be read is told by the next read that works."""
    await read(hass, setup_integration, mock_parcels, {}, status=500)
    assert hass.states.get(UPDATES).state == STATE_UNAVAILABLE
    await read(
        hass,
        setup_integration,
        mock_parcels,
        answer(dict(BOOTS, status="failed_attempt", needsAttention="failed_attempt")),
    )
    assert [kind for kind, _ in fired] == ["needs_attention"]


def test_change_rules() -> None:
    """What counts as a change, and what doesn't."""
    before = {item["id"]: item for item in (BOOTS, JACKET, BOWLS)}
    assert parcel_changes(before, [dict(JACKET, status="customs", needsAttention="customs")]) == [
        ("needs_attention", dict(JACKET, status="customs", needsAttention="customs"))
    ]
    # A delivered parcel's day doesn't move; a parcel that is new and already delivered or archived isn't "added".
    assert parcel_changes(before, [dict(BOOTS, status="delivered", expectedDelivery="2026-11-18")])[0][0] == "delivered"
    assert parcel_changes({DOCK["id"]: DOCK}, [dict(DOCK, expectedDelivery="2026-11-19")]) == []
    assert parcel_changes({}, [DOCK, dict(SCARF, archived=True)]) == []
    # Attention that goes away, or stays the same, isn't news.
    assert parcel_changes(before, [dict(BOWLS, needsAttention=None)]) == []
    assert parcel_changes(before, [BOWLS]) == []
