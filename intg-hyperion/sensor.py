"""
Sensor entity definitions for the AudioControl Hyperion APR-16 integration.

Exposes read-only sensor entities for audio format, video details, and volume level.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi.sensor import Attributes, DeviceClasses, Options, States
from ucapi_framework import SensorEntity
from device import Apr16

_LOG = logging.getLogger(__name__)


class Apr16VolumeSensor(SensorEntity):
    """Sensor entity for displaying the master volume level."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.volume",
            f"{device_config.name} Volume",
            [],
            {
                Attributes.STATE: States.ON,
                Attributes.VALUE: "0.0",
            },
            device_class=DeviceClasses.CUSTOM,
            options={Options.CUSTOM_UNIT: "dB"},
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            vol = await self._device.get_volume()
            vol_str = f"{vol:.1f}" if isinstance(vol, (int, float)) else str(vol)
            self.update({
                Attributes.STATE: States.ON,
                Attributes.VALUE: vol_str,
            })
        except Exception as err:
            _LOG.debug("[%s] Failed to update volume sensor: %s", self.identifier, err)


class Apr16AudioFormatSensor(SensorEntity):
    """Sensor entity for displaying the active audio codec and format."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.audio_format",
            f"{device_config.name} Audio Format",
            [],
            {
                Attributes.STATE: States.ON,
                Attributes.VALUE: "Unknown",
            },
            device_class=DeviceClasses.CUSTOM,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            format_str = await self._device.get_audio_format() or "Unknown"
            self.update({
                Attributes.STATE: States.ON,
                Attributes.VALUE: format_str,
            })
        except Exception as err:
            _LOG.debug("[%s] Failed to update audio format sensor: %s", self.identifier, err)


class Apr16MuteSensor(SensorEntity):
    """Sensor entity for displaying master mute status."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.mute",
            f"{device_config.name} Mute",
            [],
            {Attributes.STATE: States.ON, Attributes.VALUE: "False"},
            device_class=DeviceClasses.CUSTOM,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            muted = await self._device.get_mute()
            self.update({Attributes.STATE: States.ON, Attributes.VALUE: str(muted)})
        except Exception as err:
            _LOG.debug("[%s] Failed to update mute sensor: %s", self.identifier, err)


class Apr16DisplayBrightnessSensor(SensorEntity):
    """Sensor entity for displaying front panel display brightness."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.display_brightness",
            f"{device_config.name} Display Brightness",
            [],
            {Attributes.STATE: States.ON, Attributes.VALUE: "0"},
            device_class=DeviceClasses.CUSTOM,
            options={Options.CUSTOM_UNIT: "%"},
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            brightness = await self._device.get_display_brightness()
            self.update({Attributes.STATE: States.ON, Attributes.VALUE: str(brightness)})
        except Exception as err:
            _LOG.debug("[%s] Failed to update brightness sensor: %s", self.identifier, err)


class Apr16AudioDetailSensor(SensorEntity):
    """Sensor entity for displaying comprehensive audio signal details."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.audio_detail",
            f"{device_config.name} Audio Signal",
            [],
            {Attributes.STATE: States.ON, Attributes.VALUE: "Unknown"},
            device_class=DeviceClasses.CUSTOM,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            details = await self._device.get_audio_detail()
            # Extract a friendly summary string or fallback to formatted text
            summary = details.get("summary", details.get("format", str(details)))
            self.update({Attributes.STATE: States.ON, Attributes.VALUE: str(summary)})
        except Exception as err:
            _LOG.debug("[%s] Failed to update audio detail sensor: %s", self.identifier, err)


class Apr16HostIpSensor(SensorEntity):
    """Sensor entity for displaying the processor network host IP address."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.host_ip",
            f"{device_config.name} Host IP",
            [],
            {Attributes.STATE: States.ON, Attributes.VALUE: "0.0.0.0"},
            device_class=DeviceClasses.CUSTOM,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            ip = await self._device.get_host_ip()
            self.update({Attributes.STATE: States.ON, Attributes.VALUE: str(ip)})
        except Exception as err:
            _LOG.debug("[%s] Failed to update host IP sensor: %s", self.identifier, err)


class Apr16InputBassSensor(SensorEntity):
    """Sensor entity for displaying current active input bass level (-12 to +12 dB)."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.input_bass",
            f"{device_config.name} Input Bass",
            [],
            {Attributes.STATE: States.ON, Attributes.VALUE: "0"},
            device_class=DeviceClasses.CUSTOM,
            options={Options.CUSTOM_UNIT: "dB"},
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            active_input = await self._device.get_active_input() or "HDMI 1"
            bass = await self._device.get_input_bass(active_input)
            self.update({Attributes.STATE: States.ON, Attributes.VALUE: str(bass)})
        except Exception as err:
            _LOG.debug("[%s] Failed to update input bass sensor: %s", self.identifier, err)


class Apr16InputTrebleSensor(SensorEntity):
    """Sensor entity for displaying current active input treble level (-12 to +12 dB)."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.input_treble",
            f"{device_config.name} Input Treble",
            [],
            {Attributes.STATE: States.ON, Attributes.VALUE: "0"},
            device_class=DeviceClasses.CUSTOM,
            options={Options.CUSTOM_UNIT: "dB"},
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            active_input = await self._device.get_active_input() or "HDMI 1"
            treble = await self._device.get_input_treble(active_input)
            self.update({Attributes.STATE: States.ON, Attributes.VALUE: str(treble)})
        except Exception as err:
            _LOG.debug("[%s] Failed to update input treble sensor: %s", self.identifier, err)


class Apr16VideoDetailSensor(SensorEntity):
    """Sensor entity for displaying active video resolution and HDR details."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}.video_detail",
            f"{device_config.name} Video Signal",
            [],
            {
                Attributes.STATE: States.ON,
                Attributes.VALUE: "No Signal",
            },
            device_class=DeviceClasses.CUSTOM,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        try:
            data = await self._device.get_video_detail()
            resolution = data.get("resolution", "Unknown")
            framerate = data.get("framerate", "")
            hdr = str(data.get("hdr", "SDR")).upper()

            state_str = (
                f"{resolution} @ {framerate} ({hdr})"
                if framerate
                else f"{resolution} ({hdr})"
            )
            self.update({
                Attributes.STATE: States.ON,
                Attributes.VALUE: state_str,
            })
        except Exception as err:
            _LOG.debug("[%s] Failed to update video detail sensor: %s", self.identifier, err)