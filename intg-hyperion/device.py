"""
Device Communication Module.

This module handles all communication with your device. It manages connections,
sends commands, and tracks device state.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from asyncio import AbstractEventLoop
from typing import Any
import aiohttp

from config import Apr16Config
from ucapi import media_player
from ucapi_framework import (
    BaseConfigManager,
    StatelessHTTPDevice,
)
from ucapi_framework.helpers import MediaPlayerAttributes

_LOG = logging.getLogger(__name__)


class Apr16(StatelessHTTPDevice):
    """
    Device class representing your physical device.

    This class handles all communication with the device and maintains
    its current state. Extend this class with methods specific to your device.
    """

    def __init__(
        self,
        device_config: Apr16Config,
        loop: AbstractEventLoop | None,
        config_manager: BaseConfigManager | None = None,
        driver=None,
    ) -> None:
        """
        Initialize the device.

        :param device_config: Configuration for this device
        :param loop: Event loop for async operations
        :param config_manager: Configuration manager instance
        """
        super().__init__(
            device_config=device_config,
            loop=loop,
            config_manager=config_manager,
            driver=driver,
        )

        # Store the base URL for direct HTTP communication
        self._base_url = f"http://{device_config.address}"

        # State dicts keyed by device_id (identifier), not entity_id.
        # Seed with defaults so accessors always return a valid object.
        self._media_player_attributes: dict[str, MediaPlayerAttributes] = {
            device_config.identifier: MediaPlayerAttributes(
                STATE=media_player.States.OFF,
                VOLUME=0.0,
                MUTED=False,
                SOURCE=None,
                SOURCE_LIST=[
                    "HDMI 1", "HDMI 2", "HDMI 3", "HDMI 4", "HDMI 5", "HDMI 6", "HDMI 7",
                    "Digital 1", "Digital 2", "Digital 3", "Digital 4",
                    "Analog 1", "Analog 2", "Analog 3", "Analog 4", "Analog 5"
                ],
            )
        }
    # =========================================================================
    # Properties
    # =========================================================================

    @property
    def identifier(self) -> str:
        """Return the device identifier."""
        return self._device_config.identifier

    @property
    def name(self) -> str:
        """Return the device name."""
        return self._device_config.name

    @property
    def address(self) -> str | None:
        """Return the device address."""
        return self._device_config.address

    @property
    def state(self) -> media_player.States | None:
        """Return the current power state."""
        attrs = self._media_player_attributes.get(self.identifier)
        return attrs.STATE if attrs else None

    @property
    def log_id(self) -> str:
        """Return a log identifier for debugging."""
        return self.name if self.name else self.identifier

    def get_media_player_attributes(self, device_id: str) -> MediaPlayerAttributes | None:
        """
        Return media player attributes for the given device_id.

        Called by the entity's sync_state() after push_update() fires.

        :param device_id: Device identifier (DeviceConfig.identifier)
        :return: Current MediaPlayerAttributes, or None if unknown
        """
        return self._media_player_attributes.get(device_id)

    # =========================================================================
    # Connection Management
    # =========================================================================
    async def verify_connection(self) -> None:
        """
        Verify connection to the device and emit current state.
        """
        _LOG.debug(
            "[%s] Verifying connection to device at %s", self.log_id, self.address
        )

        try:
            async with aiohttp.ClientSession() as session:
                # Fetch Power
                async with session.get(f"{self._base_url}/v1/power") as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    power_state = data.get("state", "STANDBY")
                    is_on = (power_state.upper() == "ON")

                # Fetch Volume
                async with session.get(f"{self._base_url}/v1/vol") as resp:
                    resp.raise_for_status()
                    vol_data = await resp.json()
                    current_vol = float(vol_data.get("master", 0.0))

                # Fetch Mute
                async with session.get(f"{self._base_url}/v1/mute") as resp:
                    resp.raise_for_status()
                    mute_data = await resp.json()
                    current_mute = bool(mute_data.get("mute", False))

                # Fetch Active Input
                async with session.get(f"{self._base_url}/api/atlas/input/active") as resp:
                    resp.raise_for_status()
                    input_data = await resp.json()
                    current_source = str(input_data.get("source", input_data.get("input", "")))

                # Fetch Audio Format/Details (Non-blocking diagnostic logging)
                try:
                    async with session.get(f"{self._base_url}/v1/audioformat") as aud_resp:
                        if aud_resp.status == 200:
                            aud_data = await aud_resp.json()
                            _LOG.debug("[%s] Active Audio Codec: %s", self.log_id, aud_data.get("format"))
                except Exception as aud_err:
                    _LOG.debug("[%s] Could not fetch audio format during verification: %s", self.log_id, aud_err)
                
                # Fetch Video Details (Non-blocking diagnostic logging)
                try:
                    async with session.get(f"{self._base_url}/v1/videodetail") as vid_resp:
                        if vid_resp.status == 200:
                            vid_data = await vid_resp.json()
                            _LOG.debug(
                                "[%s] Active Video: %s @ %s, HDR: %s", 
                                self.log_id, 
                                vid_data.get("resolution", "Unknown"), 
                                vid_data.get("framerate", "Unknown"),
                                vid_data.get("hdr", "No HDR")
                            )
                except Exception as vid_err:
                    _LOG.debug("[%s] Could not fetch video detail during verification: %s", self.log_id, vid_err)

            # Update attributes
            if self.identifier in self._media_player_attributes:
                attrs = self._media_player_attributes[self.identifier]
                attrs.STATE = media_player.States.ON if is_on else media_player.States.OFF
                attrs.VOLUME = current_vol
                attrs.MUTED = current_mute
                attrs.SOURCE = current_source

            _LOG.debug(
                "[%s] Connection verified. State: %s, Vol: %s, Mute: %s", 
                self.log_id, self.state, current_vol, current_mute
            )

        except Exception as err:
            _LOG.error("[%s] Connection verification failed: %s", self.log_id, err)
            raise

    # =========================================================================
    # System & Power Operations
    # =========================================================================

    async def get_system_power(self) -> str:
        """
        Get system power state from GET /v1/power.
        Returns current power state (e.g., 'ON', 'STANDBY').
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/power") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("state", "STANDBY")

    async def reboot(self) -> None:
        """
        Initiate a controlled system restart via POST /v1/reboot (~30-45s).
        """
        _LOG.warning("[%s] Initiating system reboot...", self.log_id)
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/v1/reboot") as resp:
                resp.raise_for_status()
        _LOG.info("[%s] Reboot command sent successfully.", self.log_id)

    async def get_system_status(self) -> dict[str, Any]:
        """
        Retrieve overall system status and version/build metadata via GET /v1/status.
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/status") as resp:
                resp.raise_for_status()
                return await resp.json()

    async def power_on(self) -> None:
        """Turn on the device."""
        _LOG.debug("[%s] Powering on", self.log_id)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/v1/power", json={"state": "ON"}) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].STATE = media_player.States.ON
        self.push_update()

    async def power_off(self) -> None:
        """Turn off the device."""
        _LOG.debug("[%s] Powering off", self.log_id)
        
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/v1/power", json={"state": "STANDBY"}) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].STATE = media_player.States.OFF
        self.push_update()

    async def power_toggle(self) -> None:
        """Toggle the device power state."""
        _LOG.debug("[%s] Toggling power", self.log_id)

        if self.state == media_player.States.ON:
            await self.power_off()
        else:
            await self.power_on()

    # =========================================================================
    # Volume, Mute & Limits Operations
    # =========================================================================

    async def get_volume(self) -> float:
        """Get master volume level (0-100) via GET /v1/vol."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/vol") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return float(data.get("master", data.get("volume", 0.0)))

    async def set_volume(self, volume: float) -> None:
        """Set master volume level (0-100) via POST /v1/vol."""
        _LOG.debug("[%s] Setting master volume to: %s", self.log_id, volume)
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/v1/vol", json={"master": volume}) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].VOLUME = volume
        self.push_update()

    async def get_mute(self) -> bool:
        """Get master mute status via GET /v1/mute."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/mute") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return bool(data.get("mute", data.get("muted", False)))

    async def set_mute(self, muted: bool) -> None:
        """Set master mute status via POST /v1/mute."""
        _LOG.debug("[%s] Setting mute to: %s", self.log_id, muted)
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/v1/mute", json={"mute": muted}) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].MUTED = muted
        self.push_update()

    async def get_max_volume(self) -> float:
        """Get maximum volume limit (0-100) via GET /v1/maxvol."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/maxvol") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return float(data.get("max", data.get("maxvol", 100.0)))

    async def set_max_volume(self, max_vol: float) -> None:
        """Set maximum volume limit (0-100) via POST /v1/maxvol."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/v1/maxvol", json={"max": max_vol}) as resp:
                resp.raise_for_status()

    async def get_power_on_volume(self) -> float:
        """Get default startup volume level via GET /v1/onvol."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/onvol") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return float(data.get("onvol", data.get("volume", 0.0)))

    async def set_power_on_volume(self, on_vol: float) -> None:
        """Set default startup volume level via POST /v1/onvol."""
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{self._base_url}/v1/onvol", json={"onvol": on_vol}) as resp:
                resp.raise_for_status()

    # =========================================================================
    # Input Management & Active Source
    # =========================================================================

    async def get_active_input(self) -> str:
        """Get the active audio/video input source via GET /api/atlas/input/active."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/api/atlas/input/active") as resp:
                resp.raise_for_status()
                data = await resp.json()
                # Adjust key based on exact API JSON response structure (e.g., 'source' or 'input')
                return str(data.get("source", data.get("input", "")))

    async def set_active_input(self, source: str) -> None:
        """Switch the active audio/video input source via POST /api/atlas/input/active."""
        _LOG.debug("[%s] Setting active input to: %s", self.log_id, source)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/api/atlas/input/active",
                json={"source": source}
            ) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].SOURCE = source
        self.push_update()

    async def get_video_detail(self) -> dict[str, Any]:
        """
        Get comprehensive video signal details (resolution, frame rate, 
        color space, HDR, and HDCP status) via GET /v1/videodetail.
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/videodetail") as resp:
                resp.raise_for_status()
                return await resp.json()

    # =========================================================================
    # Audio Status, Formats & Processing Modes
    # =========================================================================

    async def get_audio_detail(self) -> dict[str, Any]:
        """Get comprehensive audio signal details (format, rate, bit depth, channels) via GET /v1/audiodetail."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/audiodetail") as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_audio_format(self) -> str:
        """Get read-only codec detection (PCM, Dolby Atmos, DTS:X, etc.) via GET /v1/audioformat."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/audioformat") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return str(data.get("format", data.get("codec", "Unknown")))

    async def get_audio_bit_depth(self) -> int:
        """Get read-only detected bit depth (16, 24, 32 bit) via GET /v1/bit."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/bit") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return int(data.get("bit", data.get("bits", 0)))

    async def get_audio_sample_rate(self) -> int:
        """Get read-only sample rate in Hz (44100 to 192000) via GET /v1/sample."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/sample") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return int(data.get("sample", data.get("rate", 0)))

    async def get_audio_mode(self) -> str:
        """Get current audio processing mode (Stereo, Surround, etc.) via GET /v1/audiomode."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/audiomode") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return str(data.get("mode", data.get("audiomode", "")))

    async def set_audio_mode(self, mode: str) -> None:
        """Configure audio processing mode via POST /v1/audiomode."""
        _LOG.debug("[%s] Setting audio processing mode to: %s", self.log_id, mode)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/audiomode",
                json={"mode": mode}
            ) as resp:
                resp.raise_for_status()
    
    # =========================================================================
    # Command Sending
    # =========================================================================

    async def send_command(self, command: str, **kwargs: Any) -> None:
        """
        Send a command to the device.
        """
        _LOG.debug("[%s] Sending command: %s with kwargs: %s", self.log_id, command, kwargs)

        match command:
            case "reboot":
                await self.reboot()
            case "get_status":
                status = await self.get_system_status()
                _LOG.debug("[%s] System status: %s", self.log_id, status)
            case _:
                _LOG.warning("Unknown command: %s", command)

        # TODO: Implement command routing, update _media_player_attributes, then call push_update()
        # Example:
        # match command:
        #     case "volume_up":
        #         await self._client.volume_up()
        #         self._media_player_attributes[self.identifier].VOLUME += 5
        #         self.push_update()
        #     case "volume_down":
        #         await self._client.volume_down()
        #         self._media_player_attributes[self.identifier].VOLUME -= 5
        #         self.push_update()
        #     case _:
        #         _LOG.warning("Unknown command: %s", command)

