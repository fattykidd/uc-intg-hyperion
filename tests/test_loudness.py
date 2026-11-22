"""Tests for the Loudness switch."""

from ucapi import StatusCodes

from fakes import make_rig, settle, wait_until

SWITCH = "switch.dev1.loudness"
SENSOR = "sensor.dev1.loudness"


async def streaming_rig(monkeypatch, **options):
    """A connected device whose state streams are up."""
    rig = await make_rig(monkeypatch, streams=True, **options)
    await wait_until(lambda: rig.device.streams_live)
    await settle()
    return rig


async def test_the_switch_shows_loudness_on(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=True)

    assert rig.remote.last(SWITCH, "state") == "ON"


async def test_the_switch_shows_loudness_off(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=False)

    assert rig.remote.last(SWITCH, "state") == "OFF"


async def test_a_change_made_in_the_web_ui_reaches_the_remote(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=False)

    rig.apr.stream("speakers", loudness_enabled=True)
    await wait_until(lambda: rig.remote.last(SWITCH, "state") == "ON")

    rig.apr.stream("speakers", loudness_enabled=False)
    await wait_until(lambda: rig.remote.last(SWITCH, "state") == "OFF")


async def test_switching_loudness_on_sends_the_devices_own_request(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=False)

    assert await rig.command(rig.entity("switch", "loudness"), "on") == StatusCodes.OK

    assert rig.apr.rpcs[-1] == ("SetDSP2Loudness", bytes.fromhex("0801"))
    assert rig.remote.last(SWITCH, "state") == "ON"
    assert rig.device.loudness is True


async def test_switching_loudness_off_sends_an_empty_request(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=True)

    assert await rig.command(rig.entity("switch", "loudness"), "off") == StatusCodes.OK

    assert rig.apr.rpcs[-1] == ("SetDSP2Loudness", b"")
    assert rig.remote.last(SWITCH, "state") == "OFF"
    assert rig.device.loudness is False


async def test_toggling_flips_the_setting_each_time(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=False)
    switch = rig.entity("switch", "loudness")

    assert await rig.command(switch, "toggle") == StatusCodes.OK
    assert rig.apr.state["loudness"] is True

    assert await rig.command(switch, "toggle") == StatusCodes.OK
    assert rig.apr.state["loudness"] is False


async def test_a_refused_change_is_reported_and_the_display_stays(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=False)
    rig.apr.atlas_replies["SetDSP2Loudness"] = (500, b"")

    assert await rig.command(rig.entity("switch", "loudness"), "on") == StatusCodes.SERVER_ERROR

    assert rig.remote.last(SWITCH, "state") == "OFF"
    assert rig.device.loudness is False


async def test_an_unknown_command_is_not_implemented(monkeypatch):
    rig = await streaming_rig(monkeypatch)

    assert await rig.command(rig.entity("switch", "loudness"), "dim") == StatusCodes.NOT_IMPLEMENTED
    assert all(name != "SetDSP2Loudness" for name, _ in rig.apr.rpcs)


async def test_the_state_is_unknown_when_the_device_has_not_reported_it(monkeypatch):
    rig = await make_rig(monkeypatch)  # firmware without streams: nothing tells us the setting

    assert rig.remote.last(SWITCH, "state") == "UNKNOWN"


async def test_switching_loudness_works_even_without_streams(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.entity("switch", "loudness"), "on") == StatusCodes.OK

    assert rig.remote.last(SWITCH, "state") == "ON"
    assert rig.apr.rpcs[-1] == ("SetDSP2Loudness", bytes.fromhex("0801"))


async def test_the_switch_is_unavailable_on_a_unit_without_loudness(monkeypatch):
    rig = await streaming_rig(monkeypatch)

    rig.apr.stream("speakers", loudness_capability="unsupported")

    await wait_until(lambda: rig.remote.last(SWITCH, "state") == "UNAVAILABLE")


async def test_the_switch_is_unavailable_when_disconnected(monkeypatch):
    rig = await streaming_rig(monkeypatch)

    await rig.device.disconnect()
    await rig.entity("switch", "loudness").sync_state()

    assert rig.remote.last(SWITCH, "state") == "UNAVAILABLE"


# --------------------------------------------------------------------------- the companion sensor


async def test_the_sensor_shows_loudness_on_and_off(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=False)
    assert rig.remote.last(SENSOR, "value") == "Off"

    rig.apr.stream("speakers", loudness_enabled=True)
    await wait_until(lambda: rig.remote.last(SENSOR, "value") == "On")


async def test_the_sensor_follows_the_switch(monkeypatch):
    rig = await streaming_rig(monkeypatch, loudness=False)

    assert await rig.command(rig.entity("switch", "loudness"), "on") == StatusCodes.OK

    await wait_until(lambda: rig.remote.last(SENSOR, "value") == "On")


async def test_the_sensor_is_unknown_when_the_device_has_not_reported_loudness(monkeypatch):
    rig = await make_rig(monkeypatch)  # firmware without streams

    assert rig.remote.last(SENSOR, "value") == "Unknown"


async def test_the_sensor_says_when_a_unit_has_no_loudness(monkeypatch):
    rig = await streaming_rig(monkeypatch)

    rig.apr.stream("speakers", loudness_capability="unsupported")

    await wait_until(lambda: rig.remote.last(SENSOR, "value") == "Not Supported")

