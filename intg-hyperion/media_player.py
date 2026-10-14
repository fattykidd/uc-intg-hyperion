"""
Entity definitions for the AudioControl Hyperion APR-16 integration.

This module defines the Media Player entity and maps Unfolded Circle remote
commands to the APR-16 device API.
"""

import ucapi
import logging
from typing import Any

from ucapi import media_player, EntityTypes
from device import Apr16

from ucapi_framework import create_entity_id, MediaPlayerEntity
from ucapi.media_player import DeviceClasses, Attributes
from ucapi_framework.entities import MediaPlayerEntity

_LOG = logging.getLogger(__name__)


class Apr16MediaPlayer(MediaPlayerEntity):
    """
    Media player entity for the AudioControl Hyperion APR-16 processor.
    """

    def __init__(self, device: Apr16):
        # Initialize using attributes defined in the device class
        super().__init__(
            identifier=device.identifier,
            name=device.name,
            features=[
                media_player.Features.ON_OFF,
                media_player.Features.VOLUME,
                media_player.Features.MUTE,
                media_player.Features.SELECT_SOURCE,
            ],
            supported_source_list=[
                "HDMI 1",
                "HDMI 2",
                "HDMI 3",
                "HDMI 4",
                "HDMI 5",
                "HDMI 6",
                "HDMI 7",
                "Digital 1",
                "Digital 2",
                "Digital 3",
                "Digital 4",
                "Analog 1",
                "Analog 2",
                "Analog 3",
                "Analog 4",
                "Analog 5",
            ],
        )
        self._device = device

    async def async_turn_on(self) -> None:
        """Turn the processor on."""
        _LOG.debug("[%s] Entity command: Turn ON", self.identifier)
        await self._device.power_on()

    async def async_turn_off(self) -> None:
        """Turn the processor off (standby)."""
        _LOG.debug("[%s] Entity command: Turn OFF", self.identifier)
        await self._device.power_off()

    async def async_set_volume(self, volume: float) -> None:
        """Set master volume level."""
        _LOG.debug(
            "[%s] Entity command: Set Volume to %s", self.identifier, volume
        )
        await self._device.set_volume(volume)

    async def async_set_mute(self, mute: bool) -> None:
        """Set mute state."""
        _LOG.debug(
            "[%s] Entity command: Set Mute to %s", self.identifier, mute
        )
        await self._device.set_mute(mute)

    async def async_select_source(self, source: str) -> None:
        """Select active input source."""
        _LOG.debug(
            "[%s] Entity command: Select Source %s", self.identifier, source
        )
        await self._device.set_active_input(source)
