"""How the integration reads Peek's parcels: their days, the list's sections, and what changed between two reads.

"Today" is always the day in Home Assistant's time zone, which the caller passes in.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from typing import Any

from .api import Parcel, ParcelList
from .const import (
    EVENT_ADDED,
    EVENT_DELIVERED,
    EVENT_EXPECTED_DELIVERY_CHANGED,
    EVENT_NEEDS_ATTENTION,
    EVENT_OUT_FOR_DELIVERY,
    EVENT_STATUS_CHANGED,
)

# The sections of Peek's list, in its order.
SECTION_ATTENTION = "attention"
SECTION_TODAY = "today"
SECTION_ACTIVE = "active"


def expected_day(parcel: Parcel) -> date | None:
    """The day Peek expects the parcel, if it knows one."""
    value = (parcel.get("expectedDelivery") or "").strip()
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def delivered_day(parcel: Parcel, tz: tzinfo) -> date | None:
    """The day the parcel was delivered, in `tz`; a carrier that gives only a day gives that day."""
    value = (parcel.get("deliveredAt") or "").strip()
    if not value:
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    return moment.astimezone(tz).date() if moment.tzinfo else moment.date()


def arrives_today(parcel: Parcel, today: date) -> bool:
    """Whether the parcel is out for delivery or expected today."""
    return parcel.get("status") == "out_for_delivery" or expected_day(parcel) == today


def section(parcel: Parcel, today: date) -> str:
    """The section of Peek's list the parcel sits in: needs attention, arriving today, or on the way."""
    if parcel.get("needsAttention"):
        return SECTION_ATTENTION
    if arrives_today(parcel, today):
        return SECTION_TODAY
    return SECTION_ACTIVE


def summary(parcel: Parcel, today: date | None = None) -> dict[str, Any]:
    """A parcel as the integration's attributes, events, actions and tools give it."""
    last = parcel.get("lastUpdate") or {}
    result: dict[str, Any] = {
        "id": parcel.get("id"),
        "name": parcel.get("name"),
        "carrier": parcel.get("carrier"),
        "tracking_number": parcel.get("trackingNumber"),
        "status": parcel.get("status"),
        "status_text": parcel.get("statusText"),
        "needs_attention": parcel.get("needsAttention"),
        "expected_delivery": parcel.get("expectedDelivery"),
        "delivered_at": parcel.get("deliveredAt"),
        "last_update": last.get("time"),
        "location": last.get("location"),
        "pickup_point": parcel.get("pickupPoint"),
        "sender": parcel.get("sender"),
        "archived": bool(parcel.get("archived")),
    }
    if today is not None:
        result["section"] = section(parcel, today)
    return result


def event_payload(parcel: Parcel) -> dict[str, Any]:
    """What a "Parcel updates" event says about its parcel."""
    last = parcel.get("lastUpdate") or {}
    return {
        "id": parcel.get("id"),
        "name": parcel.get("name") or parcel.get("sender"),
        "carrier": parcel.get("carrier"),
        "status": parcel.get("status"),
        "status_text": parcel.get("statusText"),
        "needs_attention": parcel.get("needsAttention"),
        "expected_delivery": parcel.get("expectedDelivery"),
        "location": last.get("location"),
    }


@dataclass(frozen=True, slots=True)
class PeekData:
    """One read of the account: the parcels on their way, and the latest deliveries."""

    active: list[Parcel]
    active_total: int
    delivered: list[Parcel]

    @classmethod
    def from_lists(cls, active: ParcelList, delivered: ParcelList) -> PeekData:
        """Both of a refresh's lists."""
        return cls(
            active=list(active["parcels"]),
            active_total=int(active.get("total", len(active["parcels"]))),
            delivered=list(delivered["parcels"]),
        )

    def by_id(self) -> dict[str, Parcel]:
        """Every parcel this read holds, by id."""
        return {parcel["id"]: parcel for parcel in (*self.active, *self.delivered)}

    def in_section(self, name: str, today: date) -> list[Parcel]:
        """The parcels on their way in one of the list's sections."""
        return [parcel for parcel in self.active if section(parcel, today) == name]

    def delivered_on(self, day: date, tz: tzinfo) -> list[Parcel]:
        """The parcels delivered on `day` that are still in the list (not archived)."""
        return [
            parcel
            for parcel in self.delivered
            if parcel.get("status") == "delivered" and not parcel.get("archived") and delivered_day(parcel, tz) == day
        ]

    def next_delivery(self, today: date) -> tuple[date, list[Parcel]] | None:
        """The next day a parcel on its way is expected, today or later, and the parcels expected then."""
        days = [(day, parcel) for parcel in self.active if (day := expected_day(parcel)) is not None and day >= today]
        if not days:
            return None
        first = min(day for day, _ in days)
        return first, [parcel for day, parcel in days if day == first]

    def busy(self, today: date) -> bool:
        """Whether a parcel arrives today, so that Peek is read more often."""
        return any(arrives_today(parcel, today) for parcel in self.active)


def _change(before: Parcel, after: Parcel) -> str | None:
    """The kind of change from one read of a parcel to the next, if any worth telling."""
    status = after.get("status")
    attention = after.get("needsAttention")
    new_attention = bool(attention) and attention != before.get("needsAttention")
    if status != before.get("status"):
        if status == "delivered":
            return EVENT_DELIVERED
        if status == "out_for_delivery":
            return EVENT_OUT_FOR_DELIVERY
        return EVENT_NEEDS_ATTENTION if new_attention else EVENT_STATUS_CHANGED
    if new_attention:
        return EVENT_NEEDS_ATTENTION
    if status != "delivered" and expected_day(after) != expected_day(before):
        return EVENT_EXPECTED_DELIVERY_CHANGED
    return None


def parcel_changes(before: Mapping[str, Parcel], after: Iterable[Parcel]) -> list[tuple[str, Parcel]]:
    """What changed between two reads, in the newer read's order: new parcels and the parcels that moved on."""
    found: list[tuple[str, Parcel]] = []
    for parcel in after:
        previous = before.get(parcel["id"])
        if previous is None:
            if parcel.get("status") != "delivered" and not parcel.get("archived"):
                found.append((EVENT_ADDED, parcel))
            continue
        if kind := _change(previous, parcel):
            found.append((kind, parcel))
    return found


def parcel_title(parcel: Parcel) -> str:
    """What to call a parcel: its name, else its shop, else its carrier and number."""
    return parcel.get("name") or parcel.get("sender") or f"{parcel.get('carrier')} {parcel.get('trackingNumber')}"
