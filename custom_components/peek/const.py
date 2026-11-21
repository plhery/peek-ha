"""Constants for the Peek integration."""

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "peek"
LOGGER = logging.getLogger(__package__)

# Peek's public address. A configuration.yaml `peek:` block may point the integration at another one (a local
# development server); nothing in the UI changes it.
DEFAULT_URL: Final = "https://peektracker.com"
# The integration's OAuth client id: the address of the Client ID Metadata Document Peek publishes for it.
CLIENT_ID_PATH: Final = "/oauth/clients/home-assistant.json"
AUTHORIZE_PATH: Final = "/oauth/authorize"
TOKEN_PATH: Final = "/oauth/token"
REVOKE_PATH: Final = "/oauth/revoke"
# Reading, adding, and editing (renaming, changing the carrier, notifications, archiving, restoring). A connection
# signed in before editing came lacks `parcels:edit`: Peek refuses its edits, and the first one asks to sign in again.
SCOPES: Final = "parcels:read parcels:write parcels:edit"

CONF_CLIENT_ID: Final = "client_id"
CONF_URL: Final = "url"

# How often the parcels are read: often while one arrives today, else every half hour.
FAST_INTERVAL: Final = timedelta(minutes=10)
SLOW_INTERVAL: Final = timedelta(minutes=30)
# Each refresh reads the parcels on their way and the latest deliveries.
ACTIVE_LIMIT: Final = 50
DELIVERED_LIMIT: Final = 10

ATTR_PARCELS: Final = "parcels"

# Peek's stages, from its API's `status`.
STAGES: Final = (
    "pending",
    "registered",
    "accepted",
    "in_transit",
    "customs",
    "exception",
    "out_for_delivery",
    "failed_attempt",
    "ready_for_pickup",
    "delivered",
    "returned",
)

# The kinds of change the "Parcel updates" event entity reports.
EVENT_ADDED: Final = "added"
EVENT_STATUS_CHANGED: Final = "status_changed"
EVENT_OUT_FOR_DELIVERY: Final = "out_for_delivery"
EVENT_DELIVERED: Final = "delivered"
EVENT_NEEDS_ATTENTION: Final = "needs_attention"
EVENT_EXPECTED_DELIVERY_CHANGED: Final = "expected_delivery_changed"
EVENT_TYPES: Final = [
    EVENT_ADDED,
    EVENT_STATUS_CHANGED,
    EVENT_OUT_FOR_DELIVERY,
    EVENT_DELIVERED,
    EVENT_NEEDS_ATTENTION,
    EVENT_EXPECTED_DELIVERY_CHANGED,
]

# The card, served by the integration.
CARD_FILE: Final = "peek-parcels-card.js"
