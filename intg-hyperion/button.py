"""
Button entities for the AudioControl Hyperion APR-16 integration.

Each button only says what it is called and what pressing it does; Apr16Button handles the rest.
"""

from __future__ import annotations

import logging
from typing import Any

from ucapi import StatusCodes
from ucapi.button import Commands
from ucapi_framework import ButtonEntity

from device import Apr16

_LOG = logging.getLogger(__name__)


class Apr16Button(ButtonEntity):
    """
    Base class for APR-16 push buttons.

    Subclasses set ``suffix`` and ``label`` (together they give the entity its id and name)
    and implement ``press()``.
    """

    suffix: str
    """Last part of the entity id, e.g. "reboot" gives "button.<device>.reboot"."""

    label: str
    """Name shown on the remote, after the device name."""

    def __init__(self, device_config, device: Apr16) -> None:
        super().__init__(
            f"button.{device_config.identifier}.{self.suffix}",
            f"{device_config.name} {self.label}",
            cmd_handler=self._handle_command,
        )
        self._device = device
        self._device_config = device_config

    async def press(self) -> None:
        """Do what this button does."""
        raise NotImplementedError

    async def _handle_command(self, entity: Any, cmd_id: str, params: dict[str, Any] | None) -> StatusCodes:
        if cmd_id != Commands.PUSH:
            return StatusCodes.NOT_IMPLEMENTED

        try:
            await self.press()
        except Exception as err:
            _LOG.error("[%s] %s failed: %s", self.id, self.label, err)
            return StatusCodes.SERVER_ERROR
        return StatusCodes.OK


# --- System -----------------------------------------------------------------


class Apr16RebootButton(Apr16Button):
    """Restart the processor."""

    suffix = "reboot"
    label = "Reboot"

    async def press(self) -> None:
        await self._device.reboot()


class Apr16HpdButton(Apr16Button):
    """Trigger an HDMI hotplug detect pulse, which clears most HDMI handshake lockups."""

    suffix = "hpd"
    label = "Trigger HPD"

    async def press(self) -> None:
        await self._device.trigger_hpd()


# --- Tone (active input) ----------------------------------------------------


class Apr16InputBassUpButton(Apr16Button):
    """Raise the active input's bass by 1 dB."""

    suffix = "bass_up"
    label = "Bass +1dB"

    async def press(self) -> None:
        await self._device.step_input_tone("bass", +1)


class Apr16InputBassDownButton(Apr16Button):
    """Lower the active input's bass by 1 dB."""

    suffix = "bass_down"
    label = "Bass -1dB"

    async def press(self) -> None:
        await self._device.step_input_tone("bass", -1)


class Apr16InputTrebleUpButton(Apr16Button):
    """Raise the active input's treble by 1 dB."""

    suffix = "treble_up"
    label = "Treble +1dB"

    async def press(self) -> None:
        await self._device.step_input_tone("treble", +1)


class Apr16InputTrebleDownButton(Apr16Button):
    """Lower the active input's treble by 1 dB."""

    suffix = "treble_down"
    label = "Treble -1dB"

    async def press(self) -> None:
        await self._device.step_input_tone("treble", -1)


# --- Front panel display ----------------------------------------------------


class Apr16DisplayBrightnessUpButton(Apr16Button):
    """Raise the front panel display brightness by 10%."""

    suffix = "brightness_up"
    label = "Brightness +10%"

    async def press(self) -> None:
        await self._device.step_display_brightness(+10)


class Apr16DisplayBrightnessDownButton(Apr16Button):
    """Lower the front panel display brightness by 10%."""

    suffix = "brightness_down"
    label = "Brightness -10%"

    async def press(self) -> None:
        await self._device.step_display_brightness(-10)
