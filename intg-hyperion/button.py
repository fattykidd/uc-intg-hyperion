"""
Button entity definitions for the AudioControl Hyperion APR-16 integration.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.button import Commands
from ucapi_framework import ButtonEntity
from device import Apr16

_LOG = logging.getLogger(__name__)


class Apr16RebootButton(ButtonEntity):
    """Button entity to trigger a system reboot."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.reboot",
            f"{device_config.name} Reboot",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                await self._device.reboot()
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] Reboot command failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED


class Apr16HpdButton(ButtonEntity):
    """Button entity to trigger HDMI Hotplug Detection (HPD)."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.hpd",
            f"{device_config.name} Trigger HPD",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                await self._device.trigger_hpd()
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] HPD trigger failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED


class Apr16InputBassUpButton(ButtonEntity):
    """Button entity to increase active input bass by 1 dB."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.bass_up",
            f"{device_config.name} Bass +1dB",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                active_input = await self._device.get_active_input() or "HDMI 1"
                current = await self._device.get_input_bass(active_input)
                new_val = min(12, current + 1)
                await self._device.set_input_bass(active_input, new_val)
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] Bass up command failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED


class Apr16InputBassDownButton(ButtonEntity):
    """Button entity to decrease active input bass by 1 dB."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.bass_down",
            f"{device_config.name} Bass -1dB",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                active_input = await self._device.get_active_input() or "HDMI 1"
                current = await self._device.get_input_bass(active_input)
                new_val = max(-12, current - 1)
                await self._device.set_input_bass(active_input, new_val)
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] Bass down command failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED


class Apr16InputTrebleUpButton(ButtonEntity):
    """Button entity to increase active input treble by 1 dB."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.treble_up",
            f"{device_config.name} Treble +1dB",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                active_input = await self._device.get_active_input() or "HDMI 1"
                current = await self._device.get_input_treble(active_input)
                new_val = min(12, current + 1)
                await self._device.set_input_treble(active_input, new_val)
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] Treble up command failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED


class Apr16InputTrebleDownButton(ButtonEntity):
    """Button entity to decrease active input treble by 1 dB."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.treble_down",
            f"{device_config.name} Treble -1dB",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                active_input = await self._device.get_active_input() or "HDMI 1"
                current = await self._device.get_input_treble(active_input)
                new_val = max(-12, current - 1)
                await self._device.set_input_treble(active_input, new_val)
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] Treble down command failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED


class Apr16DisplayBrightnessUpButton(ButtonEntity):
    """Button entity to increase front panel display brightness by 10%."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.brightness_up",
            f"{device_config.name} Brightness +10%",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                current = await self._device.get_display_brightness()
                new_val = min(100, current + 10)
                await self._device.set_display_brightness(new_val)
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] Brightness up command failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED


class Apr16DisplayBrightnessDownButton(ButtonEntity):
    """Button entity to decrease front panel display brightness by 10%."""

    def __init__(self, device_config, device: Apr16):
        super().__init__(
            f"button.{device_config.identifier}.brightness_down",
            f"{device_config.name} Brightness -10%",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config
        self.subscribe_to_device(device)

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id == Commands.PRESS:
            try:
                current = await self._device.get_display_brightness()
                new_val = max(0, current - 10)
                await self._device.set_display_brightness(new_val)
                return StatusCodes.OK
            except Exception as err:
                _LOG.error("[%s] Brightness down command failed: %s", self.id, err)
                return StatusCodes.SERVER_ERROR
        return StatusCodes.NOT_IMPLEMENTED        