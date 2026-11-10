"""
Switch entity definition for master Dirac filtering on the AudioControl Hyperion APR-16.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.switch import Attributes, Commands, States
from ucapi_framework import SwitchEntity
from device import Apr16

_LOG = logging.getLogger(__name__)

class Apr16DiracFilteringSwitch(SwitchEntity):
    """
    Switch entity to toggle master Dirac Live filtering on/off.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"switch.{device_config.identifier}.dirac_filtering",
            f"{device_config.name} Dirac Filtering",
            attributes={
            Attributes.STATE: States.ON,
        },
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Synchronize master Dirac filtering state with the device."""
        try:
            # Query device active slot or state status
            active_slot = await self._device.async_get_dirac_active_slot()
            # If active slot > 0, filtering is engaged
            is_enabled = active_slot > 0
            
            self.update({
                Attributes.STATE: States.ON if is_enabled else States.OFF,
            })
            await self.push_update()
        except Exception as err:
            _LOG.debug("[%s] Failed to sync Dirac filtering switch: %s", self._device.log_id, err)
            self.update({Attributes.STATE: States.UNAVAILABLE})
            await self.push_update()

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle command callbacks from the remote UI for master Dirac filtering toggle."""
        if cmd_id not in (Commands.TURN_ON, Commands.TURN_OFF, Commands.TOGGLE):
            return StatusCodes.NOT_IMPLEMENTED

        target_state = True
        if cmd_id == Commands.TURN_OFF:
            target_state = False
        elif cmd_id == Commands.TOGGLE:
            current_state = self.get_attribute(Attributes.STATE) == States.ON
            target_state = not current_state

        _LOG.debug(
            "[%s] Executing Dirac filtering switch command %s -> target: %s",
            self._device.log_id,
            cmd_id,
            target_state,
        )

        try:
            success = await self._device.async_set_dirac_filtering(target_state)
            if not success:
                return StatusCodes.SERVER_ERROR

            self.update({
                Attributes.STATE: States.ON if target_state else States.OFF,
            })
            await self.push_update()
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Failed to set Dirac filtering switch: %s", self._device.log_id, err)
            return StatusCodes.SERVER_ERROR