"""Tests for the Apr16 device following the processor's live state streams."""

import asyncio

import pytest

import device as device_module
from fakes import make_rig, settle, wait_until
from volume import percent_to_db


@pytest.fixture
def fast_polling(monkeypatch):
    monkeypatch.setattr(device_module, "POLL_INTERVAL", 0.02)
    monkeypatch.setattr(device_module, "FULL_REFRESH_INTERVAL", 3600)


async def streaming_rig(monkeypatch, **options):
    """A connected device whose three state streams are up."""
    rig = await make_rig(monkeypatch, streams=True, **options)
    await wait_until(lambda: rig.device.streams_live)
    await settle()
    return rig


# --------------------------------------------------------------------------- following the streams


async def test_the_device_asks_for_the_audio_inputs_dirac_and_speakers_streams(monkeypatch):
    rig = await streaming_rig(monkeypatch)

    assert sorted(rig.apr.stream_requests) == ["audio", "dirac", "inputs", "speakers"]


async def test_a_change_made_on_the_device_reaches_the_remote_without_polling(monkeypatch):
    rig = await streaming_rig(monkeypatch, vol=25)  # the poll interval is 5 s, so only a stream can be this fast

    rig.apr.state["mode"] = "multich"  # the select entity reads the mode back from the device's REST API
    rig.apr.stream("audio", volume=60, mute=True, power=False, audio_mode="multich")

    await wait_until(lambda: rig.remote.last("media_player.dev1", "state") == "OFF")
    await settle()
    assert rig.remote.last("media_player.dev1", "volume") == 60
    assert rig.remote.last("media_player.dev1", "muted") is True
    assert rig.remote.last("select.dev1.audio_mode", "current_option") == "All Channel Stereo"
    assert rig.device.volume_pct == 60


async def test_relative_mode_shows_a_front_panel_change_in_db(monkeypatch):
    rig = await streaming_rig(monkeypatch, volume_mode="relative", vol=25)

    rig.apr.stream("audio", volume=70)

    await wait_until(lambda: rig.device.volume_pct == 70)
    await settle()
    assert rig.remote.last("media_player.dev1", "volume") == round(percent_to_db(70))


async def test_an_input_changed_on_the_device_is_shown_by_its_custom_name(monkeypatch):
    rig = await streaming_rig(monkeypatch, source="HDMI 1")

    rig.apr.stream("inputs", active_audio_name="HDMI 3", active_input="HDMI 3")  # named "PS5" on the fake device

    await wait_until(lambda: rig.remote.last("media_player.dev1", "source") == "PS5")


async def test_a_new_audio_signal_reaches_the_sensors(monkeypatch):
    rig = await streaming_rig(monkeypatch, bit=0, sample=0)
    assert rig.remote.last("sensor.dev1.audio_sample_rate", "value") == "No Signal"

    rig.apr.stream("audio", audio_format="Dolby TrueHD", bit_depth=24, sample_rate=96000)

    await wait_until(lambda: rig.remote.last("sensor.dev1.audio_sample_rate", "value") == "96 kHz")
    await wait_until(lambda: rig.remote.last("sensor.dev1.audio_bit_depth", "value") == "24-bit")
    assert rig.device.audio_signal.codec == "Dolby TrueHD"


async def test_dirac_filtering_changed_in_the_web_ui_reaches_the_remote(monkeypatch):
    rig = await streaming_rig(monkeypatch, dirac=False)

    rig.apr.stream("dirac", filtering_enabled=True)

    await wait_until(lambda: rig.remote.last("switch.dev1.dirac_filtering", "state") == "ON")
    await wait_until(lambda: rig.remote.last("sensor.dev1.dirac_filtering", "value") == "Active")


async def test_a_dirac_slot_changed_in_the_web_ui_reaches_the_remote(monkeypatch):
    rig = await streaming_rig(monkeypatch, slot=0)
    rig.device._dirac_slot_names_map = {0: "4dB current", 1: "2dB current", 2: "6dB current"}

    rig.apr.stream("dirac", active_slot=1)

    await wait_until(lambda: rig.remote.last("sensor.dev1.dirac_active_slot", "value") == "2dB current")
    await wait_until(lambda: rig.remote.last("select.dev1.dirac_slot", "current_option") == "2dB current")


async def test_values_the_device_sends_in_an_unexpected_form_are_ignored(monkeypatch):
    rig = await streaming_rig(monkeypatch, vol=25, slot=1)

    rig.apr.stream("audio", volume="loud", mute="yes", power=None, audio_mode=None, bit_depth=None)
    rig.apr.stream("dirac", active_slot=7, filtering_enabled="maybe")
    rig.apr.stream("inputs", active_audio_name=None, active_input=3)
    await settle()

    attrs = rig.device.get_media_player_attributes("dev1")
    assert (rig.device.volume_pct, attrs.MUTED, rig.device.dirac_slot) == (25, False, 1)
    assert str(attrs.STATE.value) == "ON"
    assert attrs.SOURCE == "HDMI 2"


