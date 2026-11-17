"""Diagnostics for Peek, without the parcels' names, numbers, places or the tokens."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .coordinator import PeekConfigEntry
from .oauth import async_ensure_oauth

TO_REDACT = {
    # The sign-in.
    "access_token",
    "refresh_token",
    # What would tell whose parcels these are.
    "id",
    "name",
    "trackingNumber",
    "statusText",
    "description",
    "location",
    "pickupPoint",
    "sender",
}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: PeekConfigEntry) -> dict[str, Any]:
    """The entry, the reads' state and the parcels with their details left out.

    An entry whose first read failed has no runtime data yet, and is when diagnostics help most.
    """
    config = async_ensure_oauth(hass)
    result: dict[str, Any] = {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "state": entry.state.value,
        "peek": {"url": config.url, "client_id": config.client_id, "overridden": config.overridden},
    }
    if (runtime := getattr(entry, "runtime_data", None)) is None:
        return result
    coordinator = runtime.coordinator
    data = coordinator.data
    return {
        **result,
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception) if coordinator.last_exception else None,
            "update_interval": str(coordinator.update_interval),
        },
        "active_total": data.active_total,
        "active": async_redact_data(data.active, TO_REDACT),
        "delivered": async_redact_data(data.delivered, TO_REDACT),
    }
