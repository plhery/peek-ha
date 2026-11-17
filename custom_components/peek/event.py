"""Peek's "Parcel updates": an event each time a read finds a parcel added or moved on."""

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import Parcel
from .const import EVENT_TYPES
from .coordinator import PeekConfigEntry, PeekCoordinator
from .entity import PeekEntity
from .model import PeekData, event_payload, parcel_changes

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PeekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the event entity."""
    async_add_entities([PeekParcelUpdates(entry.runtime_data.coordinator)])


class PeekParcelUpdates(PeekEntity, EventEntity):
    """Compares each read with the one before; the first read only sets the baseline."""

    _attr_event_types = EVENT_TYPES

    def __init__(self, coordinator: PeekCoordinator) -> None:
        """Start from the read made at setup."""
        super().__init__(coordinator, "parcel_updates")
        self._read: PeekData = coordinator.data
        self._seen: dict[str, Parcel] = coordinator.data.by_id()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Fire an event for each change since the last read."""
        data = self.coordinator.data
        if data is self._read:
            # No new read: the day changed, or a read failed.
            super()._handle_coordinator_update()
            return
        changes = parcel_changes(self._seen, [*data.active, *data.delivered])
        self._read = data
        self._seen = data.by_id()
        if not changes:
            super()._handle_coordinator_update()
            return
        for kind, parcel in changes:
            self._trigger_event(kind, event_payload(parcel))
            self.async_write_ha_state()
