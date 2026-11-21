"""
Tests for the entities as the Remote sees them: what exists, what it shows and how it reacts to commands.

Commands are sent through each entity's public command() method, the same path the Remote uses.
"""

import pytest
from ucapi import StatusCodes
from ucapi.button import Commands as ButtonCommands
from ucapi.media_player import Commands as PlayerCommands

from fakes import DEVICE_ID, make_rig, settle
from volume import db_to_percent, percent_to_db

# Entity ids and names are registered on the user's Remote, so changing one breaks their activities
# and UI pages. This list is the contract: if it has to change, that is a breaking release.
EXPECTED_ENTITIES = {
    "media_player.dev1": "APR",
    "select.dev1.audio_mode": "APR Audio Mode",
    "select.dev1.dirac_slot": "APR Dirac Slot",
    "switch.dev1.dirac_filtering": "APR Dirac Filtering",
    "sensor.dev1.volume_absolute": "APR Absolute Volume",
    "sensor.dev1.volume_relative": "APR Relative Volume",
    "sensor.dev1.audio_format": "APR Audio Format",
    "sensor.dev1.mute": "APR Mute",
    "sensor.dev1.temperature": "APR Temperature",
    "sensor.dev1.display_brightness": "APR Display Brightness",
    "sensor.dev1.audio_detail": "APR Audio Signal",
    "sensor.dev1.dirac_filtering": "APR Dirac Filtering Status",
    "sensor.dev1.audio_bit_depth": "APR Audio Bit Depth",
    "sensor.dev1.audio_sample_rate": "APR Audio Sample Rate",
    "sensor.dev1.host_ip": "APR Host IP",
    "sensor.dev1.input_bass": "APR Input Bass",
    "sensor.dev1.input_treble": "APR Input Treble",
    "sensor.dev1.video_detail": "APR Video Signal",
    "sensor.dev1.dirac_active_slot": "APR Active Dirac Slot",
    "sensor.dev1.audio_mode": "APR Audio Mode",
    "sensor.dev1.active_input": "APR Active Input",
    "button.dev1.reboot": "APR Reboot",
    "button.dev1.hpd": "APR Trigger HPD",
    "button.dev1.bass_up": "APR Bass +1dB",
    "button.dev1.bass_down": "APR Bass -1dB",
    "button.dev1.treble_up": "APR Treble +1dB",
    "button.dev1.treble_down": "APR Treble -1dB",
    "button.dev1.brightness_up": "APR Brightness +10%",
    "button.dev1.brightness_down": "APR Brightness -10%",
    "sensor.dev1.video_format": "APR Video Format",
}


async def test_the_driver_creates_exactly_the_registered_entities(monkeypatch):
    rig = await make_rig(monkeypatch, connect=False)

    assert {entity_id: entity.name["en"] for entity_id, entity in rig.entities.items()} == EXPECTED_ENTITIES


# --------------------------------------------------------------------------- sensors

SENSOR_VALUES = {
    "volume_absolute": "25.0",
    "volume_relative": f"{percent_to_db(25):.1f}",
    "mute": "Unmuted",
    "host_ip": "10.0.0.5",
    "display_brightness": "50",
    "audio_mode": "Stereo",
    "dirac_filtering": "Off",
    "audio_bit_depth": "24-bit",
    "audio_sample_rate": "48 kHz",
    "audio_format": "Dolby Atmos",
    "audio_detail": "Dolby Atmos",
    "video_detail": "Chroma: 422 | Bit Depth: 8bit | Quantization: Limited | Pixel Clock: 296700kHz",
    "active_input": "HDMI 2",
    "input_bass": "11",
    "input_treble": "-3",
    "dirac_active_slot": "Slot 0",
    "temperature": "74.5",
    "video_format": "3840x2160@23.98p",
}


async def test_every_sensor_is_covered_by_these_tests():
    assert {entity_id.split(".", 2)[2] for entity_id in EXPECTED_ENTITIES if entity_id.startswith("sensor.")} == set(
        SENSOR_VALUES
    )


@pytest.mark.parametrize(("name", "value"), SENSOR_VALUES.items())
async def test_sensors_show_what_the_processor_reports(monkeypatch, name, value):
    rig = await make_rig(monkeypatch)

    entity_id = f"sensor.{DEVICE_ID}.{name}"
    assert rig.remote.last(entity_id, "value") == value
    assert rig.remote.last(entity_id, "state") == "ON"


