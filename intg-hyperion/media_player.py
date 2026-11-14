"""
Entity definitions for the AudioControl Hyperion APR-16 integration.

This module defines the Media Player entity and maps Unfolded Circle remote
commands to the APR-16 device API.
"""

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.media_player import Attributes, Commands, DeviceClasses, Features, States
from ucapi_framework import MediaPlayerEntity

from device import Apr16

_LOG = logging.getLogger(__name__)

FEATURES = [
    Features.ON_OFF,
    Features.VOLUME,
    Features.MUTE,
    Features.MUTE_TOGGLE,
    Features.SELECT_SOURCE,
    Features.VOLUME_UP_DOWN,
]

class Apr16MediaPlayer(MediaPlayerEntity):
    """Media player entity for the AudioControl Hyperion APR-16 processor."""

    def __init__(self, device_config, device: Apr16):
        self._device = device
        self._device_config = device_config
        # Read the user's volume mode choice, defaulting to absolute if not set
        self._volume_mode = getattr(device_config, "volume_mode", "absolute")

        # Pull dynamic input names if available, falling back to empty list or defaults
        initial_sources = list(device._input_names_map.values()) if hasattr(device, "_input_names_map") and device._input_names_map else [
            "HDMI 1", "HDMI 2", "HDMI 3", "HDMI 4", "HDMI 5", "HDMI 6", "HDMI 7",
            "Digital 1", "Digital 2", "Digital 3", "Digital 4",
            "Analog 1", "Analog 2", "Analog 3", "Dante", "eArc",
        ]

        super().__init__(
            f"media_player.{device_config.identifier}",
            device_config.name,
            FEATURES,
            {
                Attributes.STATE: States.UNAVAILABLE,
                Attributes.VOLUME: 0,
                Attributes.MUTED: False,
                Attributes.SOURCE: "",
                Attributes.SOURCE_LIST: initial_sources,
            },
            device_class=DeviceClasses.RECEIVER,
            cmd_handler=self._handle_command,
        )
        # Register for push updates from the device instance
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Synchronize entity state with the device attributes cache."""
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return

        attrs = self._device.get_media_player_attributes(self._device_config.identifier)
        if attrs:
            # Refresh source list dynamically in case custom input map updated post-init
            current_sources = list(self._device._input_names_map.values()) if hasattr(self._device, "_input_names_map") and self._device._input_names_map else None
            
            update_payload = {
                Attributes.STATE: attrs.STATE,
                Attributes.VOLUME: int(attrs.VOLUME) if attrs.VOLUME is not None else 0,
                Attributes.MUTED: attrs.MUTED,
                Attributes.SOURCE: attrs.SOURCE,
            }
            if current_sources:
                update_payload[Attributes.SOURCE_LIST] = current_sources
                
            self.update(update_payload)

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        _LOG.info("[%s] Command: %s %s", self.id, cmd_id, params or "")

        try:
            if cmd_id == Commands.ON:
                await self._device.power_on()
                return StatusCodes.OK

            if cmd_id == Commands.OFF:
                await self._device.power_off()
                return StatusCodes.OK

            if cmd_id == Commands.VOLUME:
                value = float(params["volume"])
                pct = self.db_to_percent(value) if self._volume_mode == "relative" else value
                await self._device.set_volume_pct(int(round(pct)))

            if cmd_id in (Commands.VOLUME_UP, Commands.VOLUME_DOWN):
                await self._device.step_volume(1 if cmd_id == Commands.VOLUME_UP else -1)
                return StatusCodes.OK

            if cmd_id == Commands.MUTE_TOGGLE:
                current_mute = await self._device.get_mute()
                await self._device.set_mute(not current_mute)
                return StatusCodes.OK

            if cmd_id == Commands.MUTE:
                if params and "mute" in params:
                    await self._device.set_mute(bool(params["mute"]))
                    return StatusCodes.OK
                return StatusCodes.BAD_REQUEST

            if cmd_id == Commands.SELECT_SOURCE:
                if params and "source" in params:
                    await self._device.set_active_input(params["source"])
                    return StatusCodes.OK
                return StatusCodes.BAD_REQUEST

            return StatusCodes.NOT_IMPLEMENTED

        except Exception as err:
            _LOG.error("[%s] Command error: %s", self.id, err)
            return StatusCodes.SERVER_ERROR