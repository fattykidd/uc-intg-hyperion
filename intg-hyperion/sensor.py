"""
Sensor entity definitions for the AudioControl Hyperion APR-16 integration.

Exposes read-only sensor entities for audio format, video details, and volume level.
"""

import logging
from typing import Any

from device import Apr16
from ucapi_framework.entities import SensorEntity

_LOG = logging.getLogger(__name__)


class Apr16VolumeSensor(SensorEntity):
    """
    Sensor entity for displaying the master volume level.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            identifier=f"sensor.{device_config.identifier}_volume",
            name=f"{device_config.name} Volume",
            native_unit_of_measurement=None,
            device_class=SensorEntity.DeviceClass.TEXT,
        )
        self._device = device
        self._device_config = device_config
        self.state = "0.0"

    async def async_update(self) -> None:
        """Fetch the latest master volume level from the device."""
        try:
            vol = await self._device.get_volume()
            vol_str = (
                f"{vol:.1f}" if isinstance(vol, (int, float)) else str(vol)
            )
            if self.state != vol_str:
                self.state = vol_str
                await self.push_update()
        except Exception as err:
            _LOG.debug(
                "[%s] Failed to update volume sensor: %s", self.identifier, err
            )


class Apr16AudioFormatSensor(SensorEntity):
    """
    Sensor entity for displaying the active audio codec and format.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            identifier=f"sensor.{device_config.identifier}_audio_format",
            name=f"{device_config.name} Audio Format",
            native_unit_of_measurement=None,
            device_class=SensorEntity.DeviceClass.TEXT,
        )
        self._device = device
        self._device_config = device_config
        self.state = "Unknown"

    async def async_update(self) -> None:
        """Fetch the latest audio format from the device."""
        try:
            format_str = await self._device.get_audio_format()
            if self.state != format_str:
                self.state = format_str
                await self.push_update()
        except Exception as err:
            _LOG.debug(
                "[%s] Failed to update audio format sensor: %s",
                self.identifier,
                err,
            )


class Apr16VideoDetailSensor(SensorEntity):
    """
    Sensor entity for displaying active video resolution and HDR details.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            identifier=f"sensor.{device_config.identifier}_video_detail",
            name=f"{device_config.name} Video Signal",
            native_unit_of_measurement=None,
            device_class=SensorEntity.DeviceClass.TEXT,
        )
        self._device = device
        self._device_config = device_config
        self.state = "No Signal"

    async def async_update(self) -> None:
        """Fetch the latest video details from the device."""
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

            if self.state != state_str:
                self.state = state_str
                await self.push_update()
        except Exception as err:
            _LOG.debug(
                "[%s] Failed to update video detail sensor: %s",
                self.identifier,
                err,
            )