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
            f"sensor.{device_config.identifier}_volume",
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
            f"sensor.{device_config.identifier}_audio_format",
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


class Apr16VideoDetailSensor(SensorEntity):
    """Sensor entity for displaying active video resolution and HDR details."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"sensor.{device_config.identifier}_video_detail",
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