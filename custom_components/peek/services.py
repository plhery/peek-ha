"""Peek's actions: add parcels from a text, archive, restore and edit one, and list them."""

from collections.abc import Awaitable, Callable
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
    PeekClient,
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
SERVICE_RESTORE_PARCEL = "restore_parcel"
SERVICE_RENAME_PARCEL = "rename_parcel"
SERVICE_CHANGE_CARRIER = "change_carrier"
SERVICE_SET_PARCEL_NOTIFICATIONS = "set_parcel_notifications"
SERVICE_GET_PARCELS = "get_parcels"

ATTR_TEXT = "text"
ATTR_NAME = "name"
ATTR_PARCEL = "parcel"
ATTR_CARRIER = "carrier"
ATTR_POSTCODE = "postcode"
ATTR_NOTIFICATIONS = "notifications"
ATTR_STATUS = "status"
ATTR_SORT = "sort"
ATTR_SEARCH = "search"
ATTR_LIMIT = "limit"

# What Peek's API takes.
STATUSES = ["active", "attention", "today", "week", "delivered", "archived", "all"]
SORTS = ["expected", "delivered", "updated", "added"]
MOST_TEXT = 16_000
MOST_NAME = 80
MOST_PARCEL = 100
MOST_CARRIER = 60
MOST_POSTCODE = 20
MOST_SEARCH = 100
MOST_LISTED = 50

# The start of Peek's words for the refusals the integration says in the user's language; any other comes in Peek's
# words.
NO_PARCEL = "No such parcel"
NO_CARRIER = "Peek has no carrier with this id"

ADD_PARCELS_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_TEXT): probatio.All(cv.string, probatio.Length(min=1, max=MOST_TEXT)),
        probatio.Optional(ATTR_NAME): probatio.All(cv.string, probatio.Length(max=MOST_NAME)),
    }
)
# A parcel is named by its id or its tracking number.
PARCEL = probatio.All(cv.string, probatio.Length(min=1, max=MOST_PARCEL))
PARCEL_SCHEMA = probatio.Schema({probatio.Required(ATTR_PARCEL): PARCEL})
RENAME_PARCEL_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_PARCEL): PARCEL,
        # "" clears the name.
        probatio.Required(ATTR_NAME): probatio.All(cv.string, probatio.Length(max=MOST_NAME)),
    }
)
CHANGE_CARRIER_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_PARCEL): PARCEL,
        probatio.Required(ATTR_CARRIER): probatio.All(cv.string, probatio.Length(min=1, max=MOST_CARRIER)),
        probatio.Optional(ATTR_POSTCODE): probatio.All(cv.string, probatio.Length(max=MOST_POSTCODE)),
    }
)
SET_PARCEL_NOTIFICATIONS_SCHEMA = probatio.Schema(
    {
        probatio.Required(ATTR_PARCEL): PARCEL,
        probatio.Required(ATTR_NOTIFICATIONS): cv.boolean,
    }
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


async def _ask[T](
    hass: HomeAssistant, entry: PeekConfigEntry, call: Awaitable[T], missing_scope: str = "missing_scope"
) -> T:
    """Wait for a call to Peek, as an error the user can read when it fails.

    A refused token or a missing scope asks the user to sign in again; `missing_scope` names the message for the
    latter.
    """
    try:
        return await call
    except (PeekAuthError, PeekScopeError) as err:
        entry.async_start_reauth(hass)
        key = missing_scope if isinstance(err, PeekScopeError) else "auth_failed"
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


def _refusal(call: ServiceCall, err: PeekToolError) -> ServiceValidationError:
    """Peek's refusal of a change, such as a parcel the account doesn't have, as the user's mistake."""
    text = str(err)
    if text.startswith(NO_PARCEL):
        return ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="parcel_not_found",
            translation_placeholders={"parcel": call.data[ATTR_PARCEL]},
        )
    if ATTR_CARRIER in call.data and text.startswith(NO_CARRIER):
        return ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="carrier_not_found",
            translation_placeholders={"carrier": call.data[ATTR_CARRIER]},
        )
    return ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="refused",
        translation_placeholders={"error": text},
    )


async def _change(
    call: ServiceCall, change: Callable[[PeekClient], Awaitable[str]], missing_scope: str = "missing_scope"
) -> None:
    """Change one parcel in Peek, then read the parcels again."""
    entry = _entry(call.hass)
    runtime = entry.runtime_data

    async def ask() -> str:
        try:
            return await change(runtime.client)
        except PeekToolError as err:
            raise _refusal(call, err) from err

    await _ask(call.hass, entry, ask(), missing_scope)
    await runtime.coordinator.async_request_refresh()


async def _edit(call: ServiceCall, change: Callable[[PeekClient], Awaitable[str]]) -> None:
    """A change under the `parcels:edit` scope, which a connection signed in before editing came lacks."""
    await _change(call, change, "missing_edit_scope")


async def _archive_parcel(call: ServiceCall) -> None:
    """Move a parcel to the archive."""
    await _edit(call, lambda client: client.archive_parcel(call.data[ATTR_PARCEL]))


async def _restore_parcel(call: ServiceCall) -> None:
    """Bring a parcel back from the archive."""
    await _edit(call, lambda client: client.restore_parcel(call.data[ATTR_PARCEL]))


async def _rename_parcel(call: ServiceCall) -> None:
    """Give a parcel a name, or clear it."""
    await _edit(call, lambda client: client.rename_parcel(call.data[ATTR_PARCEL], call.data[ATTR_NAME]))


async def _change_carrier(call: ServiceCall) -> None:
    """Set the carrier that delivers a parcel."""
    await _edit(
        call,
        lambda client: client.change_carrier(
            call.data[ATTR_PARCEL], call.data[ATTR_CARRIER], call.data.get(ATTR_POSTCODE)
        ),
    )


async def _set_parcel_notifications(call: ServiceCall) -> None:
    """Turn Peek's notifications about a parcel on or off."""
    await _edit(
        call,
        lambda client: client.set_parcel_notifications(call.data[ATTR_PARCEL], call.data[ATTR_NOTIFICATIONS]),
    )


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
    hass.services.async_register(DOMAIN, SERVICE_ARCHIVE_PARCEL, _archive_parcel, schema=PARCEL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RESTORE_PARCEL, _restore_parcel, schema=PARCEL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_RENAME_PARCEL, _rename_parcel, schema=RENAME_PARCEL_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_CHANGE_CARRIER, _change_carrier, schema=CHANGE_CARRIER_SCHEMA)
    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PARCEL_NOTIFICATIONS,
        _set_parcel_notifications,
        schema=SET_PARCEL_NOTIFICATIONS_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_GET_PARCELS,
        _get_parcels,
        schema=GET_PARCELS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )
