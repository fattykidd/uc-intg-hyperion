"""Tests for HyperionClient: request building, error handling, retry and session reuse (network faked)."""

import aiohttp
import pytest

from client import HyperionClient
from fakes import HOST, FakeApr16, install_fake_network


def make_client(monkeypatch, **kwargs) -> tuple[HyperionClient, FakeApr16]:
    apr = FakeApr16()
    install_fake_network(monkeypatch, apr)
    return HyperionClient(HOST, 8080, **kwargs), apr


async def test_get_json_uses_the_rest_port_and_passes_params(monkeypatch):
    client, apr = make_client(monkeypatch)

    assert await client.get_json("/api/atlas/input/name", params={"input": 3}) == {"name": "PS5"}

    method, url, kwargs = apr.log[0]
    assert (method, url) == ("GET", f"http://{HOST}:8080/api/atlas/input/name")
    assert kwargs["params"] == {"input": 3}


async def test_an_empty_reply_decodes_to_an_empty_dict(monkeypatch):
    client, apr = make_client(monkeypatch)
    apr.overrides["/v1/mute"] = (200, b"")

    assert await client.get_json("/v1/mute") == {}


async def test_get_text_returns_the_body_as_text(monkeypatch):
    client, apr = make_client(monkeypatch)
    apr.overrides["/v1/hostip"] = (200, b"10.0.0.9\n")

    assert await client.get_text("/v1/hostip") == "10.0.0.9\n"


async def test_post_sends_the_payload_as_json(monkeypatch):
    client, apr = make_client(monkeypatch)

    await client.post("/v1/vol", {"level": 30})

    assert apr.posts == [("/v1/vol", {"level": 30})]
    assert apr.state["vol"] == 30


@pytest.mark.parametrize("call", ["get", "post"])
async def test_an_http_error_status_raises(monkeypatch, call):
    client, apr = make_client(monkeypatch)
    apr.failing.add("/v1/vol")

    with pytest.raises(aiohttp.ClientResponseError) as error:
        if call == "get":
            await client.get_json("/v1/vol")
        else:
            await client.post("/v1/vol", {"level": 1})

    assert error.value.status == 500


async def test_rpc_goes_to_the_atlas_port_with_connect_headers(monkeypatch):
    client, apr = make_client(monkeypatch)
    apr.atlas_replies["GetDiracActiveSlot"] = (200, b"\x08\x02")

    status, body = await client.rpc("GetDiracActiveSlot")

    assert (status, body) == (200, b"\x08\x02")
    _, url, kwargs = apr.log[0]
    assert url == f"http://{HOST}:80/commands.v1.AtlasService/GetDiracActiveSlot"
    assert kwargs["headers"]["Content-Type"] == "application/proto"
    assert kwargs["headers"]["Connect-Protocol-Version"] == "1"
    assert kwargs["data"] == b""


async def test_rpc_merges_extra_headers_and_sends_the_body(monkeypatch):
    client, apr = make_client(monkeypatch)

    await client.rpc("SetDiracFiltering", b"\x10\x01", headers={"Origin": "http://x"})

    kwargs = apr.log[0][2]
    assert kwargs["data"] == b"\x10\x01"
    assert kwargs["headers"]["Origin"] == "http://x"
    assert kwargs["headers"]["Content-Type"] == "application/proto"


async def test_rpc_returns_an_error_status_instead_of_raising(monkeypatch):
    client, apr = make_client(monkeypatch)
    apr.atlas_replies["GetDiracActiveSlot"] = (404, b"")

    assert await client.rpc("GetDiracActiveSlot") == (404, b"")


async def test_a_dropped_connection_is_retried_once(monkeypatch):
    client, apr = make_client(monkeypatch)
    apr.stale_connections["/v1/vol"] = 1

    assert await client.get_json("/v1/vol") == {"level": 25}
    assert apr.requests == 2


async def test_a_second_dropped_connection_is_raised(monkeypatch):
    client, apr = make_client(monkeypatch)
    apr.stale_connections["/v1/vol"] = 2

    with pytest.raises(aiohttp.ServerDisconnectedError):
        await client.get_json("/v1/vol")
    assert apr.requests == 2


async def test_many_requests_share_one_session(monkeypatch):
    client, apr = make_client(monkeypatch)

    for _ in range(5):
        await client.get_json("/v1/vol")
    await client.post("/v1/vol", {"level": 1})

    assert apr.sessions_opened == 1


async def test_close_is_safe_to_repeat_and_the_session_reopens_on_demand(monkeypatch):
    client, apr = make_client(monkeypatch)

    await client.close()  # nothing opened yet
    await client.get_json("/v1/vol")
    await client.close()
    await client.close()
    await client.get_json("/v1/vol")

    assert apr.sessions_opened == 2
