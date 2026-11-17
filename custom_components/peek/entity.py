"""The base of Peek's entities: one service device, "Peek"."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PeekCoordinator


class PeekEntity(CoordinatorEntity[PeekCoordinator]):
    """An entity of the Peek device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: PeekCoordinator, key: str) -> None:
        """Name the entity by its key."""
        super().__init__(coordinator)
        entry = coordinator.config_entry
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Peek",
            manufacturer="Peek",
            entry_type=DeviceEntryType.SERVICE,
            configuration_url=coordinator.client.url,
        )
