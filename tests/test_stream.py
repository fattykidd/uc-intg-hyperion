"""
StateStream against a real WebSocket server on localhost.

The server plays the part of the processor's /ws/state endpoint: it waits to be told which kind of state is
wanted, answers with the current state (as JSON inside a string, like the device) and then reports changes.
"""

import asyncio
import json

import pytest

aiohttp = pytest.importorskip("aiohttp")
pytest.importorskip("aiohttp.web")
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestServer  # noqa: E402

from client import HyperionClient  # noqa: E402
from fakes import wait_until  # noqa: E402
from stream import StateStream  # noqa: E402

AUDIO = {"power": True, "volume": 36, "mute": False, "audio_mode": "native", "timestamp": 1000}


class FakeProcessor:
    """A /ws/state endpoint. ``state`` is what it reports to a new connection."""

    def __init__(self, state: dict | None = None) -> None:
        self.state = dict(state if state is not None else AUDIO)
        self.requests: list[str] = []  # the kind each connection asked for
        self.connections: list[web.WebSocketResponse] = []
        self.refusing = False  # answer 404, like firmware that has no /ws/state
        self.server: TestServer | None = None

    async def start(self) -> "FakeProcessor":
        app = web.Application()
        app.router.add_get("/ws/state", self._handle)
        self.server = TestServer(app)
        await self.server.start_server()
        return self

    async def stop(self) -> None:
        await self.server.close()

    async def _handle(self, request: web.Request) -> web.StreamResponse:
        if self.refusing:
            return web.Response(status=404)

        ws = web.WebSocketResponse()
        await ws.prepare(request)
        kind = (await ws.receive_json())["request"]
        self.requests.append(kind)
        self.connections.append(ws)
        await self.send(ws, kind, self.state)
        async for _ in ws:  # nothing else is expected from the driver; wait for it to leave
            pass
        return ws

    @staticmethod
    async def send(ws: web.WebSocketResponse, kind: str, state: dict) -> None:
        await ws.send_str(json.dumps({"request": kind, "state": json.dumps(state)}))

    async def report(self, **changes) -> None:
        """A change on the processor: every open connection is sent the complete new state."""
        self.state.update(changes)
        for ws in self.connections:
            if not ws.closed:
                await self.send(ws, "audio", self.state)

    async def heartbeat(self) -> None:
        for ws in self.connections:
            if not ws.closed:
                await ws.send_str(json.dumps({"heartbeat": True}))

    async def hang_up(self) -> None:
        for ws in self.connections:
            await ws.close()


class Listener:
    """Collects what a stream reports."""

    def __init__(self) -> None:
        self.states: list[dict] = []

    def __call__(self, state: dict) -> None:
        self.states.append(state)


def make_stream(processor: FakeProcessor, listener, **options) -> StateStream:
    client = HyperionClient("127.0.0.1", atlas_port=processor.server.port)
    stream = StateStream("audio", client.open_state_stream, listener, reconnect_min=0.02, reconnect_max=0.05, **options)
    stream.client = client  # so the test can close it
    return stream


async def run(processor: FakeProcessor, listener=None, **options) -> StateStream:
    stream = make_stream(processor, listener or Listener(), **options)
    stream.start()
    return stream


async def finish(stream: StateStream, processor: FakeProcessor) -> None:
    await stream.stop()
    await stream.client.close()
    await processor.stop()


# --------------------------------------------------------------------------- what is asked for and what arrives


async def test_the_kind_of_state_wanted_is_sent_and_the_first_state_arrives():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await wait_until(lambda: listener.states)

        assert processor.requests == ["audio"]
        assert listener.states[0]["volume"] == 36
    finally:
        await finish(stream, processor)


async def test_the_state_is_decoded_and_its_timestamp_dropped():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await wait_until(lambda: listener.states)

        assert listener.states == [{"power": True, "volume": 36, "mute": False, "audio_mode": "native"}]
    finally:
        await finish(stream, processor)


async def test_a_state_that_only_differs_by_timestamp_is_not_reported_again():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await wait_until(lambda: listener.states)

        for second in range(1001, 1006):  # the audio stream repeats itself every second
            await processor.report(timestamp=second)
        await processor.report(volume=40)
        await wait_until(lambda: len(listener.states) == 2)

        assert [state["volume"] for state in listener.states] == [36, 40]
    finally:
        await finish(stream, processor)


async def test_every_change_is_reported_in_order():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await wait_until(lambda: listener.states)

        await processor.report(volume=37)
        await processor.report(mute=True)
        await processor.report(audio_mode="dts-nx")
        await wait_until(lambda: len(listener.states) == 4)

        assert [(s["volume"], s["mute"], s["audio_mode"]) for s in listener.states] == [
            (36, False, "native"),
            (37, False, "native"),
            (37, True, "native"),
            (37, True, "dts-nx"),
        ]
    finally:
        await finish(stream, processor)


