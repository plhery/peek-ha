"""Reads the account's parcels from Peek, more often on a day a parcel arrives."""

from dataclasses import dataclass
from datetime import date, datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    PeekAuthError,
    PeekClient,
    PeekError,
    PeekRateLimitError,
    PeekScopeError,
)
from .const import (
    ACTIVE_LIMIT,
    DELIVERED_LIMIT,
    DOMAIN,
    FAST_INTERVAL,
    LOGGER,
    SLOW_INTERVAL,
)
from .model import PeekData


def local_today() -> date:
    """Today, in Home Assistant's time zone."""
    return dt_util.now().date()


class PeekCoordinator(DataUpdateCoordinator[PeekData]):
    """The parcels on their way and the latest deliveries, read together."""

    config_entry: PeekConfigEntry

    def __init__(self, hass: HomeAssistant, entry: PeekConfigEntry, client: PeekClient) -> None:
        """Read every half hour until a parcel arrives today."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=SLOW_INTERVAL,
        )
        self.client = client

    @callback
    def async_track_midnight(self) -> None:
        """Redraw the entities when the day changes: "today" moves without a new read."""
        self.config_entry.async_on_unload(
            async_track_time_change(self.hass, self._async_new_day, hour=0, minute=0, second=0)
        )

    @callback
    def _async_new_day(self, now: datetime) -> None:
        # Tracked once the first read succeeded; a failed read keeps the last data.
        self.async_update_listeners()

    async def _async_update_data(self) -> PeekData:
        """Read both lists; a refused token asks the user to sign in again."""
        try:
            active = await self.client.parcels(status="active", limit=ACTIVE_LIMIT)
            delivered = await self.client.parcels(status="delivered", sort="delivered", limit=DELIVERED_LIMIT)
        except PeekAuthError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="auth_failed") from err
        except PeekScopeError as err:
            raise ConfigEntryAuthFailed(translation_domain=DOMAIN, translation_key="missing_scope") from err
        except PeekRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                retry_after=err.retry_after,
            ) from err
        except PeekError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        data = PeekData.from_lists(active, delivered)
        self.update_interval = FAST_INTERVAL if data.busy(local_today()) else SLOW_INTERVAL
        return data


@dataclass(slots=True)
class PeekRuntime:
    """What a loaded entry keeps: the client and the coordinator."""

    client: PeekClient
    coordinator: PeekCoordinator


type PeekConfigEntry = ConfigEntry[PeekRuntime]
