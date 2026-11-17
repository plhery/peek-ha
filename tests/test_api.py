"""Tests for Peek's API client."""

from datetime import UTC, datetime
from email.utils import format_datetime
import json

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import AiohttpClientMocker

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from custom_components.peek.api import (
    MCP_PROTOCOL_VERSION,
    PeekAuthError,
    PeekClient,
    PeekError,
    PeekRateLimitError,
    PeekScopeError,
    PeekToolError,
    PeekUnavailableError,
    retry_after_seconds,
    revoke_token,
)

from .common import (
    BOOTS,
    CLIENT_ID,
    MCP_URL,
    PARCELS_URL,
    REVOKE_URL,
    URL,
    answer,
    tool_answer,
    tool_refusal,
)


async def token() -> str:
    """The access token the client sends."""
    return "synthetic-access-token"


@pytest.fixture
async def client(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> PeekClient:
    """A client for Peek's address, on the mocked session."""
    return PeekClient(async_get_clientsession(hass), f"{URL}/", token, "9.9.9")


async def test_parcels(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """The parcels come with the query and the token."""
    aioclient_mock.get(PARCELS_URL, json=answer(BOOTS))
    result = await client.parcels(status="today", sort="expected", search="Fjord", limit=5)
    assert client.url == URL
    assert result["parcels"][0]["name"] == "Hiking boots"
    method, url, _, headers = aioclient_mock.mock_calls[0]
    assert method == "GET"
    assert dict(url.query) == {"status": "today", "sort": "expected", "search": "Fjord", "limit": "5"}
    assert headers["Authorization"] == "Bearer synthetic-access-token"


async def test_parcels_without_total(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """A missing total counts the parcels."""
    aioclient_mock.get(PARCELS_URL, json={"parcels": [BOOTS]})
    assert (await client.parcels())["total"] == 1


@pytest.mark.parametrize(
    ("status", "headers", "body", "error"),
    [
        (401, {}, {"error": "invalid_token"}, PeekAuthError),
        (403, {"WWW-Authenticate": 'Bearer error="insufficient_scope"'}, {"error": "scope"}, PeekScopeError),
        (403, {}, {"error": "Peek does not connect assistants to this account"}, PeekUnavailableError),
        (404, {}, {"error": "Not found"}, PeekUnavailableError),
        (429, {"Retry-After": "30"}, {"error": "slow down"}, PeekRateLimitError),
        (502, {}, "Bad gateway", PeekUnavailableError),
        (400, {}, {"error": "limit is a whole number"}, PeekError),
        (400, {}, {"error": {"message": "nested"}}, PeekError),
        (400, {}, [1, 2], PeekError),
        (400, {}, {"message": "no error key"}, PeekError),
        (400, {}, "plain words", PeekError),
    ],
)
async def test_parcels_errors(
    client: PeekClient,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    headers: dict[str, str],
    body: object,
    error: type[Exception],
) -> None:
    """Each status raises its error."""
    text = body if isinstance(body, str) else json.dumps(body)
    aioclient_mock.get(PARCELS_URL, status=status, text=text, headers=headers)
    with pytest.raises(error) as caught:
        await client.parcels()
    assert type(caught.value) is error
    if error is PeekRateLimitError:
        assert caught.value.retry_after == 30


@pytest.mark.parametrize("text", ["not json", json.dumps({"total": 1}), json.dumps([])])
async def test_parcels_unexpected(client: PeekClient, aioclient_mock: AiohttpClientMocker, text: str) -> None:
    """An answer without parcels is an error."""
    aioclient_mock.get(PARCELS_URL, text=text)
    with pytest.raises(PeekError):
        await client.parcels()


@pytest.mark.parametrize("exc", [ClientError("down"), TimeoutError()])
async def test_parcels_unreachable(client: PeekClient, aioclient_mock: AiohttpClientMocker, exc: Exception) -> None:
    """A connection error makes Peek unavailable."""
    aioclient_mock.get(PARCELS_URL, exc=exc)
    with pytest.raises(PeekUnavailableError):
        await client.parcels()


def test_retry_after() -> None:
    """Retry-After in seconds or as a date."""
    assert retry_after_seconds(None) is None
    assert retry_after_seconds("") is None
    assert retry_after_seconds("12") == 12
    assert retry_after_seconds("-3") == 0
    assert retry_after_seconds("soon") is None
    later = datetime(2026, 11, 17, 12, 1, tzinfo=UTC)
    now = datetime(2026, 11, 17, 12, 0, tzinfo=UTC).timestamp()
    assert retry_after_seconds(format_datetime(later, usegmt=True), now=now) == 60
    assert retry_after_seconds(format_datetime(later, usegmt=True)) is not None


async def test_add_parcels_request(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """add_parcels is one stateless tools/call request in the 2026-07-28 shape."""
    outcomes = [{"trackingNumber": "1Z4E7W960398127345", "carrier": "UPS", "outcome": "added", "id": BOOTS["id"]}]
    aioclient_mock.post(MCP_URL, json=tool_answer({"parcels": outcomes}))
    assert await client.add_parcels("UPS 1Z4E7W960398127345", "Fjord Outdoor") == outcomes
    method, url, body, headers = aioclient_mock.mock_calls[0]
    assert method == "POST"
    assert str(url) == MCP_URL
    assert headers["Authorization"] == "Bearer synthetic-access-token"
    assert headers["MCP-Protocol-Version"] == MCP_PROTOCOL_VERSION
    assert headers["Mcp-Method"] == "tools/call"
    assert headers["Mcp-Name"] == "add_parcels"
    assert headers["Accept"] == "application/json, text/event-stream"
    assert body == {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "add_parcels",
            "arguments": {"text": "UPS 1Z4E7W960398127345", "name": "Fjord Outdoor"},
            "_meta": {
                "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                "io.modelcontextprotocol/clientCapabilities": {},
                "io.modelcontextprotocol/clientInfo": {"name": "peek-home-assistant", "version": "9.9.9"},
            },
        },
    }


async def test_add_parcels_without_name(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """Without a name, only the text goes."""
    aioclient_mock.post(MCP_URL, json=tool_answer({"parcels": []}))
    assert await client.add_parcels("no number here") == []
    assert aioclient_mock.mock_calls[0][2]["params"]["arguments"] == {"text": "no number here"}


async def test_event_stream_answer(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """An older server answers in Server-Sent Events."""
    reply = json.dumps(tool_answer({"id": BOOTS["id"], "archived": True}))
    aioclient_mock.post(
        MCP_URL,
        text=f"event: message\ndata: not json\n\nevent: message\ndata: {reply}\n\n",
        headers={"Content-Type": "text/event-stream"},
    )
    assert await client.archive_parcel("1Z4E7W960398127345") == BOOTS["id"]


async def test_event_stream_without_reply(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """A stream holding no reply to the request is an error."""
    aioclient_mock.post(
        MCP_URL,
        text='event: ping\n\ndata: {"jsonrpc": "2.0", "id": 99, "result": {}}\n\n',
        headers={"Content-Type": "text/event-stream"},
    )
    with pytest.raises(PeekError):
        await client.archive_parcel("x")


@pytest.mark.parametrize(
    ("status", "reply", "error"),
    [
        (200, {"jsonrpc": "2.0", "id": 1, "error": {"code": -32602, "message": "Unknown tool"}}, PeekError),
        (
            400,
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32020, "message": "Mcp-Name is required"}},
            PeekError,
        ),
        (
            200,
            tool_refusal("This connection to Peek may see parcels but not add them.", scope=True),
            PeekScopeError,
        ),
        (200, tool_refusal("No such parcel in this Peek account."), PeekToolError),
        (200, {"jsonrpc": "2.0", "id": 1, "result": {"isError": True, "content": []}}, PeekToolError),
        (200, {"jsonrpc": "2.0", "id": 1}, PeekError),
        (200, [1], PeekError),
        (200, "not json", PeekError),
        (401, {"error": "invalid_token"}, PeekAuthError),
        (429, {"error": "slow down"}, PeekRateLimitError),
    ],
)
async def test_tool_errors(
    client: PeekClient,
    aioclient_mock: AiohttpClientMocker,
    status: int,
    reply: object,
    error: type[Exception],
) -> None:
    """Refusals and errors raise their own error."""
    text = reply if isinstance(reply, str) else json.dumps(reply)
    aioclient_mock.post(MCP_URL, status=status, text=text)
    with pytest.raises(error) as caught:
        await client.archive_parcel("6A18273645095")
    assert type(caught.value) is error


async def test_tool_answers_without_content(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """A reply without structured content still archives; one without parcels is an error for add_parcels."""
    aioclient_mock.post(MCP_URL, json={"jsonrpc": "2.0", "id": 1, "result": {"content": []}})
    assert await client.archive_parcel("6A18273645095") == "6A18273645095"
    with pytest.raises(PeekError):
        await client.add_parcels("text")


async def test_request_ids_increase(client: PeekClient, aioclient_mock: AiohttpClientMocker) -> None:
    """Each call has its own JSON-RPC id."""
    aioclient_mock.post(MCP_URL, json=tool_answer({"id": "a"}))
    await client.archive_parcel("a")
    await client.archive_parcel("b")
    assert [call[2]["id"] for call in aioclient_mock.mock_calls] == [1, 2]


async def test_revoke(hass: HomeAssistant, aioclient_mock: AiohttpClientMocker) -> None:
    """Revoking posts the token and the client id."""
    aioclient_mock.post(REVOKE_URL, status=200)
    await revoke_token(async_get_clientsession(hass), URL, CLIENT_ID, "synthetic-refresh-token")
    assert aioclient_mock.mock_calls[0][2] == {
        "token": "synthetic-refresh-token",
        "client_id": CLIENT_ID,
        "token_type_hint": "refresh_token",
    }


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"status": 400}, PeekError),
        ({"exc": ClientError("down")}, PeekUnavailableError),
        ({"exc": TimeoutError()}, PeekUnavailableError),
    ],
)
async def test_revoke_errors(
    hass: HomeAssistant, aioclient_mock: AiohttpClientMocker, kwargs: dict, error: type[Exception]
) -> None:
    """A failed revocation raises."""
    aioclient_mock.post(REVOKE_URL, **kwargs)
    with pytest.raises(error):
        await revoke_token(async_get_clientsession(hass), URL, CLIENT_ID, "synthetic-refresh-token")