async def test_sensors_follow_the_volume(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)

    await rig.device.step_volume(1)
    await settle()

    assert rig.remote.last("sensor.dev1.volume_absolute", "value") == "26.0"
    assert rig.remote.last("sensor.dev1.volume_relative", "value") == f"{percent_to_db(26):.1f}"


async def test_a_sensor_whose_read_fails_goes_unavailable_instead_of_crashing(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.failing.add("/v1/mute")

    await rig.entity("sensor", "mute").sync_state()

    assert rig.remote.last("sensor.dev1.mute", "state") == "UNAVAILABLE"


async def test_sensors_are_unavailable_once_the_device_disconnects(monkeypatch):
    rig = await make_rig(monkeypatch)
    await rig.device.disconnect()

    for name in SENSOR_VALUES:
        await rig.entity("sensor", name).sync_state()
        assert rig.remote.last(f"sensor.dev1.{name}", "state") == "UNAVAILABLE", name


@pytest.mark.parametrize(("raw", "friendly"), [("dts-nx", "DTS Neural:X"), ("multich", "All Channel Stereo"), ("native", "Native")])
async def test_the_audio_mode_sensor_uses_the_same_names_as_the_select(monkeypatch, raw, friendly):
    rig = await make_rig(monkeypatch, mode=raw)

    assert rig.remote.last("sensor.dev1.audio_mode", "value") == friendly
    await rig.entity("select", "audio_mode").sync_state()
    assert rig.remote.last("select.dev1.audio_mode", "current_option") == friendly


async def test_the_audio_mode_sensor_shows_a_mode_it_does_not_know_as_reported(monkeypatch):
    rig = await make_rig(monkeypatch, mode="some-new-mode")

    assert rig.remote.last("sensor.dev1.audio_mode", "value") == "some-new-mode"


@pytest.mark.parametrize(
    ("bit", "sample", "shown_bit", "shown_rate"),
    [(16, 44100, "16-bit", "44.1 kHz"), (24, 96000, "24-bit", "96 kHz"), (32, 192000, "32-bit", "192 kHz"), (0, 0, "No Signal", "No Signal")],
)
async def test_bit_depth_and_sample_rate_sensors(monkeypatch, bit, sample, shown_bit, shown_rate):
    rig = await make_rig(monkeypatch, bit=bit, sample=sample)

    assert rig.remote.last("sensor.dev1.audio_bit_depth", "value") == shown_bit
    assert rig.remote.last("sensor.dev1.audio_sample_rate", "value") == shown_rate


# The processor's three Dirac slots are numbered from 0, and the first name it lists belongs to slot 0.
SLOT_NAMES_REPLY = b"\x0b4dB current\x1a\x0b2dB current\x1a\x0b6dB current\x1a"


async def rig_with_named_slots(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.atlas_replies["GetDiracFilterSlots"] = (200, SLOT_NAMES_REPLY)
    await rig.device.async_fetch_dirac_slot_names()
    return rig


@pytest.mark.parametrize(("slot_reply", "name"), [((200, b""), "4dB current"), ((200, b"\x08\x01"), "2dB current"), ((200, b"\x08\x02"), "6dB current")])
async def test_the_active_dirac_slot_sensor_names_the_right_slot(monkeypatch, slot_reply, name):
    rig = await rig_with_named_slots(monkeypatch)
    rig.apr.atlas_replies["GetDiracActiveSlot"] = slot_reply
    await rig.device.refresh_state()

    await rig.entity("sensor", "dirac_active_slot").sync_state()
    await rig.entity("select", "dirac_slot").sync_state()

    assert rig.remote.last("sensor.dev1.dirac_active_slot", "value") == name
    assert rig.remote.last("select.dev1.dirac_slot", "current_option") == name
    assert rig.remote.last("select.dev1.dirac_slot", "options") == ["4dB current", "2dB current", "6dB current"]


@pytest.mark.parametrize(("name", "payload"), [("4dB current", "1001"), ("2dB current", "08011001"), ("6dB current", "08021001")])
async def test_choosing_a_dirac_slot_by_name_selects_that_slot(monkeypatch, name, payload):
    rig = await rig_with_named_slots(monkeypatch)

    assert await rig.command(rig.entity("select", "dirac_slot"), "select_option", {"option": name}) == StatusCodes.OK

    assert rig.apr.rpcs[-1] == ("SetDiracFilterSlot", bytes.fromhex(payload))


async def test_choosing_a_dirac_slot_updates_the_sensor_at_once(monkeypatch):
    rig = await rig_with_named_slots(monkeypatch)
    assert rig.remote.last("sensor.dev1.dirac_active_slot", "value") in ("Slot 0", "4dB current")

    assert await rig.command(rig.entity("select", "dirac_slot"), "select_option", {"option": "2dB current"}) == StatusCodes.OK
    await settle()

    assert rig.apr.state["slot"] == 1
    assert rig.remote.last("sensor.dev1.dirac_active_slot", "value") == "2dB current"

async def test_an_unknown_dirac_slot_name_is_refused_and_changes_nothing(monkeypatch):
    rig = await rig_with_named_slots(monkeypatch)
    sent_before = len(rig.apr.rpcs)

    result = await rig.command(rig.entity("select", "dirac_slot"), "select_option", {"option": "No Such Slot"})

    assert result == StatusCodes.BAD_REQUEST
    assert len(rig.apr.rpcs) == sent_before, "a command was sent to the processor"
    assert rig.apr.state["slot"] == 0


@pytest.mark.parametrize(
    ("command", "payload"),
    [
        ("select_next", "08011001"),      # from slot 0 to slot 1
        ("select_previous", "08021001"),  # from slot 0 wraps round to the last slot
        ("select_first", "1001"),
        ("select_last", "08021001"),
    ],
)
async def test_stepping_through_the_dirac_slots(monkeypatch, command, payload):
    rig = await rig_with_named_slots(monkeypatch)
    await rig.device.refresh_state()
    await rig.entity("select", "dirac_slot").sync_state()

    assert await rig.command(rig.entity("select", "dirac_slot"), command) == StatusCodes.OK

    assert rig.apr.rpcs[-1] == ("SetDiracFilterSlot", bytes.fromhex(payload))


async def test_an_unknown_dirac_select_command_is_not_implemented(monkeypatch):
    rig = await rig_with_named_slots(monkeypatch)

    assert await rig.command(rig.entity("select", "dirac_slot"), "select_prev") == StatusCodes.NOT_IMPLEMENTED

async def test_the_dirac_switch_and_sensor_show_the_devices_filtering_state(monkeypatch):
    rig = await make_rig(monkeypatch, dirac=True)

    assert rig.remote.last("switch.dev1.dirac_filtering", "state") == "ON"
    assert rig.remote.last("sensor.dev1.dirac_filtering", "value") == "Active"


async def test_the_dirac_switch_and_sensor_show_filtering_off(monkeypatch):
    rig = await make_rig(monkeypatch, dirac=False)

    assert rig.remote.last("switch.dev1.dirac_filtering", "state") == "OFF"
    assert rig.remote.last("sensor.dev1.dirac_filtering", "value") == "Off"


async def test_toggling_the_dirac_switch_changes_the_device(monkeypatch):
    rig = await make_rig(monkeypatch, dirac=False)
    switch = rig.entity("switch", "dirac_filtering")

    assert await rig.command(switch, "toggle") == StatusCodes.OK
    await settle()
    assert rig.apr.state["dirac"] is True
    assert rig.remote.last("sensor.dev1.dirac_filtering", "value") == "Active"

    assert await rig.command(switch, "toggle") == StatusCodes.OK
    await settle()
    assert rig.apr.state["dirac"] is False
    assert rig.remote.last("switch.dev1.dirac_filtering", "state") == "OFF"


async def test_a_refused_dirac_command_leaves_the_state_alone(monkeypatch):
    rig = await make_rig(monkeypatch, dirac=False)
    rig.apr.atlas_replies["SetDiracFiltering"] = (500, b"")

    assert await rig.command(rig.entity("switch", "dirac_filtering"), "on") == StatusCodes.SERVER_ERROR

    assert rig.device.dirac_filtering is False


async def test_dirac_state_is_unknown_when_the_device_cannot_be_asked(monkeypatch):
    rig = await make_rig(monkeypatch, connect=False)
    rig.apr.atlas_replies["GetDiracFiltering"] = (500, b"")

    assert await rig.device.connect()  # Dirac is not essential for connecting
    await settle()

    assert rig.device.dirac_filtering is None
    assert rig.remote.last("switch.dev1.dirac_filtering", "state") == "UNKNOWN"
    assert rig.remote.last("sensor.dev1.dirac_filtering", "value") == "Unknown"


async def test_the_dirac_switch_is_unavailable_when_disconnected(monkeypatch):
    rig = await make_rig(monkeypatch)
    await rig.device.disconnect()

    await rig.entity("switch", "dirac_filtering").sync_state()

    assert rig.remote.last("switch.dev1.dirac_filtering", "state") == "UNAVAILABLE"


# --------------------------------------------------------------------------- buttons


async def test_reboot_and_hpd_buttons_call_the_processor(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.entity("button", "reboot"), ButtonCommands.PUSH) == StatusCodes.OK
    assert await rig.command(rig.entity("button", "hpd"), ButtonCommands.PUSH) == StatusCodes.OK

    assert ("/v1/reboot", {}) in rig.apr.posts
    assert ("/v1/hdmi/output/hpd", {"state": True}) in rig.apr.posts


@pytest.mark.parametrize(
    ("button", "key", "start", "expected"),
    [
        ("bass_up", "bass", 11, 12),
        ("bass_up", "bass", 12, 12),
        ("bass_down", "bass", -12, -12),
        ("bass_down", "bass", 0, -1),
        ("treble_up", "treble", 3, 4),
        ("treble_down", "treble", -12, -12),
        ("brightness_up", "brightness", 50, 60),
        ("brightness_up", "brightness", 95, 100),
        ("brightness_down", "brightness", 5, 0),
    ],
)
async def test_tone_and_brightness_buttons_step_within_their_limits(monkeypatch, button, key, start, expected):
    rig = await make_rig(monkeypatch, **{key: start})

    assert await rig.command(rig.entity("button", button), ButtonCommands.PUSH) == StatusCodes.OK

    assert rig.apr.state[key] == expected


async def test_a_failing_button_press_reports_an_error_instead_of_raising(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.failing.add("/v1/reboot")

    assert await rig.command(rig.entity("button", "reboot"), ButtonCommands.PUSH) == StatusCodes.SERVER_ERROR


async def test_a_button_ignores_commands_that_are_not_a_push(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.entity("button", "hpd"), "bogus") == StatusCodes.NOT_IMPLEMENTED
    assert rig.apr.posts == []


# --------------------------------------------------------------------------- media player


async def test_volume_up_and_down_in_absolute_mode(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)

    assert await rig.command(rig.media_player, PlayerCommands.VOLUME_UP) == StatusCodes.OK
    assert await rig.command(rig.media_player, PlayerCommands.VOLUME_UP) == StatusCodes.OK
    assert await rig.command(rig.media_player, PlayerCommands.VOLUME_DOWN) == StatusCodes.OK

    assert rig.apr.volume_posts() == [26, 27, 26]
    assert rig.remote.last("media_player.dev1", "volume") == 26


async def test_volume_up_in_relative_mode_shows_decibels(monkeypatch):
    rig = await make_rig(monkeypatch, volume_mode="relative", vol=50)

    assert await rig.command(rig.media_player, PlayerCommands.VOLUME_UP) == StatusCodes.OK

    assert rig.apr.state["vol"] > 50
    assert rig.remote.last("media_player.dev1", "volume") == round(percent_to_db(rig.apr.state["vol"]))
    assert rig.apr.rejected == []


async def test_the_volume_command_sets_a_percent_in_absolute_mode(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.media_player, PlayerCommands.VOLUME, {"volume": 60}) == StatusCodes.OK

    assert rig.apr.volume_posts() == [60]


async def test_the_volume_command_takes_decibels_in_relative_mode(monkeypatch):
    rig = await make_rig(monkeypatch, volume_mode="relative")

    assert await rig.command(rig.media_player, PlayerCommands.VOLUME, {"volume": -40}) == StatusCodes.OK

    assert rig.apr.volume_posts() == [round(db_to_percent(-40))]


async def test_a_positive_decibel_value_is_refused_not_turned_into_full_volume(monkeypatch):
    rig = await make_rig(monkeypatch, volume_mode="relative")

    assert await rig.command(rig.media_player, PlayerCommands.VOLUME, {"volume": 30}) == StatusCodes.BAD_REQUEST

    assert rig.apr.volume_posts() == []


async def test_the_volume_command_needs_a_volume(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.media_player, PlayerCommands.VOLUME, {}) == StatusCodes.BAD_REQUEST


async def test_mute_toggle_and_mute(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.media_player, PlayerCommands.MUTE_TOGGLE) == StatusCodes.OK
    assert rig.apr.state["mute"] is True
    assert await rig.command(rig.media_player, PlayerCommands.MUTE, {"mute": False}) == StatusCodes.OK
    assert rig.apr.state["mute"] is False
    assert await rig.command(rig.media_player, PlayerCommands.MUTE, {}) == StatusCodes.BAD_REQUEST


async def test_power_commands(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.media_player, PlayerCommands.OFF) == StatusCodes.OK
    assert rig.apr.state["power"] == "0"
    assert await rig.command(rig.media_player, PlayerCommands.ON) == StatusCodes.OK
    assert rig.apr.state["power"] == "1"


async def test_selecting_a_source_by_its_custom_name(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.media_player, PlayerCommands.SELECT_SOURCE, {"source": "PS5"}) == StatusCodes.OK
    assert rig.apr.state["source"] == "HDMI 3"
    assert await rig.command(rig.media_player, PlayerCommands.SELECT_SOURCE, {}) == StatusCodes.BAD_REQUEST


async def test_a_command_the_processor_rejects_returns_an_error(monkeypatch):
    rig = await make_rig(monkeypatch)
    rig.apr.failing.add("/v1/mute")

    assert await rig.command(rig.media_player, PlayerCommands.MUTE, {"mute": True}) == StatusCodes.SERVER_ERROR


async def test_an_unknown_player_command_is_not_implemented(monkeypatch):
    rig = await make_rig(monkeypatch)

    assert await rig.command(rig.media_player, "bogus") == StatusCodes.NOT_IMPLEMENTED


async def test_the_player_shows_power_source_and_volume(monkeypatch):
    rig = await make_rig(monkeypatch, vol=25)

    assert rig.remote.last("media_player.dev1", "state") == "ON"
    assert rig.remote.last("media_player.dev1", "source") == "HDMI 2"
    assert rig.remote.last("media_player.dev1", "volume") == 25


# --------------------------------------------------------------------------- selects and switch


async def test_the_audio_mode_select_sends_the_devices_name_for_the_mode(monkeypatch):
    rig = await make_rig(monkeypatch)
    select = rig.entity("select", "audio_mode")

    assert await rig.command(select, "select_option", {"option": "All Channel Stereo"}) == StatusCodes.OK
    assert ("/v1/audiomode", {"mode": "multich"}) in rig.apr.posts
    assert await rig.command(select, "select_option", {"option": "Nonsense"}) == StatusCodes.BAD_REQUEST


async def test_the_audio_mode_select_shows_the_friendly_name(monkeypatch):
    rig = await make_rig(monkeypatch, mode="dts-nx")

    await rig.entity("select", "audio_mode").sync_state()

    assert rig.remote.last("select.dev1.audio_mode", "current_option") == "DTS Neural:X"


async def test_the_dirac_switch_turns_filtering_on_and_off(monkeypatch):
    rig = await make_rig(monkeypatch)
    switch = rig.entity("switch", "dirac_filtering")

    assert await rig.command(switch, "on") == StatusCodes.OK
    assert rig.apr.rpcs[-1] == ("SetDiracFiltering", bytes.fromhex("080110011801"))
    assert await rig.command(switch, "off") == StatusCodes.OK
    assert rig.apr.rpcs[-1] == ("SetDiracFiltering", bytes.fromhex("10011801"))

    rig.apr.atlas_replies["SetDiracFiltering"] = (500, b"")
    assert await rig.command(switch, "on") == StatusCodes.SERVER_ERROR