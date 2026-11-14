"""
HyperionClient against a real aiohttp server on localhost.

The other tests fake aiohttp's ClientSession. These use the real thing, so they cover what a fake cannot:
that requests are really formed the way the client says they are, that errors and timeouts surface as the
exceptions the rest of the code expects, and that one session really means one TCP connection.
"""

import asyncio

import pytest

aiohttp = pytest.importorskip("aiohttp")
pytest.importorskip("aiohttp.web")
from aiohttp import web  # noqa: E402
from aiohttp.test_utils import TestServer  # noqa: E402

from client import HyperionClient  # noqa: E402


async def start_server() -> TestServer:
    async def echo(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "query": dict(request.query),
                "body": await request.json() if request.can_read_body else None,
                "peer_port": request.transport.get_extra_info("peername")[1],
            }
        )

    async def broken(request: web.Request) -> web.Response:
        return web.Response(status=500)

    async def slow(request: web.Request) -> web.Response:
        await asyncio.sleep(2)
        return web.Response()

    async def rpc(request: web.Request) -> web.Response:
        return web.Response(
            body=await request.read(),
            headers={"X-Content-Type": request.headers["Content-Type"], "X-Connect": request.headers["Connect-Protocol-Version"]},
        )

    app = web.Application()
    app.router.add_get("/echo", echo)
    app.router.add_post("/echo", echo)
    app.router.add_get("/broken", broken)
    app.router.add_get("/slow", slow)
    app.router.add_post("/commands.v1.AtlasService/Echo", rpc)

    server = TestServer(app)
    await server.start_server()
    return server


async def test_params_and_json_arrive_as_sent():
    server = await start_server()
    client = HyperionClient("127.0.0.1", server.port)
    try:
        assert (await client.get_json("/echo", params={"input": 3}))["query"] == {"input": "3"}
        assert (await client.get_json("/echo"))["query"] == {}

        await client.post("/echo", {"level": 30})
    finally:
        await client.close()
        await server.close()


async def test_requests_reuse_one_tcp_connection():
    server = await start_server()
    client = HyperionClient("127.0.0.1", server.port)
    try:
        peer_ports = {(await client.get_json("/echo"))["peer_port"] for _ in range(5)}
    finally:
        await client.close()
        await server.close()

    assert len(peer_ports) == 1, "a new connection was opened for some of the requests"


async def test_an_error_status_raises_client_response_error():
    server = await start_server()
    client = HyperionClient("127.0.0.1", server.port)
    try:
        with pytest.raises(aiohttp.ClientResponseError) as error:
            await client.get_json("/broken")
    finally:
        await client.close()
        await server.close()

    assert error.value.status == 500


async def test_a_slow_device_times_out():
    server = await start_server()
    client = HyperionClient("127.0.0.1", server.port, timeout=0.2)
    try:
        with pytest.raises(TimeoutError):
            await client.get_json("/slow")
    finally:
        await client.close()
        await server.close()


async def test_an_unreachable_device_raises_a_client_error():
    server = await start_server()
    port = server.port
    await server.close()  # nothing is listening any more

    client = HyperionClient("127.0.0.1", port)
    try:
        with pytest.raises(aiohttp.ClientConnectionError):
            await client.get_json("/echo")
    finally:
        await client.close()


async def test_rpc_sends_the_body_and_connect_headers_and_returns_unfavourable_statuses():
    server = await start_server()
    client = HyperionClient("127.0.0.1", server.port, atlas_port=server.port)
    try:
        status, body = await client.rpc("Echo", b"\x08\x01")
        missing_status, _ = await client.rpc("NoSuchMethod")
    finally:
        await client.close()
        await server.close()

    assert (status, body) == (200, b"\x08\x01")
    assert missing_status == 404
