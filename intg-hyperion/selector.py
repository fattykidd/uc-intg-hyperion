"""
Select entity definitions for audio modes and dirac live filter slotson the AudioControl Hyperion APR-16.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.select import Attributes, Commands, States
from ucapi_framework import SelectEntity
from device import Apr16

_LOG = logging.getLogger(__name__)

# Map clean UI display names to the exact backend slot indices
DIRAC_SLOT_MAPPING = {
    "Slot 0 (Default/Bypass)": 0,
    "Slot 1": 1,
    "Slot 2": 2,
}

API_TO_UI_DIRAC = {v: k for k, v in DIRAC_SLOT_MAPPING.items()}

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
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Failed to set audio mode: %s", self._device.log_id, err)
            return StatusCodes.SERVER_ERROR

class Apr16DiracSlotSelect(SelectEntity):
    """
    Select entity for changing active Dirac Live filter slots.
    """
    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"select.{device_config.identifier}.dirac_slot",
            f"{device_config.name} Dirac Slot",
            {
                Attributes.STATE: States.ON,
                Attributes.OPTIONS: list(DIRAC_SLOT_MAPPING.keys()),
                Attributes.CURRENT_OPTION: "Slot 0 (Default/Bypass)",
            },
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Synchronize active Dirac slot state with the device via port 80 binary query."""
        try:
            raw_slot = await self._device.async_get_dirac_active_slot()
            display_option = API_TO_UI_DIRAC.get(raw_slot, "Slot 0 (Default/Bypass)")
            self.update({
                Attributes.STATE: States.ON,
                Attributes.CURRENT_OPTION: display_option,
            })
        except Exception as err:
            _LOG.debug("[%s] Failed to sync Dirac slot: %s", self._device.log_id, err)
            self.update({Attributes.STATE: States.UNAVAILABLE})

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle command callbacks for the Dirac slot selector."""
        params = params or {}
        options = ["Slot 0 (Default/Bypass)", "Slot 1", "Slot 2"]
        
        current_option = self.attributes.get(Attributes.CURRENT_OPTION) or options[0]
        target_option = current_option
        if cmd_id == "select_option":
            target_option = params.get("option", current_option)
        elif cmd_id == "select_first":
            target_option = options[0]
        elif cmd_id == "select_last":
            target_option = options[-1]
        elif cmd_id == "select_next":
            try:
                idx = options.index(current_option)
                target_option = options[(idx + 1) % len(options)]
            except ValueError:
                target_option = options[0]
        elif cmd_id == "select_prev":
            try:
                idx = options.index(current_option)
                target_option = options[(idx - 1) % len(options)]
            except ValueError:
                target_option = options[0]
        else:
            return StatusCodes.NOT_IMPLEMENTED

        # Get slot index directly from the mapping dictionary
        slot_idx = DIRAC_SLOT_MAPPING.get(target_option, 0)
        
        _LOG.debug(
            "[%s] Executing Dirac slot selector command %s -> target option: %s (slot %d)",
            self._device.log_id,
            cmd_id,
            target_option,
            slot_idx,
        )

        try:
            success = await self._device.async_set_dirac_filter_slot(slot_idx)
            if not success:
                return StatusCodes.SERVER_ERROR

            self.update({
                Attributes.CURRENT_OPTION: target_option,
            })
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Failed to set Dirac slot: %s", self._device.log_id, err)
            return StatusCodes.SERVER_ERROR