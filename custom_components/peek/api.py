"""A small client for Peek's API, with nothing from Home Assistant in it.

Reading goes through `GET /api/parcels`; adding and archiving go through Peek's MCP server (`POST /mcp`), whose
`add_parcels` and `archive_parcel` tools are the only way to write. Each call takes a fresh access token from `token`.
"""

from collections.abc import Awaitable, Callable
from email.utils import parsedate_to_datetime
import json
import time
from typing import Any, Final, NotRequired, TypedDict

import aiohttp

MCP_PROTOCOL_VERSION: Final = "2026-07-28"
CLIENT_NAME: Final = "peek-home-assistant"
TIMEOUT: Final = aiohttp.ClientTimeout(total=30)


class LastUpdate(TypedDict):
    """The newest scan of a parcel."""

    time: str
    description: str
    location: str | None


class Parcel(TypedDict):
    """A parcel as Peek's API gives it."""

    id: str
    name: str | None
    carrier: str
    trackingNumber: str
    status: str
    statusText: str | None
    needsAttention: str | None
    expectedDelivery: str | None
    deliveredAt: str | None
    lastUpdate: LastUpdate | None
    pickupPoint: str | None
    sender: str | None
    archived: bool
    addedAt: str


class ParcelList(TypedDict):
    """An answer of `GET /api/parcels`: `total` counts every match, `parcels` holds up to `limit` of them."""

    total: int
    status: str
    sort: str
    parcels: list[Parcel]


class Addition(TypedDict):
    """What became of one tracking number `add_parcels` found."""

    trackingNumber: str
    carrier: str
    outcome: str
    id: NotRequired[str]
    reason: NotRequired[str]


class PeekError(Exception):
    """Peek could not answer."""


class PeekAuthError(PeekError):
    """Peek refused the token: the user has to sign in again."""


class PeekScopeError(PeekError):
    """The token may not do this: a new sign-in asks for every scope again."""


class PeekRateLimitError(PeekError):
    """Too many requests for this connection; `retry_after` says when to come back, in seconds."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        """Keep the wait Peek asked for."""
        super().__init__(message)
        self.retry_after = retry_after


class PeekUnavailableError(PeekError):
    """Peek can't be reached, or doesn't connect assistants right now."""


class PeekToolError(PeekError):
    """Peek refused a tool call, such as archiving a parcel it doesn't know."""


def retry_after_seconds(value: str | None, now: float | None = None) -> float | None:
    """Read a Retry-After header: seconds, or an HTTP date."""
    if not value:
        return None
    try:
        return max(float(value), 0.0)
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(value)
    except TypeError, ValueError:
        return None
    return max(when.timestamp() - (time.time() if now is None else now), 0.0)


def _error_text(body: str) -> str:
    """The `error` (or JSON-RPC error message) of an error answer, else its first words."""
    try:
        data = json.loads(body)
    except ValueError:
        return body[:200]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message", error))
        if error:
            return str(error)
    return body[:200]


def _raise_for_status(status: int, headers: Any, body: str) -> None:
    """Raise the error an HTTP status stands for."""
    if status < 400:
        return
    text = _error_text(body)
    if status == 401:
        raise PeekAuthError(f"Peek refused the token: {text}")
    if status == 403:
        if "insufficient_scope" in headers.get("WWW-Authenticate", ""):
            raise PeekScopeError(f"The connection may not do this: {text}")
        raise PeekUnavailableError(f"Peek refused the request: {text}")
    if status == 404:
        raise PeekUnavailableError("Peek does not connect assistants at this address")
    if status == 429:
        raise PeekRateLimitError("Too many requests to Peek", retry_after_seconds(headers.get("Retry-After")))
    if status >= 500:
        raise PeekUnavailableError(f"Peek answered {status}")
    raise PeekError(f"Peek answered {status}: {text}")


def _read_event_stream(body: str, request_id: int) -> dict[str, Any]:
    """The JSON-RPC answer in a Server-Sent Events body, as a server speaking an older revision sends it."""
    answer: dict[str, Any] | None = None
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            message = json.loads(line[5:].strip())
        except ValueError:
            continue
        if isinstance(message, dict) and message.get("id") == request_id:
            answer = message
    if answer is None:
        raise PeekError("Peek's answer held no reply")
    return answer


