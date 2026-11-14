"""
Test doubles for the integration tests.

- FakeApr16:   plays the processor. It answers the REST and Atlas calls the integration makes and records
               everything it was asked to change.
- FakeRemote:  stands in for ucapi's IntegrationAPI. It records what entities push to the Remote.
- make_rig():  builds a real Apr16 device plus every real entity the driver creates, wired to the two fakes.

Only the network is faked. The device, client, entities and the ucapi / ucapi-framework base classes are real.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import re
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import aiohttp

from config import APR16Config
from device import Apr16
from driver import Apr16Driver

ATLAS_PREFIX = "/commands.v1.AtlasService/"
HOST = "10.0.0.5"
DEVICE_ID = "dev1"
DEVICE_NAME = "APR"


def http_error(status: int) -> aiohttp.ClientResponseError:
    """The exception aiohttp raises for an error status."""
    return aiohttp.ClientResponseError(request_info=MagicMock(), history=(), status=status)


# =============================================================================
# The processor
# =============================================================================


class FakeApr16:
    """Answers the calls the integration makes, like an APR-16 would, and records what it is asked to change."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {
            "power": "1",
            "vol": 25,
            "mute": False,
            "brightness": 50,
            "bass": 11,
            "treble": -3,
            "source": "HDMI 2",
            "mode": "2ch",
            "bit": 24,
            "sample": 48000,
            "dirac": False,  # master Dirac filtering
            "slot": 0,  # active Dirac slot
        }
        self.input_names = {1: "Apple TV", 3: "PS5"}

        self.posts: list[tuple[str, Any]] = []  # (path, json payload) of every REST POST
        self.rpcs: list[tuple[str, bytes]] = []  # (method, body) of every Atlas call
        self.log: list[tuple[str, str, dict[str, Any]]] = []  # (method, url, kwargs) of every request
        self.rejected: list[str] = []  # requests the real device would have refused

        self.failing: set[str] = set()  # paths that answer HTTP 500 to any request
        self.failing_posts: set[str] = set()  # paths that answer HTTP 500 to POST only (reads still work)
        self.overrides: dict[str, tuple[int, bytes]] = {}  # path -> fixed reply
        self.atlas_replies: dict[str, tuple[int, bytes]] = {}  # Atlas method -> reply
        self.stale_connections: dict[str, int] = {}  # path -> times the next request hits a dropped connection

        self.sessions_opened = 0

    # ------------------------------------------------------------------ helpers for the tests

    @property
    def requests(self) -> int:
        return len(self.log)

    def volume_posts(self) -> list[int]:
        """Every level sent to /v1/vol, in order."""
        return [payload["level"] for path, payload in self.posts if path == "/v1/vol"]

    # ------------------------------------------------------------------ the HTTP exchange

    def handle(self, method: str, url: str, kwargs: dict[str, Any]) -> tuple[int, bytes]:
        self.log.append((method, url, kwargs))
        path = "/" + url.split("//", 1)[1].split("/", 1)[1]

        if self.stale_connections.get(path):
            self.stale_connections[path] -= 1
            raise aiohttp.ServerDisconnectedError()

        if path.startswith(ATLAS_PREFIX):
            name = path.removeprefix(ATLAS_PREFIX)
            body = kwargs.get("data", b"")
            self.rpcs.append((name, body))
            if name in self.atlas_replies:
                return self.atlas_replies[name]
            # Like the real device: filtering is the first field of the reply, and zero values are left out.
            if name == "GetDiracFiltering":
                return 200, (bytes.fromhex("080110011801") if self.state["dirac"] else b"")
            if name == "GetDiracActiveSlot":
                return 200, (bytes([0x08, self.state["slot"]]) if self.state["slot"] else b"")
            if name == "SetDiracFilterSlot":
                self.state["slot"] = body[1] if body[:1] == b"\x08" else 0
            if name == "SetDiracFiltering":
                self.state["dirac"] = body[:2] == b"\x08\x01"
            return 200, b""

        if path in self.overrides:
            return self.overrides[path]
        if path in self.failing:
            return 500, b""

        if method == "POST" and path in self.failing_posts:
            return 500, b""

        if method == "POST":
            return self._post(path, kwargs.get("json"))
        return self._get(path, kwargs.get("params"))

    def _post(self, path: str, payload: Any) -> tuple[int, bytes]:
        self.posts.append((path, payload))
        state = self.state

        if path == "/v1/vol":
            level = payload["level"]
            if not isinstance(level, int) or isinstance(level, bool):
                self.rejected.append(f"/v1/vol level {level!r} is not an integer")
                return 500, b""
            if level < 0:
                self.rejected.append(f"/v1/vol level {level!r} is negative (the device silently clamps it to 0)")
            state["vol"] = max(0, min(100, level))
        elif path == "/v1/mute":
            state["mute"] = payload["state"]
        elif path == "/v1/power":
            state["power"] = payload["state"]
        elif path == "/v1/displaybrightness":
            state["brightness"] = payload["brightness"]
        elif path == "/api/atlas/input/active":
            state["source"] = payload["input"]
        elif path == "/v1/audiomode":
            state["mode"] = payload["mode"]
        elif match := re.fullmatch(r"/api/atlas/input/.+/(bass|treb)/(-?\d+)", path):
            state["bass" if match[1] == "bass" else "treble"] = int(match[2])

        return 200, b"{}"

    def _get(self, path: str, params: dict[str, Any] | None) -> tuple[int, bytes]:
        state = self.state

        if path == "/api/atlas/input/name":
            name = self.input_names.get(params["input"])
            return (200, _json({"name": name})) if name else (404, b"")

        if match := re.fullmatch(r"/api/atlas/input/.+/(bass|treb)", path):
            return 200, _json({"level": state["bass" if match[1] == "bass" else "treble"]})

        replies = {
            "/v1/power": {"state": state["power"]},
            "/v1/vol": {"level": state["vol"]},
            "/v1/mute": {"state": state["mute"]},
            "/v1/audiomode": {"mode": state["mode"]},
            "/v1/audioformat": {"format": "Dolby Atmos"},
            "/v1/audiodetail": {"summary": "PCM 48k"},
            "/v1/bit": {"bit": state["bit"]},
            "/v1/sample": {"sample": state["sample"]},
            "/v1/videodetail": {"resolution": "4K", "framerate": "60", "hdr": "hdr10"},
            "/v1/displaybrightness": {"brightness": state["brightness"]},
            "/v1/hostip": {"ip": HOST},
            "/api/atlas/input/active": {"source": state["source"]},
        }
        return (200, _json(replies[path])) if path in replies else (404, b"")


