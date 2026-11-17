"""Peek's "Deliveries" calendar: each parcel on the day Peek expects it, or the day it came."""

from datetime import date, datetime, time, timedelta

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import PeekConfigEntry, PeekCoordinator, local_today
from .entity import PeekEntity
from .model import delivered_day, expected_day, parcel_title

PARALLEL_UPDATES = 0
DAY = timedelta(days=1)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PeekConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the calendar."""
    async_add_entities([PeekCalendar(entry.runtime_data.coordinator)])


class PeekCalendar(PeekEntity, CalendarEntity):
    """All-day events: a parcel on its way on its expected day, a delivered one on the day it came."""

    def __init__(self, coordinator: PeekCoordinator) -> None:
        """Set up the calendar."""
        super().__init__(coordinator, "deliveries")

    def _events(self) -> list[CalendarEvent]:
        data = self.coordinator.data
        tz = dt_util.get_default_time_zone()
        events: list[CalendarEvent] = []
        for parcel in data.active:
            if (day := expected_day(parcel)) is not None:
                events.append(self._event(parcel, day, "expected"))
        for parcel in data.delivered:
            if parcel.get("status") == "delivered" and (day := delivered_day(parcel, tz)):
                events.append(self._event(parcel, day, "delivered"))
        return sorted(events, key=lambda event: (event.start, event.summary))

    @staticmethod
    def _event(parcel: dict, day: date, kind: str) -> CalendarEvent:
        return CalendarEvent(
            start=day,
            end=day + DAY,
            summary=f"{parcel_title(parcel)} · {parcel.get('carrier')}",
            description=parcel.get("statusText"),
            location=parcel.get("pickupPoint"),
            uid=f"{parcel['id']}-{kind}",
        )

    @property
    def event(self) -> CalendarEvent | None:
        """Today's first delivery, else the next one."""
        today = local_today()
        return next((event for event in self._events() if event.end > today), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        """The deliveries between two moments."""
        tz = dt_util.get_default_time_zone()

        def moment(day: date) -> datetime:
            return datetime.combine(day, time.min, tz)

        return [event for event in self._events() if moment(event.start) < end_date and moment(event.end) > start_date]
