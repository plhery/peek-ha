"""Peek's sensors: parcels on their way, arriving today, needing you and delivered today, and the next delivery day."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, tzinfo
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import ATTR_PARCELS
from .coordinator import PeekConfigEntry, PeekCoordinator, local_today
from .entity import PeekEntity
from .model import SECTION_ATTENTION, SECTION_TODAY, PeekData, summary

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class PeekSensorDescription(SensorEntityDescription):
    """A Peek sensor: its value, and the parcels it lists, from a read and today's date."""

    value_fn: Callable[[PeekData, date, tzinfo], int | date | None]
    parcels_fn: Callable[[PeekData, date, tzinfo], list[dict[str, Any]]] | None = None


def _next_delivery(data: PeekData, today: date) -> date | None:
    found = data.next_delivery(today)
    return found[0] if found else None


def _next_parcels(data: PeekData, today: date) -> list[dict[str, Any]]:
    found = data.next_delivery(today)
    return [summary(parcel, today) for parcel in found[1]] if found else []


COUNT = {
    "state_class": SensorStateClass.MEASUREMENT,
    "suggested_display_precision": 0,
}

SENSORS: tuple[PeekSensorDescription, ...] = (
    PeekSensorDescription(
        key="on_the_way",
        **COUNT,
        value_fn=lambda data, today, tz: data.active_total,
        parcels_fn=lambda data, today, tz: [summary(parcel, today) for parcel in data.active],
    ),
    PeekSensorDescription(
        key="arriving_today",
        **COUNT,
        value_fn=lambda data, today, tz: len(data.in_section(SECTION_TODAY, today)),
    ),
    PeekSensorDescription(
        key="needs_attention",
        **COUNT,
        value_fn=lambda data, today, tz: len(data.in_section(SECTION_ATTENTION, today)),
    ),
    PeekSensorDescription(
        key="delivered_today",
        **COUNT,
        value_fn=lambda data, today, tz: len(data.delivered_on(today, tz)),
        parcels_fn=lambda data, today, tz: [summary(parcel) for parcel in data.delivered_on(today, tz)],
    ),
    PeekSensorDescription(
        key="next_delivery",
        device_class=SensorDeviceClass.DATE,
        value_fn=lambda data, today, tz: _next_delivery(data, today),
        parcels_fn=lambda data, today, tz: _next_parcels(data, today),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PeekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Peek's sensors."""
    coordinator = entry.runtime_data.coordinator
    async_add_entities(PeekSensor(coordinator, description) for description in SENSORS)


class PeekSensor(PeekEntity, SensorEntity):
    """A count, or a day, read from the parcels."""

    entity_description: PeekSensorDescription
    # The parcels' details change at every read: the recorder keeps the counts only.
    _unrecorded_attributes = frozenset({ATTR_PARCELS})

    def __init__(self, coordinator: PeekCoordinator, description: PeekSensorDescription) -> None:
        """Set up one of the sensors."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> int | date | None:
        """The count, or the day."""
        return self.entity_description.value_fn(self.coordinator.data, local_today(), dt_util.get_default_time_zone())

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """The parcels the sensor counts, for cards and templates."""
        if self.entity_description.parcels_fn is None:
            return None
        return {
            ATTR_PARCELS: self.entity_description.parcels_fn(
                self.coordinator.data, local_today(), dt_util.get_default_time_zone()
            )
        }
