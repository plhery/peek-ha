"""Peek's actions: add parcels from a text, archive one, and list them."""

from collections.abc import Awaitable
from typing import Any

import probatio

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .api import (
    PeekAuthError,
    PeekError,
    PeekRateLimitError,
    PeekScopeError,
    PeekToolError,
)
from .const import DOMAIN
from .coordinator import PeekConfigEntry
from .model import summary

SERVICE_ADD_PARCELS = "add_parcels"
SERVICE_ARCHIVE_PARCEL = "archive_parcel"
SERVICE_GET_PARCELS = "get_parcels"

ATTR_TEXT = "text"
ATTR_NAME = "name"
ATTR_PARCEL = "parcel"
ATTR_STATUS = "status"
ATTR_SORT = "sort"
ATTR_SEARCH = "search"
ATTR_LIMIT = "limit"

# What Peek's API takes.
STATUSES = ["active", "attention", "today", "week", "delivered", "archived", "all"]
SORTS = ["expected", "delivered", "updated", "added"]
MOST_TEXT = 16_000
MOST_NAME = 80
MOST_SEARCH = 100
MOST_LISTED = 50

ADD_PARCELS_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_TEXT): probatio.All(cv.string, probatio.Length(min=1, max=MOST_TEXT)),
        probatio.Optional(ATTR_NAME): probatio.All(cv.string, probatio.Length(max=MOST_NAME)),
    }
)
ARCHIVE_PARCEL_SCHEMA = probatio.Schema(
    {probatio.Required(ATTR_PARCEL): probatio.All(cv.string, probatio.Length(min=1, max=100))}
)
GET_PARCELS_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_STATUS): probatio.In(STATUSES),
        probatio.Optional(ATTR_SORT): probatio.In(SORTS),
        probatio.Optional(ATTR_SEARCH): probatio.All(cv.string, probatio.Length(max=MOST_SEARCH)),
        probatio.Optional(ATTR_LIMIT): probatio.All(probatio.Coerce(int), probatio.Range(min=1, max=MOST_LISTED)),
    }
)


def _entry(hass: HomeAssistant) -> PeekConfigEntry:
    """The loaded Peek entry."""
    entries: list[PeekConfigEntry] = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    return entries[0]


async def _ask[T](hass: HomeAssistant, entry: PeekConfigEntry, call: Awaitable[T]) -> T:
    """Wait for a call to Peek, as an error the user can read when it fails."""
    try:
        return await call
    except (PeekAuthError, PeekScopeError) as err:
        entry.async_start_reauth(hass)
        key = "missing_scope" if isinstance(err, PeekScopeError) else "auth_failed"
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key=key) from err
    except PeekRateLimitError as err:
        raise HomeAssistantError(translation_domain=DOMAIN, translation_key="rate_limited") from err
    except PeekError as err:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="request_failed",
            translation_placeholders={"error": str(err)},
        ) from err


async def _add_parcels(call: ServiceCall) -> ServiceResponse:
    """Add the tracking numbers a text holds, such as a shipping email's."""
    entry = _entry(call.hass)
    runtime = entry.runtime_data
    additions = await _ask(
        call.hass,
        entry,
        runtime.client.add_parcels(call.data[ATTR_TEXT], call.data.get(ATTR_NAME)),
    )
    await runtime.coordinator.async_request_refresh()
    parcels: list[Any] = []
    for addition in additions:
        outcome: dict[str, Any] = {
            "tracking_number": addition.get("trackingNumber"),
            "carrier": addition.get("carrier"),
            "outcome": addition.get("outcome"),
        }
        if "id" in addition:
            outcome["id"] = addition["id"]
        if "reason" in addition:
            outcome["reason"] = addition["reason"]
        parcels.append(outcome)
    return {"parcels": parcels}


async def _archive_parcel(call: ServiceCall) -> None:
    """Move a parcel to the archive."""
    entry = _entry(call.hass)
    runtime = entry.runtime_data
    named = call.data[ATTR_PARCEL]

    async def archive() -> str:
        try:
            return await runtime.client.archive_parcel(named)
        except PeekToolError as err:
            # Peek refuses only a parcel the account doesn't have.
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="parcel_not_found",
                translation_placeholders={"parcel": named},
            ) from err

    await _ask(call.hass, entry, archive())
    await runtime.coordinator.async_request_refresh()


async def _get_parcels(call: ServiceCall) -> ServiceResponse:
    """The parcels that match, read from Peek now."""
    entry = _entry(call.hass)
    answer = await _ask(
        call.hass,
        entry,
        entry.runtime_data.client.parcels(
            status=call.data.get(ATTR_STATUS),
            sort=call.data.get(ATTR_SORT),
            search=call.data.get(ATTR_SEARCH),
            limit=call.data.get(ATTR_LIMIT),
        ),
    )
    return {
        "total": answer["total"],
        "parcels": [summary(parcel) for parcel in answer["parcels"]],
    }


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register Peek's actions."""
    hass.services.async_register(
        DOMAIN,
        SERVICE_ADD_PARCELS,
        _add_parcels,
        schema=ADD_PARCELS_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_ARCHIVE_PARCEL,
        _archive_parcel,
        schema=ARCHIVE_PARCEL_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PARCELS,
        _get_parcels,
        schema=GET_PARCELS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
