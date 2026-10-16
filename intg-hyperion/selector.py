"""
Select entity definition for audio modes on the AudioControl Hyperion APR-16.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.select import Attributes, Commands, States
from ucapi_framework import SelectEntity
from device import Apr16

_LOG = logging.getLogger(__name__)


class Apr16AudioModeSelect(SelectEntity):
    """
    Select entity for changing audio listening/upmixing modes.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"select.{device_config.identifier}_audio_mode",
            f"{device_config.name} Audio Mode",
            {
                Attributes.STATE: States.ON,
                Attributes.OPTIONS: [
                    "Stereo",
                    "All Channel Stereo",
                    "Dolby Surround",
                    "DTS Neural:X",
                    "Dolby Mode",
                    "Native",
                ],
                Attributes.CURRENT_OPTION: "Stereo",
            },
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Synchronize entity state with the device."""
        if not self._device.is_connected:
            self.update({Attributes.STATE: States.UNAVAILABLE})
            return
        
        # Pull current mode from device or keep tracked state
        self.update({
            Attributes.STATE: States.ON,
            Attributes.CURRENT_OPTION: getattr(self, "_current_option", "Stereo"),
        })

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle command callbacks from the remote UI."""
        if cmd_id != Commands.SELECT_OPTION:
            return StatusCodes.NOT_IMPLEMENTED
        
        option = params.get("option") if params else None
        if not option:
            return StatusCodes.BAD_REQUEST

        _LOG.debug("[%s] Selecting audio mode: %s", self._device.log_id, option)
        try:
            await self._device.set_audio_mode(option)
            self._current_option = option
            self.update({
                Attributes.STATE: States.ON,
                Attributes.CURRENT_OPTION: option,
            })
            await self.push_update()
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Failed to set audio mode: %s", self._device.log_id, err)
            return StatusCodes.SERVER_ERROR