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

# Map clean UI display names to the exact backend API strings
AUDIO_MODE_MAPPING = {
    "Direct Mode": "dspdirectmode",
    "DTS Neural:X": "dts-nx",
    "Stereo": "2ch",
    "All Channel Stereo": "multich",
    "Dolby Mode": "dolby mode",
    "Native": "native",
    "Dolby Surround": "dolby surround",
}

# Reverse mapping to display friendly names from the raw API state
API_TO_UI_MAPPING = {v: k for k, v in AUDIO_MODE_MAPPING.items()}

class Apr16AudioModeSelect(SelectEntity):
    """
    Select entity for changing audio listening/upmixing modes.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"select.{device_config.identifier}.audio_mode",
            f"{device_config.name} Audio Mode",
            {
                Attributes.STATE: States.ON,
                Attributes.OPTIONS: list(AUDIO_MODE_MAPPING.keys()),
                Attributes.CURRENT_OPTION: "Stereo",
            },
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Synchronize entity state with the device."""
        try:
            raw_mode = await self._device.get_audio_mode()
            display_option = API_TO_UI_MAPPING.get(raw_mode, "Stereo")
            self.update({
                Attributes.STATE: States.ON,
                Attributes.CURRENT_OPTION: display_option,
            })
        except Exception as err:
            _LOG.debug("[%s] Failed to sync audio mode: %s", self._device.log_id, err)
            self.update({Attributes.STATE: States.UNAVAILABLE})

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle command callbacks from the remote UI."""
        if cmd_id != Commands.SELECT_OPTION:
            return StatusCodes.NOT_IMPLEMENTED
        
        option = params.get("option") if params else None
        if not option or option not in AUDIO_MODE_MAPPING:
            return StatusCodes.BAD_REQUEST

        api_mode = AUDIO_MODE_MAPPING[option]
        _LOG.debug("[%s] Selecting audio mode: %s (API: %s)", self._device.log_id, option, api_mode)
        
        try:
            await self._device.set_audio_mode(api_mode)
            self.update({
                Attributes.STATE: States.ON,
                Attributes.CURRENT_OPTION: option,
            })
            await self.push_update()
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Failed to set audio mode: %s", self._device.log_id, err)
            return StatusCodes.SERVER_ERROR