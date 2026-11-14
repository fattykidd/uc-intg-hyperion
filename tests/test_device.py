"""Tests for the Apr16 device: connecting, volume, inputs, Dirac, tone and brightness."""

import asyncio

import pytest
from ucapi_framework.device import DeviceEvents

import device as device_module
from fakes import make_rig, settle
from volume import percent_to_db

# --------------------------------------------------------------------------- connecting


async def test_connecting_loads_the_processors_state(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    attrs = rig.device.get_media_player_attributes("dev1")

    assert rig.device.is_connected
    assert str(attrs.STATE.value) == "ON"
    assert attrs.SOURCE == "HDMI 2"
    assert attrs.SOUND_MODE == "2ch"
    assert rig.device.volume_pct == 25


async def test_connecting_announces_itself(monkeypatch):
    rig = await make_rig(monkeypatch, connect=False)
    events = []
    rig.device.events.on(DeviceEvents.CONNECTED, lambda *args: events.append(args))

    assert await rig.device.connect()
    await settle()

    assert events


async def test_a_processor_that_cannot_be_reached_does_not_connect(monkeypatch):
    rig = await make_rig(monkeypatch, connect=False)
    rig.apr.failing.add("/v1/power")

    assert not await rig.device.connect()
    assert not rig.device.is_connected


async def test_everything_shares_one_http_session(monkeypatch):
    rig = await make_rig(monkeypatch)
    for _ in range(5):
        await rig.device.step_volume(1)
        await rig.device.get_audio_mode()

    assert rig.apr.sessions_opened == 1


async def test_disconnecting_closes_the_session_and_reconnecting_reopens_it(monkeypatch):
    rig = await make_rig(monkeypatch)
    events = []
    rig.device.events.on(DeviceEvents.DISCONNECTED, lambda *args: events.append(args))

    await rig.device.disconnect()
    await settle()
    assert not rig.device.is_connected and events
    assert rig.device._api._session is None

    assert await rig.device.connect()
    await rig.device.step_volume(1)
    assert rig.apr.state["vol"] == 26
    assert rig.apr.sessions_opened == 2


# --------------------------------------------------------------------------- volume


async def test_absolute_mode_steps_one_percent_and_shows_percent(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)

    for _ in range(10):
        await rig.device.step_volume(1)

    assert rig.apr.volume_posts() == list(range(26, 36))
    assert rig.remote.last("media_player.dev1", "volume") == 35
    assert rig.apr.rejected == []


async def test_relative_mode_shows_db_but_always_sends_whole_percent(monkeypatch):
    rig = await make_rig(monkeypatch, volume_mode="relative", vol=42)
    assert rig.remote.last("media_player.dev1", "volume") == round(percent_to_db(42))

    for direction in (-1, -1, 1, 1, 1):
        await rig.device.step_volume(direction)

    sent = rig.apr.volume_posts()
    assert all(isinstance(level, int) and 0 < level <= 100 for level in sent)
    assert sent[0] < 42, "volume down must lower the volume"
    assert rig.apr.rejected == []
    shown = rig.remote.last("media_player.dev1", "volume")
    assert shown == round(percent_to_db(rig.apr.state["vol"])) and shown < 0


async def test_relative_mode_always_moves_even_where_one_db_is_less_than_a_percent(monkeypatch):
    rig = await make_rig(monkeypatch, volume_mode="relative", vol=0)

    await rig.device.step_volume(1)

    assert rig.apr.volume_posts() == [1]


async def test_the_remote_is_updated_before_the_processor_answers(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    shown_when_sent = []
    original_post = rig.device._api.post

    async def post(path, payload=None, **kwargs):
        await settle()  # the remote gets its update while the request is still on its way
        shown_when_sent.append(rig.remote.last("media_player.dev1", "volume"))
        return await original_post(path, payload, **kwargs)

    monkeypatch.setattr(rig.device._api, "post", post)
    await rig.device.step_volume(1)

    assert shown_when_sent == [26]


async def test_a_burst_of_presses_reaches_the_processor_in_order(monkeypatch):
    import asyncio

    rig = await make_rig(monkeypatch, vol=25)

    await asyncio.gather(*(rig.device.step_volume(1) for _ in range(6)))

    assert rig.apr.volume_posts() == [26, 27, 28, 29, 30, 31]
    assert rig.apr.state["vol"] == 31


async def test_a_failed_change_puts_the_real_volume_back_on_the_remote(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    rig.apr.failing_posts.add("/v1/vol")  # the change is refused, but reading the volume still works

    await rig.device.step_volume(1)
    await settle()

    assert rig.device.volume_pct == 25
    assert rig.remote.last("media_player.dev1", "volume") == 25


async def test_a_dropped_connection_does_not_lose_the_change(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    rig.apr.stale_connections["/v1/vol"] = 1

    await rig.device.step_volume(1)

    assert rig.apr.state["vol"] == 26


@pytest.mark.parametrize(("start", "direction"), [(100, 1), (0, -1)])
async def test_nothing_is_sent_past_either_end_of_the_scale(monkeypatch, start, direction):
    rig = await make_rig(monkeypatch, vol=start)

    await rig.device.step_volume(direction)

    assert rig.apr.volume_posts() == []


@pytest.mark.parametrize(("asked", "sent"), [(150, 100), (-5, 0), (41.6, 42), (30, 30)])
async def test_set_volume_pct_clamps_and_rounds_to_a_whole_percent(monkeypatch, asked, sent):
    rig = await make_rig(monkeypatch, vol=25)

    await rig.device.set_volume_pct(asked)

    assert rig.apr.volume_posts() == [sent]
    assert rig.apr.rejected == []


async def test_resync_replaces_the_cached_volume(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    rig.apr.state["vol"] = 60  # changed on the front panel

    await rig.device.resync_volume()
    await settle()

    assert rig.device.volume_pct == 60
    assert rig.remote.last("media_player.dev1", "volume") == 60


async def test_mute_and_power_are_pushed_to_the_remote(monkeypatch):
    rig = await make_rig(monkeypatch)

    await rig.device.set_mute(True)
    await rig.device.power_off()
    await settle()

    assert rig.apr.state["mute"] is True and rig.apr.state["power"] == "0"
    assert rig.remote.last("media_player.dev1", "muted") is True
    assert rig.remote.last("media_player.dev1", "state") == "OFF"

    await rig.device.power_toggle()
    assert rig.apr.state["power"] == "1"


# --------------------------------------------------------------------------- inputs


async def test_custom_input_names_reach_the_remote_after_connecting(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert rig.remote.last("media_player.dev1", "source_list")[:4] == ["Apple TV", "HDMI 2", "PS5", "HDMI 4"]


async def test_choosing_a_custom_name_sends_the_hardware_input(monkeypatch):
    rig = await make_rig(monkeypatch)

    await rig.device.set_active_input("apple tv")

    assert ("/api/atlas/input/active", {"input": "HDMI 1"}) in rig.apr.posts


async def test_choosing_a_default_name_in_any_case_sends_the_hardware_input(monkeypatch):
    rig = await make_rig(monkeypatch)

    await rig.device.set_active_input("hdmi 3")

    assert ("/api/atlas/input/active", {"input": "HDMI 3"}) in rig.apr.posts


async def test_the_active_input_is_reported_by_its_custom_name(monkeypatch):
    rig = await make_rig(monkeypatch, source="HDMI 1")

    assert await rig.device.get_active_input_name() == "Apple TV"


async def test_a_non_json_host_ip_is_still_understood(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.overrides["/v1/hostip"] = (200, b"10.0.0.9\n")

    assert await rig.device.get_host_ip() == "10.0.0.9"


# --------------------------------------------------------------------------- Dirac


async def test_dirac_slot_names_are_read_from_the_processor(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.atlas_replies["GetDiracFilterSlots"] = (200, b"\x0bMovies\x1a\x0bMusic\x1a")

    assert await rig.device.async_fetch_dirac_slot_names() == {1: "Movies", 2: "Music"}
    assert rig.device.dirac_slot_names == {1: "Movies", 2: "Music"}


@pytest.mark.parametrize("reply", [(200, b""), (500, b""), (200, b"\x00\x01")])
async def test_an_unusable_dirac_reply_keeps_the_existing_names(monkeypatch, reply):
    rig = await make_rig(monkeypatch)
    before = dict(rig.device.dirac_slot_names)
    rig.apr.atlas_replies["GetDiracFilterSlots"] = reply

    await rig.device.async_fetch_dirac_slot_names()

    assert rig.device.dirac_slot_names == before
    assert 0 in before


@pytest.mark.parametrize(("reply", "slot"), [((200, b"\x08\x02"), 2), ((200, b""), 0), ((500, b""), 0)])
async def test_the_active_dirac_slot_is_read(monkeypatch, reply, slot):
    rig = await make_rig(monkeypatch)
    rig.apr.atlas_replies["GetDiracActiveSlot"] = reply

    assert await rig.device.async_get_dirac_active_slot() == slot


@pytest.mark.parametrize(("slot", "payload"), [(0, "1001"), (1, "08011001"), (2, "08021001"), (7, "1001")])
async def test_switching_dirac_slot_sends_the_captured_payload(monkeypatch, slot, payload):
    rig = await make_rig(monkeypatch)

    assert await rig.device.async_set_dirac_filter_slot(slot) is True

    assert rig.apr.rpcs[-1] == ("SetDiracFilterSlot", bytes.fromhex(payload))


async def test_dirac_filtering_can_be_switched_and_failures_are_reported(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.device.async_set_dirac_filtering(True) is True
    assert rig.apr.rpcs[-1] == ("SetDiracFiltering", bytes.fromhex("080110011801"))
    assert await rig.device.async_set_dirac_filtering(False) is True
    assert rig.apr.rpcs[-1] == ("SetDiracFiltering", bytes.fromhex("10011801"))

    rig.apr.atlas_replies["SetDiracFiltering"] = (500, b"")
    assert await rig.device.async_set_dirac_filtering(True) is False


# --------------------------------------------------------------------------- tone and brightness


async def test_bass_steps_on_the_active_input_and_stops_at_the_limit(monkeypatch):
    rig = await make_rig(monkeypatch)  # bass starts at 11

    assert await rig.device.step_input_tone("bass", +1) == 12
    assert await rig.device.step_input_tone("bass", +1) == 12
    assert ("/api/atlas/input/HDMI 2/bass/12", {"inputId": 0}) in rig.apr.posts


async def test_treble_stops_at_the_lower_limit(monkeypatch):
    rig = await make_rig(monkeypatch, treble=-12)

    assert await rig.device.step_input_tone("treble", -1) == -12


@pytest.mark.parametrize(("start", "delta", "expected"), [(5, -10, 0), (95, +10, 100), (50, +10, 60), (0, -10, 0)])
async def test_brightness_steps_stay_between_0_and_100(monkeypatch, start, delta, expected):
    rig = await make_rig(monkeypatch, brightness=start)

    assert await rig.device.step_display_brightness(delta) == expected
    assert rig.apr.state["brightness"] == expected


# --------------------------------------------------------------------------- polling


async def wait_until(condition, timeout: float = 2.0) -> None:
    """Wait for something that happens in the background (the poll loop)."""
    async with asyncio.timeout(timeout):
        while not condition():
            await asyncio.sleep(0.01)


@pytest.fixture
def fast_polling(monkeypatch):
    monkeypatch.setattr(device_module, "POLL_INTERVAL", 0.02)
    monkeypatch.setattr(device_module, "FULL_REFRESH_INTERVAL", 3600)


async def test_changes_made_on_the_device_reach_the_remote(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch, vol=25)

    rig.apr.state.update(vol=60, mute=True, source="HDMI 4", mode="multich", power="0")

    await wait_until(lambda: rig.remote.last("media_player.dev1", "state") == "OFF")
    await settle()
    assert rig.remote.last("media_player.dev1", "volume") == 60
    assert rig.remote.last("media_player.dev1", "muted") is True
    assert rig.remote.last("media_player.dev1", "source") == "HDMI 4"
    assert rig.device.volume_pct == 60


async def test_relative_mode_shows_a_front_panel_change_in_db(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch, volume_mode="relative", vol=25)

    rig.apr.state["vol"] = 70

    await wait_until(lambda: rig.device.volume_pct == 70)
    await settle()
    assert rig.remote.last("media_player.dev1", "volume") == round(percent_to_db(70))


async def test_sensors_follow_a_change_made_on_the_device(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch, vol=25)

    rig.apr.state["vol"] = 40

    await wait_until(lambda: rig.remote.last("sensor.dev1.volume_absolute", "value") == "40.0")


async def test_nothing_is_pushed_while_nothing_changes(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch)
    pushed = len(rig.remote.updates)
    requests = rig.apr.requests

    await wait_until(lambda: rig.apr.requests > requests + 15)  # many polls have happened
    await settle()

    assert len(rig.remote.updates) == pushed


async def test_the_slow_sensors_are_refreshed_on_the_slower_schedule(monkeypatch):
    monkeypatch.setattr(device_module, "POLL_INTERVAL", 0.02)
    monkeypatch.setattr(device_module, "FULL_REFRESH_INTERVAL", 0.1)
    rig = await make_rig(monkeypatch)

    rig.apr.state["brightness"] = 80  # not part of the core state that is watched

    await wait_until(lambda: rig.remote.last("sensor.dev1.display_brightness", "value") == "80")


async def test_a_volume_change_made_while_polling_is_not_overwritten(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)
    original_get = rig.device.get_volume

    async def get_volume_then_the_user_presses_a_button():
        old = await original_get()
        await rig.device.set_volume_pct(40)  # happens while the poll is still reading
        return old

    monkeypatch.setattr(rig.device, "get_volume", get_volume_then_the_user_presses_a_button)

    await rig.device.refresh_state()

    assert rig.device.volume_pct == 40


async def test_polling_survives_an_outage_and_catches_up(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch, vol=25)
    rig.apr.failing.add("/v1/power")
    await asyncio.sleep(0.1)  # several failed polls

    rig.apr.failing.clear()
    rig.apr.state["vol"] = 55

    await wait_until(lambda: rig.device.volume_pct == 55)


async def test_polling_stops_when_the_device_disconnects(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch)
    task = rig.device._poll_task
    assert task and not task.done()

    await rig.device.disconnect()
    requests = rig.apr.requests
    await asyncio.sleep(0.1)

    assert task.done() and rig.apr.requests == requests


async def test_reconnecting_does_not_start_a_second_poll_loop(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch)
    await rig.device.disconnect()

    assert await rig.device.connect()
    task = rig.device._poll_task
    assert await rig.device.connect()

    assert rig.device._poll_task is task
