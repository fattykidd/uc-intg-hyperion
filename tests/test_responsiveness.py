"""
Tests that the driver stays quiet and quick: the Remote must never wait on the processor, and a change must not
turn into a burst of requests to the processor or of messages to the Remote.

This was a real problem: every change makes every entity refresh, the sensors each asked the processor for their
value, and the select and media player resent themselves in full. One or two volume presses were enough to make
the Remote report that the processor was not responding.
"""

import asyncio

from ucapi import StatusCodes
from ucapi.media_player import Commands as PlayerCommands

from fakes import make_rig, settle


def gets(rig) -> list[str]:
    """The path of every read made of the processor so far."""
    return [url.split("//", 1)[1].split("/", 1)[1] for method, url, _ in rig.apr.log if method == "GET"]


def hold_volume_requests(rig, monkeypatch):
    """Make the processor slow to answer volume changes: they wait until the test lets them through."""
    release = asyncio.Event()
    original_post = rig.device._api.post

    async def slow_post(path, payload=None, **kwargs):
        if path == "/v1/vol":
            await release.wait()
        return await original_post(path, payload, **kwargs)

    monkeypatch.setattr(rig.device._api, "post", slow_post)
    return release


# --------------------------------------------------------------------------- the Remote never waits on the processor


async def test_a_volume_command_returns_before_the_processor_answers(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    release = hold_volume_requests(rig, monkeypatch)

    async with asyncio.timeout(1):  # would time out if the command waited for the processor
        result = await rig.command(rig.media_player, PlayerCommands.VOLUME_UP)

    await settle()

    assert result == StatusCodes.OK
    assert rig.remote.last("media_player.dev1", "volume") == 26
    assert rig.apr.volume_posts() == []

    release.set()
    await rig.device.wait_volume_sent()
    assert rig.apr.volume_posts() == [26]


async def test_presses_made_while_the_processor_is_busy_are_merged_into_one_request(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    release = hold_volume_requests(rig, monkeypatch)

    await rig.command(rig.media_player, PlayerCommands.VOLUME_UP)
    await settle()  # the first request is now on its way and waiting for the processor
    for _ in range(5):
        await rig.command(rig.media_player, PlayerCommands.VOLUME_UP)
    release.set()
    await rig.device.wait_volume_sent()

    assert rig.apr.volume_posts() == [26, 31], "the first press, then only the newest volume"
    assert rig.apr.state["vol"] == 31
    assert rig.remote.last("media_player.dev1", "volume") == 31


async def test_a_refused_volume_change_shows_the_real_volume_again(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    rig.apr.failing_posts.add("/v1/vol")

    await rig.command(rig.media_player, PlayerCommands.VOLUME_UP)
    await rig.device.wait_volume_sent()
    await settle()

    assert rig.remote.last("media_player.dev1", "volume") == 25


async def test_disconnecting_stops_a_volume_change_that_is_still_waiting(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    hold_volume_requests(rig, monkeypatch)

    await rig.device.step_volume(1)
    await rig.device.disconnect()

    assert rig.device._vol_sender is None
    assert rig.apr.volume_posts() == []


# --------------------------------------------------------------------------- a change is not a burst of requests


async def test_a_volume_press_does_not_read_the_processor_for_the_sensors(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    await settle()
    reads_before = len(gets(rig))

    for _ in range(5):
        await rig.command(rig.media_player, PlayerCommands.VOLUME_UP)
        await rig.device.wait_volume_sent()
    await settle()

    assert gets(rig)[reads_before:] == [], "nothing is read from the processor because of a volume press"


async def test_every_entity_refreshing_reads_each_slow_value_only_once(monkeypatch):
    rig = await make_rig(monkeypatch)
    await settle()
    reads_before = len(gets(rig))

    for _ in range(10):
        rig.device.push_update()
        await settle()

    assert gets(rig)[reads_before:] == []


async def test_a_value_is_read_again_once_it_is_old_enough(monkeypatch):
    import device as device_module

    monkeypatch.setattr(device_module, "SENSOR_CACHE_TTL", 0.02)
    rig = await make_rig(monkeypatch)
    rig.apr.state["brightness"] = 80
    await asyncio.sleep(0.05)

    rig.device.push_update()
    await settle()

    assert rig.remote.last("sensor.dev1.display_brightness", "value") == "80"


async def test_overlapping_reads_of_the_same_thing_share_one_request(monkeypatch):
    rig = await make_rig(monkeypatch)
    calls = []

    async def slow_read():
        calls.append(1)
        await asyncio.sleep(0.01)
        return 42

    results = await asyncio.gather(*(rig.device.cached("thing", slow_read) for _ in range(5)))

    assert results == [42] * 5
    assert len(calls) == 1


async def test_a_failed_read_is_not_remembered(monkeypatch):
    rig = await make_rig(monkeypatch)
    outcomes = iter([RuntimeError("down"), 7])

    async def flaky_read():
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    try:
        await rig.device.cached("flaky", flaky_read)
    except RuntimeError:
        pass

    assert await rig.device.cached("flaky", flaky_read) == 7


async def test_switching_input_drops_what_was_read_for_the_old_one(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.state.update(source="HDMI 3", bass=-4)

    await rig.device.set_active_input("HDMI 3")
    await settle()

    assert rig.remote.last("sensor.dev1.input_bass", "value") == "-4"


async def test_the_signal_description_follows_a_change_in_the_signal(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.streams_supported = True
    await rig.device.disconnect()
    assert await rig.device.connect()
    await settle()

    rig.apr.overrides["/v1/audiodetail"] = (200, b'{"detail": "DTS-HD MA 7.1"}')
    rig.apr.stream("audio", audio_format="DTS-HD MA", bit_depth=24, sample_rate=96000)
    await settle()

    assert rig.remote.last("sensor.dev1.audio_detail", "value") == "DTS-HD MA 7.1"


# --------------------------------------------------------------------------- the Remote is not sent things twice


async def test_the_audio_mode_select_is_not_resent_when_nothing_changed(monkeypatch):
    rig = await make_rig(monkeypatch)
    await settle()
    sent = len(rig.remote.updates)

    for _ in range(10):
        rig.device.push_update()
        await settle()

    assert len(rig.remote.updates) == sent


async def test_the_select_is_sent_in_full_again_after_the_device_was_gone(monkeypatch):
    rig = await make_rig(monkeypatch)
    select = rig.entity("select", "audio_mode")
    await settle()

    await rig.device.disconnect()
    await select.sync_state()
    assert rig.remote.last("select.dev1.audio_mode", "state") == "UNAVAILABLE"

    assert await rig.device.connect()
    await settle()

    pushed = rig.remote.last("select.dev1.audio_mode", "options")
    assert pushed and rig.remote.last("select.dev1.audio_mode", "state") == "ON"


async def test_the_audio_mode_select_follows_a_change_of_mode(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.streams_supported = True
    await rig.device.disconnect()
    assert await rig.device.connect()
    await settle()

    rig.apr.stream("audio", audio_mode="dts-nx")
    await settle()

    assert rig.remote.last("select.dev1.audio_mode", "current_option") == "DTS Neural:X"
    assert rig.remote.last("sensor.dev1.audio_mode", "value") == "DTS Neural:X"
