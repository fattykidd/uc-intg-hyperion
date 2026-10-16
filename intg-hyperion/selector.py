"""
Select entity definition for audio modes on the AudioControl Hyperion APR-16.
"""

import logging
from typing import Any

from ucapi import StatusCodes
from device import Apr16
from ucapi_framework.entities import SelectEntity

_LOG = logging.getLogger(__name__)


class Apr16AudioModeSelect(SelectEntity):
    """
    Select entity for changing audio listening/upmixing modes.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            identifier=f"select.{device_config.identifier}_audio_mode",
            name=f"{device_config.name} Audio Mode",
            options=[
                "Stereo",
                "All Channel Stereo",
                "Dolby Surround",
                "DTS Neural:X",
                "Dolby Mode",
                "Native",
            ],
        )
        self._device = device
        self._device_config = device_config
        self.state = "Stereo"

    async def async_select_option(self, option: str) -> None:
        """Handle option selection from the remote UI."""
        _LOG.debug("[%s] Selecting audio mode: %s", self.identifier, option)

        # Call the actual device method from your device.py module
        await self._device.set_audio_mode(option)

        self.state = option
        await self.push_update()