async def test_nothing_is_pushed_when_a_state_repeats(monkeypatch):
    rig = await streaming_rig(monkeypatch)
    pushed = len(rig.remote.updates)

    for _ in range(5):
        rig.apr.stream("audio")  # the device repeats its audio state every second
        rig.apr.stream("inputs")
        rig.apr.stream("dirac")
        rig.apr.stream("speakers")
    await settle()

    assert len(rig.remote.updates) == pushed


# --------------------------------------------------------------------------- polling underneath


async def test_the_device_is_not_polled_while_its_streams_are_live(monkeypatch, fast_polling):
    rig = await streaming_rig(monkeypatch)
    await asyncio.sleep(0.1)  # let a poll that was already under way finish
    requests = rig.apr.requests

    await asyncio.sleep(0.3)  # fifteen poll intervals

    assert rig.apr.requests == requests


async def test_polling_takes_over_when_the_streams_go_down(monkeypatch, fast_polling):
    rig = await streaming_rig(monkeypatch, vol=25)

    rig.apr.drop_streams()
    await wait_until(lambda: not rig.device.streams_live)
    rig.apr.state["vol"] = 70

    await wait_until(lambda: rig.device.volume_pct == 70)


async def test_a_device_without_streams_is_polled_as_before(monkeypatch, fast_polling):
    rig = await make_rig(monkeypatch, vol=25)  # like firmware that has no /ws/state
    assert not rig.device.streams_live

    rig.apr.state["vol"] = 60

    await wait_until(lambda: rig.device.volume_pct == 60)


async def test_the_full_refresh_still_runs_while_the_streams_are_live(monkeypatch):
    monkeypatch.setattr(device_module, "POLL_INTERVAL", 0.02)
    monkeypatch.setattr(device_module, "FULL_REFRESH_INTERVAL", 0.1)
    rig = await streaming_rig(monkeypatch, vol=25)

    rig.apr.state["vol"] = 30  # a change the streams were not told about

    await wait_until(lambda: rig.device.volume_pct == 30)


# --------------------------------------------------------------------------- volume changed from the remote


async def test_the_devices_reports_of_our_own_volume_changes_do_not_make_the_display_jump(monkeypatch):
    monkeypatch.setattr(device_module, "VOLUME_SETTLE", 0.1)
    rig = await streaming_rig(monkeypatch, vol=36)

    await rig.device.set_volume_pct(40)
    rig.apr.stream("audio", volume=38)  # the device reports the steps on its way to 40
    await settle()
    assert rig.device.volume_pct == 40

    rig.apr.stream("audio", volume=40)
    await asyncio.sleep(0.2)
    assert rig.device.volume_pct == 40
    assert rig.remote.last("media_player.dev1", "volume") == 40


async def test_a_volume_change_the_device_refused_is_corrected(monkeypatch):
    monkeypatch.setattr(device_module, "VOLUME_SETTLE", 0.1)
    rig = await streaming_rig(monkeypatch, vol=75)

    await rig.device.set_volume_pct(80)  # the device's maximum volume is 75: it stays there and says nothing
    assert rig.device.volume_pct == 80

    await wait_until(lambda: rig.device.volume_pct == 75)
    await settle()
    assert rig.remote.last("media_player.dev1", "volume") == 75


async def test_a_front_panel_change_after_ours_is_shown(monkeypatch):
    monkeypatch.setattr(device_module, "VOLUME_SETTLE", 0.05)
    rig = await streaming_rig(monkeypatch, vol=36)

    await rig.device.set_volume_pct(40)
    rig.apr.stream("audio", volume=40)
    await asyncio.sleep(0.1)
    rig.apr.stream("audio", volume=45)

    await wait_until(lambda: rig.device.volume_pct == 45)


# --------------------------------------------------------------------------- connecting and disconnecting


async def test_disconnecting_closes_the_streams(monkeypatch):
    rig = await streaming_rig(monkeypatch)

    await rig.device.disconnect()

    assert not rig.device.streams_live
    assert rig.apr.open_streams and all(stream.closed for stream in rig.apr.open_streams)


async def test_reconnecting_does_not_open_a_second_set_of_streams(monkeypatch):
    rig = await streaming_rig(monkeypatch)
    streams = rig.device._streams

    assert await rig.device.connect()
    await settle()

    assert rig.device._streams is streams
    assert len(rig.apr.stream_requests) == 4