def _json(value: Any) -> bytes:
    return json.dumps(value).encode()


class _Response:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    async def read(self) -> bytes:
        return self._body

    def raise_for_status(self) -> None:
        if self.status >= 400:
            raise http_error(self.status)


class _Exchange:
    """What ``session.request(...)`` returns: an async context manager yielding the response."""

    def __init__(self, apr: FakeApr16, method: str, url: str, kwargs: dict[str, Any]) -> None:
        self._apr, self._request = apr, (method, url, kwargs)

    async def __aenter__(self) -> _Response:
        await asyncio.sleep(0)  # a real request yields to the event loop
        return _Response(*self._apr.handle(*self._request))

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False


def install_fake_network(monkeypatch, apr: FakeApr16) -> None:
    """Make every aiohttp.ClientSession talk to ``apr`` instead of the network."""

    class Session:
        closed = False

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            apr.sessions_opened += 1

        def request(self, method: str, url: str, **kwargs: Any) -> _Exchange:
            return _Exchange(apr, method, url, kwargs)

        async def close(self) -> None:
            self.closed = True

    monkeypatch.setattr(aiohttp, "ClientSession", Session)


# =============================================================================
# The Remote
# =============================================================================


def _plain(value: Any) -> Any:
    """Enum members compare by value on the wire; turn them into plain values."""
    return getattr(value, "value", value)


class FakeRemote:
    """
    Stands in for ucapi's IntegrationAPI.

    Entities push their attributes through ``api.configured_entities``; this records those pushes.
    """

    def __init__(self) -> None:
        self.updates: list[tuple[str, dict[str, Any]]] = []
        self.configured_entities = self

    # the parts of ConfiguredEntities that framework entities use
    def contains(self, entity_id: str) -> bool:
        return True

    def get(self, entity_id: str) -> None:
        return None

    def update_attributes(self, entity_id: str, attributes: dict[Any, Any]) -> None:
        self.updates.append((entity_id, {_plain(k): _plain(v) for k, v in attributes.items()}))

    # for the tests
    def last(self, entity_id: str, attribute: str) -> Any:
        """The most recent value pushed for an attribute of an entity, or None."""
        for pushed_id, attributes in reversed(self.updates):
            if pushed_id == entity_id and attribute in attributes:
                return attributes[attribute]
        return None


# =============================================================================
# Everything wired together
# =============================================================================


async def settle() -> None:
    """Let the event emitter run the entities' sync_state() handlers."""
    for _ in range(60):
        await asyncio.sleep(0)


@dataclass
class Rig:
    apr: FakeApr16
    device: Apr16
    remote: FakeRemote
    entities: dict[str, Any]
    config: APR16Config

    @property
    def media_player(self):
        return self.entities[f"media_player.{DEVICE_ID}"]

    def entity(self, kind: str, name: str):
        """For example entity("sensor", "mute")."""
        return self.entities[f"{kind}.{DEVICE_ID}.{name}"]

    async def command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None = None):
        """Send a command the way the Remote does, through the entity's public command()."""
        if "websocket" in inspect.signature(entity.command).parameters:
            return await entity.command(cmd_id, params, websocket=None)
        return await entity.command(cmd_id, params)


async def make_rig(monkeypatch, *, volume_mode: str = "absolute", connect: bool = True, **device_state: Any) -> Rig:
    """
    Build a real device and the real entities against a fake processor and a fake Remote.

    Keyword arguments other than volume_mode and connect set the processor's starting state
    (for example ``vol=42``). With connect=True the device connects and the entities sync,
    like the driver does after a successful connection.
    """
    apr = FakeApr16()
    apr.state.update(device_state)
    install_fake_network(monkeypatch, apr)

    config = APR16Config(
        identifier=DEVICE_ID, name=DEVICE_NAME, address=HOST, port=8080, volume_mode=volume_mode
    )
    device = Apr16(config, asyncio.get_running_loop())

    remote = FakeRemote()
    entities = {entity.id: entity for entity in Apr16Driver().create_entities(config, device)}
    for entity in entities.values():
        entity._api = remote

    rig = Rig(apr=apr, device=device, remote=remote, entities=entities, config=config)

    if connect:
        assert await device.connect(), "the fake processor should accept the connection"
        device.push_update()  # the driver syncs every entity after a successful connect
        await settle()

    return rig
