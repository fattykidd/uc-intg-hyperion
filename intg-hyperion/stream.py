"""
Live state streams from the AudioControl Hyperion APR-16.

The device's own web UI doesn't poll. It opens a WebSocket to ``/ws/state``, sends ``{"request": "<kind>"}``
and is then told about every change. A StateStream does the same for one kind of state ("audio", "inputs" or
"dirac") and hands each new state to a callback.

What the device sends, per connection:

- ``{"request": "<kind>", "state": "<JSON text>"}``  the complete state (the state is JSON inside a string).
  The first one is the current state. ``audio`` repeats about once a second with only its ``timestamp``
  changed, so the timestamp is dropped and a state identical to the last one is not passed on.
- ``{"heartbeat": true}``  every ~15 seconds, so silence means the connection is dead.

A stream that fails (device rebooting, firmware without ``/ws/state``) reconnects with a growing delay.
``live`` tells the owner whether the stream can be trusted, so it can fall back to polling meanwhile.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

import aiohttp

from const import (
    STREAM_CONNECT_TIMEOUT,
    STREAM_RECONNECT_MAX,
    STREAM_RECONNECT_MIN,
    STREAM_SILENCE_TIMEOUT,
    STREAM_STABLE_AFTER,
)

_LOG = logging.getLogger(__name__)

StateCallback = Callable[[dict[str, Any]], None]
Connector = Callable[[], Awaitable[aiohttp.ClientWebSocketResponse]]

_CLOSED = (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSING, aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR)


class StateStream:
    """Follows one kind of device state and reports each change to a callback."""

    def __init__(
        self,
        kind: str,
        connect: Connector,
        on_state: StateCallback,
        *,
        log_id: str = "",
        silence_timeout: float = STREAM_SILENCE_TIMEOUT,
        reconnect_min: float = STREAM_RECONNECT_MIN,
        reconnect_max: float = STREAM_RECONNECT_MAX,
        stable_after: float = STREAM_STABLE_AFTER,
    ) -> None:
        """
        :param kind: what to ask the device for: "audio", "inputs", "dirac", ...
        :param connect: opens a new WebSocket to the device's state endpoint
        :param on_state: called with each new state (a dict, without its timestamp). Must not block.
        :param silence_timeout: seconds without any message (heartbeats included) before the connection is
            considered dead and replaced
        :param reconnect_min: first delay before reconnecting, doubled after each failure
        :param reconnect_max: longest delay before reconnecting
        :param stable_after: a connection that lasted this long counts as healthy again, so the next
            reconnect starts at reconnect_min
        """
        self.kind = kind
        self._connect = connect
        self._on_state = on_state
        self._log_id = log_id or kind
        self._silence_timeout = silence_timeout
        self._reconnect_min = reconnect_min
        self._reconnect_max = reconnect_max
        self._stable_after = stable_after

        self._task: asyncio.Task | None = None
        self._connected = False
        self._last_seen = 0.0  # monotonic time of the last message
        self._last_state: dict[str, Any] | None = None

    @property
    def live(self) -> bool:
        """True while connected and the device has been heard from recently."""
        return self._connected and time.monotonic() - self._last_seen < self._silence_timeout

    def start(self) -> None:
        """Start following the device. Does nothing if already started."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name=f"hyperion-stream-{self.kind}")

    async def stop(self) -> None:
        """Stop following the device and close the connection."""
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self._connected = False

    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Keep a connection open, reconnecting after every failure."""
        delay = self._reconnect_min
        warned = False

        while True:
            started = time.monotonic()
            try:
                await self._follow()
                reason = "the device closed the connection"
            except asyncio.CancelledError:
                raise
            except Exception as err:
                reason = repr(err) if isinstance(err, TimeoutError) else str(err)

            if time.monotonic() - started >= self._stable_after:
                delay = self._reconnect_min
                warned = False

            if warned:
                _LOG.debug("[%s] %s stream is still down: %s", self._log_id, self.kind, reason)
            else:
                _LOG.warning("[%s] Lost the %s stream (%s), retrying", self._log_id, self.kind, reason)
                warned = True

            await asyncio.sleep(delay)
            delay = min(delay * 2, self._reconnect_max)

    async def _follow(self) -> None:
        """One connection, from opening it until it ends or goes quiet."""
        ws = await asyncio.wait_for(self._connect(), STREAM_CONNECT_TIMEOUT)
        self._last_state = None  # the first message of a connection is passed on even if it is unchanged
        self._last_seen = time.monotonic()
        self._connected = True
        try:
            await ws.send_str(json.dumps({"request": self.kind}))
            _LOG.debug("[%s] Following the %s stream", self._log_id, self.kind)

            while True:
                message = await ws.receive(timeout=self._silence_timeout)
                if message.type == aiohttp.WSMsgType.TEXT:
                    self._handle(message.data)
                elif message.type in _CLOSED:
                    return
        finally:
            self._connected = False
            await ws.close()

    def _handle(self, text: str) -> None:
        """Decode one message and pass its state on if it differs from the last one."""
        try:
            message = json.loads(text)
        except ValueError:
            _LOG.debug("[%s] Ignoring a %s message that isn't JSON", self._log_id, self.kind)
            return

        if not isinstance(message, dict):
            return
        self._last_seen = time.monotonic()  # heartbeats count, they prove the device is still there

        state = message.get("state")
        if isinstance(state, str):
            try:
                state = json.loads(state)
            except ValueError:
                state = None
        if not isinstance(state, dict):
            return  # a heartbeat, or something this driver doesn't know

        state.pop("timestamp", None)
        if state == self._last_state:
            return
        self._last_state = state

        try:
            self._on_state(state)
        except Exception:
            _LOG.exception("[%s] Handling a %s update failed", self._log_id, self.kind)
