"""
Select entity definitions for audio modes on the AudioControl Hyperion APR-16.
"""

import logging
from typing import Any

from ucapi import select
from device import Apr16

_LOG = logging.getLogger(__name__)


class Apr16AudioModeSelect(select.Select):
    """
    Select entity for changing audio listening/upmixing modes.
    """

    def __init__(self, device: Apr16):
        super().__init__(
            identifier=f"{device.identifier}_audio_mode",
            name=f"{device.name} Audio Mode",
            options=["Stereo", "All Channel Stereo", "Dolby Surround", "DTS Neural:X", "Dolby Mode", "Native"],
        )
        self._device = device
        self.state = "Stereo"

    async def async_select_option(self, option: str) -> None:
        """Handle option selection from the remote UI."""
        _LOG.debug("[%s] Selecting audio mode: %s", self.identifier, option)
        
        # Call the actual device method from your device.py module
        await self._device.set_audio_mode(option)
        
        self.state = option
        await self.push_update()