class PeekClient:
    """Peek's API for one account, reached with the tokens `token` hands out."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        url: str,
        token: Callable[[], Awaitable[str]],
        version: str = "0.1.1",
    ) -> None:
        """Keep the session, Peek's address and where tokens come from."""
        self._session = session
        self._url = url.rstrip("/")
        self._token = token
        self._version = version
        self._request_id = 0

    @property
    def url(self) -> str:
        """Peek's address."""
        return self._url

    async def _send(self, method: str, path: str, **kwargs: Any) -> tuple[int, Any, str]:
        """Send one request with a valid token; return the status, headers and body."""
        token = await self._token()
        headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
        try:
            async with self._session.request(
                method, f"{self._url}{path}", headers=headers, timeout=TIMEOUT, **kwargs
            ) as response:
                return response.status, response.headers, await response.text()
        except TimeoutError as err:
            raise PeekUnavailableError("Peek did not answer in time") from err
        except aiohttp.ClientError as err:
            raise PeekUnavailableError(f"Peek can't be reached: {err}") from err

    async def parcels(
        self,
        status: str | None = None,
        sort: str | None = None,
        search: str | None = None,
        limit: int | None = None,
    ) -> ParcelList:
        """The account's parcels that match, as `GET /api/parcels` lists them."""
        params = {
            key: str(value)
            for key, value in (
                ("status", status),
                ("sort", sort),
                ("search", search),
                ("limit", limit),
            )
            if value is not None
        }
        code, headers, body = await self._send(
            "GET", "/api/parcels", params=params, headers={"Accept": "application/json"}
        )
        _raise_for_status(code, headers, body)
        try:
            data = json.loads(body)
        except ValueError as err:
            raise PeekError("Peek's answer was not JSON") from err
        if not isinstance(data, dict) or not isinstance(data.get("parcels"), list):
            raise PeekError("Peek's answer held no parcels")
        data.setdefault("total", len(data["parcels"]))
        return data  # type: ignore[return-value]

    async def add_parcels(self, text: str, name: str | None = None) -> list[Addition]:
        """Add the tracking numbers found in `text`; what became of each."""
        arguments: dict[str, Any] = {"text": text}
        if name:
            arguments["name"] = name
        result = await self._call_tool("add_parcels", arguments)
        parcels = result.get("parcels")
        if not isinstance(parcels, list):
            raise PeekError("Peek's answer held no parcels")
        return parcels

    async def archive_parcel(self, parcel: str) -> str:
        """Archive a parcel, named by its id or tracking number; its id."""
        result = await self._call_tool("archive_parcel", {"parcel": parcel})
        return str(result.get("id", parcel))

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Call one of Peek's MCP tools, statelessly: one request, no session, no initialize."""
        self._request_id += 1
        request_id = self._request_id
        message = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": name,
                "arguments": arguments,
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": MCP_PROTOCOL_VERSION,
                    "io.modelcontextprotocol/clientCapabilities": {},
                    "io.modelcontextprotocol/clientInfo": {
                        "name": CLIENT_NAME,
                        "version": self._version,
                    },
                },
            },
        }
        code, headers, body = await self._send(
            "POST",
            "/mcp",
            json=message,
            headers={
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
                "Mcp-Method": "tools/call",
                "Mcp-Name": name,
            },
        )
        if code == 400:
            # A JSON-RPC error comes back as 400 with the error in the body.
            raise PeekError(f"Peek refused the call: {_error_text(body)}")
        _raise_for_status(code, headers, body)
        if "text/event-stream" in headers.get("Content-Type", ""):
            answer = _read_event_stream(body, request_id)
        else:
            try:
                answer = json.loads(body)
            except ValueError as err:
                raise PeekError("Peek's answer was not JSON") from err
        if not isinstance(answer, dict):
            raise PeekError("Peek's answer was not a JSON-RPC reply")
        if "error" in answer:
            raise PeekError(f"Peek refused the call: {_error_text(json.dumps(answer))}")
        result = answer.get("result")
        if not isinstance(result, dict):
            raise PeekError("Peek's answer held no result")
        if result.get("isError"):
            text = " ".join(
                part.get("text", "") for part in result.get("content", []) if isinstance(part, dict)
            ).strip()
            if "mcp/www_authenticate" in (result.get("_meta") or {}):
                raise PeekScopeError(text or "The connection may not do this")
            raise PeekToolError(text or "Peek refused the call")
        structured = result.get("structuredContent")
        return structured if isinstance(structured, dict) else {}


async def revoke_token(session: aiohttp.ClientSession, url: str, client_id: str, token: str) -> None:
    """Give a token back to Peek, which then forgets the connection (RFC 7009)."""
    try:
        async with session.post(
            f"{url.rstrip('/')}/oauth/revoke",
            data={"token": token, "client_id": client_id, "token_type_hint": "refresh_token"},
            timeout=TIMEOUT,
        ) as response:
            if response.status >= 400:
                raise PeekError(f"Peek answered {response.status}")
    except TimeoutError as err:
        raise PeekUnavailableError("Peek did not answer in time") from err
    except aiohttp.ClientError as err:
        raise PeekUnavailableError(f"Peek can't be reached: {err}") from err
