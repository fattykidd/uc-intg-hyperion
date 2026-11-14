"""
Switch entity definition for master Dirac filtering on the AudioControl Hyperion APR-16.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.switch import Attributes, States
from ucapi_framework import SwitchEntity
from device import Apr16

_LOG = logging.getLogger(__name__)

class Apr16DiracFilteringSwitch(SwitchEntity):
    """
    Switch entity to toggle master Dirac Live filtering on/off.

    Its state comes from the device (GetDiracFiltering), which the poll loop keeps current.
    """

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"switch.{device_config.identifier}.dirac_filtering",
            f"{device_config.name} Dirac Filtering",
            features=[],
            attributes={
                Attributes.STATE: States.UNKNOWN,
            },
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def sync_state(self) -> None:
        """Show the device's Dirac filtering state, or unavailable while disconnected."""
        filtering = self._device.dirac_filtering
        if not self._device.is_connected:
            state = States.UNAVAILABLE
        elif filtering is None:
            state = States.UNKNOWN
        else:
            state = States.ON if filtering else States.OFF
        self.update({Attributes.STATE: state})

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle command callbacks from the remote UI for master Dirac filtering toggle."""
        if cmd_id not in ("on", "off", "toggle"):
            return StatusCodes.NOT_IMPLEMENTED

        target_state = True
        if cmd_id == "off":
            target_state = False
        elif cmd_id == "toggle":
            current_state = self._device.dirac_filtering is True
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

            self.update({Attributes.STATE: States.ON if target_state else States.OFF})
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Failed to set Dirac filtering switch: %s", self._device.log_id, err)
            return StatusCodes.SERVER_ERROR