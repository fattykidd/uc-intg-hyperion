"""
Async HTTP client for the AudioControl Hyperion APR-16.

One instance owns one aiohttp session for the lifetime of the device, so requests
reuse the same TCP connection instead of reconnecting every time. The session is
created on first use and closed with close().
"""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp

from const import ATLAS_PORT, ATLAS_SERVICE, DEFAULT_PORT, DEFAULT_TIMEOUT

_LOG = logging.getLogger(__name__)


class HyperionClient:
    """Thin wrapper around the APR-16 REST API (and its Atlas RPC port)."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        atlas_port: int = ATLAS_PORT,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._rest_url = f"http://{host}:{port}"
        self._atlas_url = f"http://{host}:{atlas_port}"
        self._timeout = timeout
        self._session: aiohttp.ClientSession | None = None

    @property
    def atlas_origin(self) -> str:
        """Origin (scheme, host, port) of the Atlas RPC service."""
        return self._atlas_url

    # ------------------------------------------------------------------
    # Session handling
    # ------------------------------------------------------------------

    def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Close the shared session. Safe to call more than once."""
        session, self._session = self._session, None
        if session is not None and not session.closed:
            await session.close()

    async def _request(
        self,
        method: str,
        url: str,
        *,
        timeout: float | None = None,
        raise_for_status: bool = True,
        **kwargs: Any,
    ) -> tuple[int, bytes]:
        """Send one request and return (status, body)."""
        session = self._ensure_session()
        request_timeout = aiohttp.ClientTimeout(total=timeout or self._timeout)

        for attempt in (1, 2):
            try:
                async with session.request(method, url, timeout=request_timeout, **kwargs) as resp:
                    body = await resp.read()
                    if raise_for_status:
                        resp.raise_for_status()
                    return resp.status, body
            except aiohttp.ServerDisconnectedError:
                # A reused connection can go stale if the device dropped it while idle.
                # The request never reached the device, so one retry on a fresh connection is safe.
                if attempt == 2:
                    raise
                _LOG.debug("Connection dropped by device, retrying %s %s", method, url)

        raise AssertionError("unreachable")  # pragma: no cover

    # ------------------------------------------------------------------
    # REST API
    # ------------------------------------------------------------------

    async def get_text(self, path: str, *, timeout: float | None = None) -> str:
        """GET a path on the REST API and return the body as text."""
        _, body = await self._request("GET", f"{self._rest_url}{path}", timeout=timeout)
        return body.decode("utf-8", errors="replace")

    async def get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> Any:
        """GET a path on the REST API and return the decoded JSON ({} for an empty body)."""
        _, body = await self._request(
            "GET",
            f"{self._rest_url}{path}",
            timeout=timeout,
            params=params,
            headers={"Accept": "application/json"},
        )
        return json.loads(body) if body else {}

    async def post(
        self,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: float | None = None,
    ) -> None:
        """POST a JSON payload to the REST API. Raises on an HTTP error status."""
        await self._request("POST", f"{self._rest_url}{path}", timeout=timeout, json=payload)

    # ------------------------------------------------------------------
    # Atlas RPC (Connect protocol over HTTP, protobuf bodies)
    # ------------------------------------------------------------------

    async def rpc(
        self,
        method: str,
        data: bytes = b"",
        *,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[int, bytes]:
        """
        Call an Atlas RPC method and return (status, body).

        Unlike the REST helpers this does not raise on an HTTP error status, because
        callers decide what a failed Dirac call means.
        """
        merged = {
            "Content-Type": "application/proto",
            "Connect-Protocol-Version": "1",
            **(headers or {}),
        }
        return await self._request(
            "POST",
            f"{self._atlas_url}/{ATLAS_SERVICE}/{method}",
            timeout=timeout,
            raise_for_status=False,
            data=data,
            headers=merged,
        )
