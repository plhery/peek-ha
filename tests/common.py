"""Synthetic parcels for the tests: made-up shops, names and tracking numbers."""

from copy import deepcopy
from typing import Any

URL = "https://peektracker.com"
CLIENT_ID = f"{URL}/oauth/clients/home-assistant.json"
PARCELS_URL = f"{URL}/api/parcels"
MCP_URL = f"{URL}/mcp"
TOKEN_URL = f"{URL}/oauth/token"
REVOKE_URL = f"{URL}/oauth/revoke"

ACTIVE_QUERY = {"status": "active", "limit": "50"}
DELIVERED_QUERY = {"status": "delivered", "sort": "delivered", "limit": "10"}


def parcel(
    id: str,
    name: str | None,
    carrier: str,
    number: str,
    status: str,
    expected: str | None,
    *,
    attention: str | None = None,
    delivered_at: str | None = None,
    location: str | None = "Bern",
    sender: str | None = "Example Shop",
    pickup_point: str | None = None,
    archived: bool = False,
) -> dict[str, Any]:
    """A parcel as Peek's API gives it."""
    text = {"delivered": "Delivered", "out_for_delivery": "Out for delivery today"}.get(status, "Scanned at depot")
    return {
        "id": id,
        "name": name,
        "carrier": carrier,
        "trackingNumber": number,
        "status": status,
        "statusText": text,
        "needsAttention": attention,
        "expectedDelivery": expected,
        "deliveredAt": delivered_at,
        "lastUpdate": {"time": "2026-11-17T09:00:00+00:00", "description": text, "location": location},
        "pickupPoint": pickup_point,
        "sender": sender,
        "archived": archived,
        "addedAt": "2026-11-10T08:00:00+00:00",
    }


# "Today" in the tests is Tuesday 17 November 2026, in Zurich.
BOOTS = parcel(
    "0ca5a2d0-b0f2-45ef-97b1-0f542ef30b98",
    "Hiking boots",
    "UPS",
    "1Z4E7W960398127345",
    "out_for_delivery",
    "2026-11-17",
    sender="Fjord Outdoor",
    location="Zurich",
)
BOWLS = parcel(
    "7adc5a28-39e4-450d-8cbf-fb4b123eb52d",
    "Ceramic bowls",
    "La Poste / Colissimo",
    "6A18273645095",
    "ready_for_pickup",
    "2026-11-16",
    attention="ready_for_pickup",
    pickup_point="Relais Demo",
    sender="Atelier Demo",
)
JACKET = parcel(
    "105e6417-fbfe-4ebc-be89-babcbed30a29",
    "Winter jacket",
    "DHL",
    "00340434292135100186",
    "in_transit",
    "2026-11-18",
    location="Basel",
)
BOOKS = parcel(
    "e1ea8d55-1c51-421b-9dd7-16f885beee5e",
    None,
    "PostNL",
    "3SDEMO0482917",
    "pending",
    "2026-11-21",
    sender="Demo Books",
    location=None,
)
HOSE = parcel(
    "04f6ea14-0e01-4fb1-bcaa-d6dc8473ef76",
    "Garden hose",
    "DPD Switzerland",
    "01505024382917",
    "failed_attempt",
    "2026-11-18",
    attention="failed_attempt",
    sender="Garden Supply Co",
)
CASE = parcel(
    "0fb9dbaf-be67-45a7-a397-7fdc42498ebb",
    "Phone case",
    "AliExpress / Cainiao",
    "AP00498127365012",
    "customs",
    "2026-11-23",
    attention="customs",
    sender="Demo Gadgets Store",
)
DOCK = parcel(
    "2c7859bc-6c9f-4bec-a4ed-d8a5e311cfa7",
    "USB-C dock",
    "Swiss Post",
    "996012345612345678",
    "delivered",
    "2026-11-17",
    delivered_at="2026-11-17T10:05:09+00:00",
    sender="Demo Electronics",
    location="Lausanne",
)
LAMP = parcel(
    "67c197b1-3f99-463b-9dba-2eca7a096923",
    "Desk lamp",
    "GLS Switzerland",
    "46523910834",
    "delivered",
    "2026-11-08",
    delivered_at="2026-11-08T12:05:00+00:00",
    archived=True,
)


def answer(
    *parcels: dict[str, Any], status: str = "active", sort: str = "expected", total: int | None = None
) -> dict[str, Any]:
    """An answer of GET /api/parcels."""
    return {
        "total": len(parcels) if total is None else total,
        "status": status,
        "sort": sort,
        "parcels": [deepcopy(item) for item in parcels],
    }


def active_answer() -> dict[str, Any]:
    """The default parcels on their way."""
    return answer(BOOTS, BOWLS, JACKET, HOSE, BOOKS, CASE)


def delivered_answer() -> dict[str, Any]:
    """The default deliveries."""
    return answer(DOCK, LAMP, status="delivered", sort="delivered")


def tool_answer(structured: dict[str, Any], request_id: int = 1) -> dict[str, Any]:
    """An MCP tools/call reply."""
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "result": {"content": [{"type": "text", "text": "ok"}], "structuredContent": structured},
    }


def tool_refusal(text: str, *, scope: bool = False, request_id: int = 1) -> dict[str, Any]:
    """An MCP tools/call reply that refuses."""
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}], "isError": True}
    if scope:
        result["_meta"] = {"mcp/www_authenticate": ['Bearer error="insufficient_scope"']}
    return {"jsonrpc": "2.0", "id": request_id, "result": result}
