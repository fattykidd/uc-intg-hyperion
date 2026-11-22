"""
Switch entities for the AudioControl Hyperion APR-16: master Dirac filtering and loudness.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.switch import Attributes, States
from ucapi_framework import SwitchEntity

from device import Apr16

_LOG = logging.getLogger(__name__)


class Apr16Switch(SwitchEntity):
    """
    A switch showing one on/off setting of the device.

    The state comes from the device, which keeps it current. Subclasses say which setting
    they show (``_is_on``) and how to change it (``_set``).
    """

    suffix: str
    label: str

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"switch.{device_config.identifier}.{self.suffix}",
            f"{device_config.name} {self.label}",
            features=[],
            attributes={
                Attributes.STATE: States.UNKNOWN,
            },
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    def _is_on(self) -> bool | None:
        """Whether the setting is on, or None if the device hasn't reported it yet."""
        raise NotImplementedError

    async def _set(self, enabled: bool) -> bool:
        """Change the setting on the device. Returns False if the device didn't accept it."""
        raise NotImplementedError

    def _is_available(self) -> bool:
        """Whether the device offers the setting. Defaults to True."""
        return True

    async def sync_state(self) -> None:
        """Show the device's state, or unavailable while disconnected."""
        setting = self._is_on()
        if not self._device.is_connected or not self._is_available():
            state = States.UNAVAILABLE
        elif setting is None:
            state = States.UNKNOWN
        else:
            state = States.ON if setting else States.OFF
        self.update({Attributes.STATE: state})

    async def _handle_command(
        self, entity: Any, cmd_id: str, params: dict[str, Any] | None
    ) -> StatusCodes:
        """Handle on, off and toggle from the Remote."""
        if cmd_id not in ("on", "off", "toggle"):
            return StatusCodes.NOT_IMPLEMENTED

        target_state = cmd_id == "on" or (cmd_id == "toggle" and self._is_on() is not True)

        _LOG.debug("[%s] Executing %s switch command %s -> target: %s", self._device.log_id, self.label, cmd_id, target_state)

        try:
            if not await self._set(target_state):
                return StatusCodes.SERVER_ERROR

            self.update({Attributes.STATE: States.ON if target_state else States.OFF})
            return StatusCodes.OK
        except Exception as err:
            _LOG.error("[%s] Failed to set %s switch: %s", self._device.log_id, self.label, err)
            return StatusCodes.SERVER_ERROR


class Apr16DiracFilteringSwitch(Apr16Switch):
    """Toggles master Dirac Live filtering on and off."""

    suffix = "dirac_filtering"
    label = "Dirac Filtering"

    def _is_on(self) -> bool | None:
        return self._device.dirac_filtering

    async def _set(self, enabled: bool) -> bool:
        return await self._device.async_set_dirac_filtering(enabled)


class Apr16LoudnessSwitch(Apr16Switch):
    """
    Toggles loudness compensation, which adds bass at low listening levels.

    The device reports its state only over its live streams, so the switch reads "unknown" on firmware
    that has none until it has been switched once from here.
    """

    suffix = "loudness"
    label = "Loudness"

    def _is_on(self) -> bool | None:
        return self._device.loudness

    def _is_available(self) -> bool:
        return self._device.loudness_supported is not False

    async def _set(self, enabled: bool) -> bool:
        return await self._device.async_set_loudness(enabled)
