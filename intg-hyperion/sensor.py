"""
Sensor entities for the AudioControl Hyperion APR-16 integration.

Read-only values: volume, mute, audio and video signal details, input tone, Dirac slot and so on.
Each sensor only says what it is called and how to read its value; Apr16Sensor does the rest.
"""

from __future__ import annotations

import logging

from ucapi.sensor import Attributes, DeviceClasses, Options, States
from ucapi_framework import SensorEntity

from const import API_TO_UI_AUDIO_MODE, DEFAULT_INPUTS
from device import Apr16

_LOG = logging.getLogger(__name__)


def format_bit_depth(bits: int) -> str:
    """16 -> "16-bit". 0 means the device sees no audio signal."""
    return f"{bits}-bit" if bits > 0 else "No Signal"


def format_sample_rate(hertz: int) -> str:
    """48000 -> "48 kHz", 44100 -> "44.1 kHz". 0 means the device sees no audio signal."""
    if hertz <= 0:
        return "No Signal"
    return f"{hertz / 1000:g} kHz"


class Apr16Sensor(SensorEntity):
    """
    Base class for APR-16 sensors.

    Subclasses set ``suffix`` and ``label`` (together they give the entity its id and name),
    optionally ``initial``, ``custom_unit`` and ``device_class``, and implement ``read()``.
    """

    suffix: str
    """Last part of the entity id, e.g. "mute" gives "sensor.<device>.mute"."""

    label: str
    """Name shown on the remote, after the device name."""

    initial: str = "Unknown"
    """Value shown until the first successful read."""

    custom_unit: str | None = None
    """Unit shown next to the value, if any."""

    device_class: DeviceClasses | None = DeviceClasses.CUSTOM

    def __init__(self, device_config, device: Apr16) -> None:
        super().__init__(
            f"sensor.{device_config.identifier}.{self.suffix}",
            f"{device_config.name} {self.label}",
            [],
            {Attributes.STATE: States.ON, Attributes.VALUE: self.initial},
            device_class=self.device_class,
            options={Options.CUSTOM_UNIT: self.custom_unit} if self.custom_unit else None,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def read(self) -> str:
        """Return the value to display."""
        raise NotImplementedError

    async def sync_state(self) -> None:
        """Refresh the value from the device, or mark the sensor unavailable if that isn't possible."""
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return

        try:
            value = await self.read()
        except Exception as err:
            _LOG.debug("[%s] Failed to update %s: %s", self.id, self.label, err)
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return

        self.update({Attributes.STATE: States.ON, Attributes.VALUE: str(value)})


# --- Volume -----------------------------------------------------------------


class Apr16AbsoluteVolumeSensor(Apr16Sensor):
    """Volume as a percent (0-100)."""

    suffix = "volume_absolute"
    label = "Absolute Volume"
    initial = "0.0"
    custom_unit = "%"

    async def read(self) -> str:
        return f"{self._device.volume_pct:.1f}"


class Apr16RelativeVolumeSensor(Apr16Sensor):
    """Volume in decibels."""

    suffix = "volume_relative"
    label = "Relative Volume"
    initial = "0.0"
    custom_unit = "dB"

    async def read(self) -> str:
        return f"{self._device.volume_db:.1f}"


class Apr16MuteSensor(Apr16Sensor):
    """Master mute status."""

    suffix = "mute"
    label = "Mute"
    initial = "Unmuted"

    async def read(self) -> str:
        return "Muted" if await self._device.get_mute() else "Unmuted"


# --- Signal -----------------------------------------------------------------


class Apr16AudioFormatSensor(Apr16Sensor):
    """Active audio codec and format."""

    suffix = "audio_format"
    label = "Audio Format"

    async def read(self) -> str:
        return await self._device.get_audio_format() or "Unknown"


class Apr16AudioDetailSensor(Apr16Sensor):
    """Audio signal summary."""

    suffix = "audio_detail"
    label = "Audio Signal"

    async def read(self) -> str:
        details = await self._device.get_audio_detail()
        if "result" in details:  # a bare status reply rather than signal details
            return "Active" if details["result"] == "ok" else "Unknown"
        return details.get("summary", details.get("format", "Active"))


class Apr16AudioBitDepthSensor(Apr16Sensor):
    """Bit depth of the incoming audio signal."""

    suffix = "audio_bit_depth"
    label = "Audio Bit Depth"
    initial = "No Signal"

    async def read(self) -> str:
        return format_bit_depth(await self._device.get_audio_bit_depth())


class Apr16AudioSampleRateSensor(Apr16Sensor):
    """Sample rate of the incoming audio signal."""

    suffix = "audio_sample_rate"
    label = "Audio Sample Rate"
    initial = "No Signal"

    async def read(self) -> str:
        return format_sample_rate(await self._device.get_audio_sample_rate())


class Apr16VideoDetailSensor(Apr16Sensor):
    """Active video resolution, frame rate and HDR format."""

    suffix = "video_detail"
    label = "Video Signal"
    initial = "No Signal"

    async def read(self) -> str:
        data = await self._device.get_video_detail()
        resolution = data.get("resolution", "Unknown")
        framerate = data.get("framerate", "")
        hdr = str(data.get("hdr", "SDR")).upper()
        return f"{resolution} @ {framerate} ({hdr})" if framerate else f"{resolution} ({hdr})"


# --- Processing -------------------------------------------------------------


class Apr16AudioModeSensor(Apr16Sensor):
    """Active audio processing mode, by the same friendly name the audio mode select uses."""

    suffix = "audio_mode"
    label = "Audio Mode"

    async def read(self) -> str:
        mode = await self._device.get_audio_mode()
        return API_TO_UI_AUDIO_MODE.get(mode, mode) or "Unknown"


class Apr16ActiveInputSensor(Apr16Sensor):
    """Active input, using the user's own name for it."""

    suffix = "active_input"
    label = "Active Input"

    async def read(self) -> str:
        return await self._device.get_active_input_name() or "Unknown"


class Apr16InputBassSensor(Apr16Sensor):
    """Bass level of the active input (-12 to +12 dB)."""

    suffix = "input_bass"
    label = "Input Bass"
    initial = "0"
    custom_unit = "dB"

    async def read(self) -> str:
        active_input = await self._device.get_active_input() or DEFAULT_INPUTS[0]
        return str(await self._device.get_input_bass(active_input))


class Apr16InputTrebleSensor(Apr16Sensor):
    """Treble level of the active input (-12 to +12 dB)."""

    suffix = "input_treble"
    label = "Input Treble"
    initial = "0"
    custom_unit = "dB"

    async def read(self) -> str:
        active_input = await self._device.get_active_input() or DEFAULT_INPUTS[0]
        return str(await self._device.get_input_treble(active_input))


class Apr16DiracSlotSensor(Apr16Sensor):
    """Active Dirac Live filter slot, by name."""

    suffix = "dirac_active_slot"
    label = "Active Dirac Slot"
    initial = "Slot 0"
    device_class = None

    async def read(self) -> str:
        slot = self._device.dirac_slot
        if slot is None:
            return "Unknown"
        return self._device.dirac_slot_names.get(slot, f"Slot {slot}")


class Apr16DiracFilteringSensor(Apr16Sensor):
    """Whether Dirac Live room correction is on."""

    suffix = "dirac_filtering"
    label = "Dirac Filtering Status"
    initial = "Unknown"
    device_class = None

    async def read(self) -> str:
        filtering = self._device.dirac_filtering
        return "Unknown" if filtering is None else ("On" if filtering else "Off")


# --- System -----------------------------------------------------------------


class Apr16DisplayBrightnessSensor(Apr16Sensor):
    """Front panel display brightness."""

    suffix = "display_brightness"
    label = "Display Brightness"
    initial = "0"
    custom_unit = "%"

    async def read(self) -> str:
        return str(await self._device.get_display_brightness())


class Apr16HostIpSensor(Apr16Sensor):
    """The processor's network IP address."""

    suffix = "host_ip"
    label = "Host IP"
    initial = "0.0.0.0"

    async def read(self) -> str:
        return await self._device.get_host_ip()