async def test_messages_that_are_not_states_are_ignored():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await wait_until(lambda: listener.states)
        ws = processor.connections[0]

        await processor.heartbeat()
        await ws.send_str("not json")
        await ws.send_str(json.dumps(["a", "list"]))
        await ws.send_str(json.dumps({"request": "audio", "state": "not json either"}))
        await ws.send_str(json.dumps({"request": "audio", "state": "[1, 2]"}))
        await processor.report(volume=41)
        await wait_until(lambda: len(listener.states) == 2)

        assert listener.states[1]["volume"] == 41
        assert stream.live
    finally:
        await finish(stream, processor)


async def test_a_listener_that_fails_does_not_end_the_stream():
    processor = await FakeProcessor().start()
    seen = []

    def listener(state: dict) -> None:
        seen.append(state["volume"])
        raise RuntimeError("the listener is broken")

    stream = await run(processor, listener)
    try:
        await wait_until(lambda: seen)
        await processor.report(volume=50)
        await wait_until(lambda: seen == [36, 50])
        assert len(processor.requests) == 1  # it never had to reconnect
    finally:
        await finish(stream, processor)


# --------------------------------------------------------------------------- whether the stream can be trusted


async def test_a_stream_is_live_only_while_connected():
    processor = await FakeProcessor().start()
    stream = make_stream(processor, Listener())
    try:
        assert not stream.live

        stream.start()
        await wait_until(lambda: stream.live)

        await stream.stop()
        assert not stream.live
    finally:
        await stream.client.close()
        await processor.stop()


async def test_starting_twice_opens_one_connection():
    processor = await FakeProcessor().start()
    stream = await run(processor)
    try:
        stream.start()
        await wait_until(lambda: stream.live)
        await asyncio.sleep(0.1)

        assert processor.requests == ["audio"]
    finally:
        await finish(stream, processor)


async def test_stopping_closes_the_connection():
    processor = await FakeProcessor().start()
    stream = await run(processor)
    try:
        await wait_until(lambda: stream.live)
        await stream.stop()

        await wait_until(lambda: processor.connections[0].closed)
    finally:
        await stream.client.close()
        await processor.stop()


async def test_a_silent_connection_is_replaced():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener, silence_timeout=0.2)
    try:
        await wait_until(lambda: len(processor.requests) == 1)
        await asyncio.sleep(0.1)
        assert stream.live

        await wait_until(lambda: len(processor.requests) == 2)  # nothing was heard for 0.2 s: it reconnected
        await wait_until(lambda: len(listener.states) == 2)  # and the new connection's state was reported, changed or not
    finally:
        await finish(stream, processor)


async def test_heartbeats_keep_a_quiet_connection_alive():
    processor = await FakeProcessor().start()
    stream = await run(processor, silence_timeout=0.3)
    try:
        await wait_until(lambda: stream.live)

        for _ in range(6):
            await asyncio.sleep(0.1)
            await processor.heartbeat()

        assert processor.requests == ["audio"]
        assert stream.live
    finally:
        await finish(stream, processor)


# --------------------------------------------------------------------------- reconnecting


async def test_it_reconnects_when_the_processor_hangs_up():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await wait_until(lambda: listener.states)

        processor.state["volume"] = 44  # changed while the connection was down
        await processor.hang_up()

        await wait_until(lambda: len(processor.requests) == 2)
        await wait_until(lambda: listener.states[-1]["volume"] == 44)
        assert stream.live
    finally:
        await finish(stream, processor)


async def test_an_unchanged_state_is_reported_again_after_reconnecting():
    processor = await FakeProcessor().start()
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await wait_until(lambda: listener.states)
        await processor.hang_up()

        await wait_until(lambda: len(listener.states) == 2)  # anything could have changed meanwhile, so say so
        assert listener.states[0] == listener.states[1]
    finally:
        await finish(stream, processor)


async def test_a_processor_without_the_endpoint_is_retried_until_it_has_one():
    processor = await FakeProcessor().start()
    processor.refusing = True
    listener = Listener()
    stream = await run(processor, listener)
    try:
        await asyncio.sleep(0.2)  # several refused attempts
        assert not stream.live
        assert listener.states == []

        processor.refusing = False

        await wait_until(lambda: stream.live)
        await wait_until(lambda: listener.states)
    finally:
        await finish(stream, processor)


async def test_a_processor_that_is_off_the_network_is_retried_until_it_returns():
    processor = await FakeProcessor().start()
    port = processor.server.port
    await processor.server.close()  # nobody is listening any more
    client = HyperionClient("127.0.0.1", atlas_port=port)
    listener = Listener()
    stream = StateStream("audio", client.open_state_stream, listener, reconnect_min=0.02, reconnect_max=0.05)
    stream.start()
    try:
        await asyncio.sleep(0.2)
        assert not stream.live

        app = web.Application()
        app.router.add_get("/ws/state", processor._handle)
        processor.server = TestServer(app, port=port)
        await processor.server.start_server()

        await wait_until(lambda: stream.live)
    finally:
        await stream.stop()
        await client.close()
        await processor.server.close()
