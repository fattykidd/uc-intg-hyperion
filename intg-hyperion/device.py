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

from dataclasses import dataclass
from config import APR16Config
from ucapi import media_player
from ucapi_framework import (
    BaseConfigManager,
    StatelessHTTPDevice,
    BaseIntegrationDriver,
)
from ucapi_framework.helpers import MediaPlayerAttributes

_LOG = logging.getLogger(__name__)

# --- Volume Mapping Lookup Table ---
LOWER_VOLUME_MAP = {
    0: -127.5,
    1: -121.5,
    2: -115.0,
    3: -108.5,
    4: -102.5,
    5: -96.0,
    6: -89.5,
    7: -83.5,
    8: -77.0,
    9: -70.5,
    10: -64.0,
    11: -63.5,
    12: -63.0,
    13: -62.0,
    14: -61.5,
    15: -60.5,
    16: -60.0,
    17: -59.0,
    18: -58.0,
    19: -57.5,
}


class Apr16(StatelessHTTPDevice):
    """
    Device class representing your physical device.

    This class handles all communication with the device and maintains
    its current state. Extend this class with methods specific to your device.
    """

    def __init__(
        self,
        device_config: APR16Config,
        loop: AbstractEventLoop | None,
        config_manager: BaseConfigManager | None = None,
        driver: BaseIntegrationDriver | None = None,
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
        self._base_url = f"http://{device_config.address}:{device_config.port}"

        # State dicts keyed by device_id (identifier), not entity_id.
        # Seed with defaults so accessors always return a valid object.
        self._media_player_attributes: dict[str, MediaPlayerAttributes] = {
            device_config.identifier: MediaPlayerAttributes(
                STATE=media_player.States.OFF,
                VOLUME=0,
                MUTED=False,
                SOURCE=None,
                SOURCE_LIST=[
                    "HDMI 1",
                    "HDMI 2",
                    "HDMI 3",
                    "HDMI 4",
                    "HDMI 5",
                    "HDMI 6",
                    "HDMI 7",                    
                    "Digital 1",
                    "Digital 2",
                    "Digital 3",
                    "Digital 4",
                    "Analog 1",
                    "Analog 2",
                    "Analog 3",
                    "Dante",
                    "eArc",
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
    def source(self) -> str:
        """Return the current input source."""
        attrs = self._media_player_attributes.get(self.identifier)
        return attrs.SOURCE if attrs else ""

    @property
    def source_list(self) -> list[str]:
        """Return the list of available input sources."""
        attrs = self._media_player_attributes.get(self.identifier)
        return attrs.SOURCE_LIST if attrs else []

    @property
    def log_id(self) -> str:
        """Return a log identifier for debugging."""
        return self.name if self.name else self.identifier
    def get_media_player_attributes(
        self, device_id: str
    ) -> MediaPlayerAttributes | None:
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
            "[%s] Verifying connection to device at %s",
            self.log_id,
            self.address,
        )

        try:
            async with aiohttp.ClientSession() as session:
                # Fetch Power
                async with session.get(f"{self._base_url}/v1/power") as resp:
                    resp.raise_for_status()
                    data = await resp.json()
                    power_state = str(data.get("state", "0"))
                    is_on = power_state == "1"

                # Fetch Volume
                async with session.get(f"{self._base_url}/v1/vol") as resp:
                    resp.raise_for_status()
                    vol_data = await resp.json()
                    current_vol = int(round(float(vol_data.get("level", 0))))

                # Fetch Mute
                async with session.get(f"{self._base_url}/v1/mute") as resp:
                    resp.raise_for_status()
                    mute_data = await resp.json()
                    current_mute = bool(mute_data.get("state", False))

                # Fetch Active Input
                async with session.get(
                    f"{self._base_url}/api/atlas/input/active"
                ) as resp:
                    resp.raise_for_status()
                    input_data = await resp.json()
                    current_source = str(
                        input_data.get("source", input_data.get("input", ""))
                    )

                # Fetch Audio Format/Details (Non-blocking diagnostic logging)
                try:
                    async with session.get(
                        f"{self._base_url}/v1/audioformat"
                    ) as aud_resp:
                        if aud_resp.status == 200:
                            aud_data = await aud_resp.json()
                            _LOG.debug(
                                "[%s] Active Audio Codec: %s",
                                self.log_id,
                                aud_data.get("format"),
                            )
                except Exception as aud_err:
                    _LOG.debug(
                        "[%s] Could not fetch audio format during verification: %s",
                        self.log_id,
                        aud_err,
                    )

                # Fetch Video Details (Non-blocking diagnostic logging)
                try:
                    async with session.get(
                        f"{self._base_url}/v1/videodetail"
                    ) as vid_resp:
                        if vid_resp.status == 200:
                            vid_data = await vid_resp.json()
                            _LOG.debug(
                                "[%s] Active Video: %s @ %s, HDR: %s",
                                self.log_id,
                                vid_data.get("resolution", "Unknown"),
                                vid_data.get("framerate", "Unknown"),
                                vid_data.get("hdr", "No HDR"),
                            )
                except Exception as vid_err:
                    _LOG.debug(
                        "[%s] Could not fetch video detail during verification: %s",
                        self.log_id,
                        vid_err,
                    )

            # Update attributes
            if self.identifier in self._media_player_attributes:
                attrs = self._media_player_attributes[self.identifier]
                attrs.STATE = (
                    media_player.States.ON
                    if is_on
                    else media_player.States.OFF
                )
                attrs.VOLUME = current_vol
                attrs.MUTED = current_mute
                attrs.SOURCE = current_source

            _LOG.debug(
                "[%s] Connection verified. State: %s, Vol: %s, Mute: %s",
                self.log_id,
                self.state,
                current_vol,
                current_mute,
            )

        except Exception as err:
            _LOG.error(
                "[%s] Connection verification failed: %s", self.log_id, err
            )
            raise

    # =========================================================================
    # System & Power Operations
    # =========================================================================

    async def get_version(self) -> dict[str, Any]:
        """Fetch firmware version and build metadata via GET /v1/version."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/version") as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_mac_address(self) -> str:
        """Fetch hardware MAC address via GET /v1/mac."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/mac") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data.get("mac", "00:00:00:00:00:00")
    
    async def get_system_power(self) -> str:
        """
        Get system power state from GET /v1/power.
        Returns current power state ('1' for on, '0' for standby).
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/power") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return str(data.get("state", "0"))

    async def reboot(self) -> None:
        """
        Initiate a controlled system restart via POST /v1/reboot (~30-45s).
        """
        _LOG.warning("[%s] Initiating system reboot...", self.log_id)
        async with aiohttp.ClientSession() as session:
            # Added json={} to match the API reference body specification[cite: 1]
            async with session.post(f"{self._base_url}/v1/reboot", json={}) as resp:
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
            async with session.post(
                f"{self._base_url}/v1/power", json={"state": "1"}
            ) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].STATE = (
                media_player.States.ON
            )
        self.push_update()

    async def power_off(self) -> None:
        """Turn off the device."""
        _LOG.debug("[%s] Powering off", self.log_id)

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/power", json={"state": "0"}
            ) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].STATE = (
                media_player.States.OFF
            )
        self.push_update()

    async def power_toggle(self) -> None:
        """Toggle the device power state."""
        _LOG.debug("[%s] Toggling power", self.log_id)

        if self.state == media_player.States.ON:
            await self.power_off()
        else:
            await self.power_on()

    async def get_host_ip(self) -> str:
        """Get system host IP address via GET /v1/hostip[cite: 1]."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/hostip") as resp:
                resp.raise_for_status()
                try:
                    data = await resp.json()
                    return data.get("ip", data.get("hostip", ""))
                except Exception:
                    text = await resp.text()
                    return text.strip()       

    async def trigger_hpd(self, state: bool = True) -> bool:
        """Trigger HDMI hotplug detection via POST /v1/hdmi/output/hpd."""
        _LOG.debug("[%s] Triggering HDMI HPD with state: %s", self.log_id, state)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/hdmi/output/hpd", json={"state": state}
            ) as resp:
                resp.raise_for_status()
                return True

    async def get_display_brightness(self) -> int:
        """Get front panel LCD display brightness via GET /v1/displaybrightness[cite: 1]."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/displaybrightness") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return int(data.get("brightness", 0))

    async def set_display_brightness(self, brightness: int) -> bool:
        """Set front panel LCD display brightness via POST /v1/displaybrightness[cite: 1]."""
        _LOG.debug("[%s] Setting display brightness to: %s", self.log_id, brightness)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/displaybrightness", json={"brightness": brightness}
            ) as resp:
                resp.raise_for_status()
                return True
            
    # =========================================================================
    # Volume, Mute & Limits Operations
    # =========================================================================

    def percentage_to_db(self, percent: float) -> float:
        """Convert absolute volume percentage (0-100) to Hyperion dB scale."""
        p_clamped = max(0.0, min(100.0, percent))
        
        # 0% to 19%: Use the explicit lower lookup table
        if p_clamped < 20:
            floor_p = int(p_clamped)
            return LOWER_VOLUME_MAP.get(floor_p, -127.5)
            
        # 100%: Exactly 0 dB
        if p_clamped >= 100.0:
            return 0.0
            
        # 20% to 95%: Clean linear slope (-57.0 dB at 20% up to -4.0 dB at 95%)
        if p_clamped <= 95.0:
            return -57.0 + ((p_clamped - 20.0) / 75.0) * 53.0
            
        # 95% to 100%: Final hop from -4.0 dB to 0.0 dB
        return -4.0 + ((p_clamped - 95.0) / 5.0) * 4.0

    def db_to_percent(self, db: float) -> float:
        """Convert Hyperion dB scale back to absolute percentage (0-100)."""
        db_clamped = max(-127.5, min(0.0, db))
        
        if db_clamped >= 0.0:
            return 100.0
        if db_clamped <= -127.5:
            return 0.0
            
        if db_clamped >= -57.0:
            if db_clamped >= -4.0:
                return 95.0 + ((db_clamped - (-4.0)) / 4.0) * 5.0
            else:
                return 20.0 + ((db_clamped - (-57.0)) / 53.0) * 75.0
                
        closest_p = 0
        min_diff = float("inf")
        for p, val in LOWER_VOLUME_MAP.items():
            diff = abs(val - db_clamped)
            if diff < min_diff:
                min_diff = diff
                closest_p = p
                
        return float(closest_p)
    
    async def get_volume(self) -> float:
        """Get master volume level via GET /v1/vol."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/vol") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return float(data.get("level", 0.0))

    async def set_volume(self, volume: float) -> None:
        """Set master volume level via POST /v1/vol."""
        _LOG.debug("[%s] Setting master volume to: %s", self.log_id, volume)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/vol", json={"level": volume}
            ) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].VOLUME = int(round(volume))  # <-- Cast to int
        self.push_update()

    async def get_mute(self) -> bool:
        """Get master mute status via GET /v1/mute."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/mute") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return bool(data.get("state", False))

    async def set_mute(self, muted: bool) -> None:
        """Set master mute status via POST /v1/mute."""
        _LOG.debug("[%s] Setting mute to: %s", self.log_id, muted)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/mute", json={"state": muted}
            ) as resp:
                resp.raise_for_status()

        if self.identifier in self._media_player_attributes:
            self._media_player_attributes[self.identifier].MUTED = muted
        self.push_update()

    async def get_max_volume(self) -> float:
        """Get maximum volume limit via GET /v1/maxvol."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/maxvol") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return float(data.get("level", 100.0))

    async def set_max_volume(self, max_vol: float) -> None:
        """Set maximum volume limit via POST /v1/maxvol."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/maxvol", json={"level": max_vol}
            ) as resp:
                resp.raise_for_status()

    async def get_power_on_volume(self) -> float:
        """Get default startup volume level via GET /v1/onvol."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/onvol") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return float(data.get("level", 0.0))

    async def set_power_on_volume(self, on_vol: float) -> None:
        """Set default startup volume level via POST /v1/onvol."""
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/onvol", json={"level": on_vol}
            ) as resp:
                resp.raise_for_status()

    # =========================================================================
    # Input Management & Active Source
    # =========================================================================

    async def get_active_input(self) -> str:
        """Get the active audio/video input source via GET /api/atlas/input/active."""
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self._base_url}/api/atlas/input/active"
            ) as resp:
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
                json={"input": source},
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

    async def get_input_bass(self, input_name: str) -> int:
        """Get input bass level via GET /api/atlas/input/{input}/bass."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/api/atlas/input/{input_name}/bass") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return int(data.get("level", 0))

    async def set_input_bass(self, input_name: str, bass: int) -> bool:
        """Set input bass level via POST /api/atlas/input/{input}/bass/{level}."""
        _LOG.debug(
            "[%s] Setting input bass for %s to: %s", self.log_id, input_name, bass
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/api/atlas/input/{input_name}/bass/{bass}",
                json={"inputId": 0}
            ) as resp:
                resp.raise_for_status()
                return True

    async def get_input_treble(self, input_name: str) -> int:
        """Get input treble level via GET /api/atlas/input/{input}/treb."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/api/atlas/input/{input_name}/treb") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return int(data.get("level", 0))

    async def set_input_treble(self, input_name: str, treble: int) -> bool:
        """Set input treble level via POST /api/atlas/input/{input}/treb/{level}."""
        _LOG.debug(
            "[%s] Setting input treble for %s to: %s", self.log_id, input_name, treble
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/api/atlas/input/{input_name}/treb/{treble}",
                json={"inputId": 0}
            ) as resp:
                resp.raise_for_status()
                return True                  

    async def get_audio_mode(self) -> str:
        """Get current audio processing mode (Stereo, Surround, etc.) via GET /v1/audiomode."""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self._base_url}/v1/audiomode") as resp:
                resp.raise_for_status()
                data = await resp.json()
                return str(data.get("mode", data.get("audiomode", "")))

    async def set_audio_mode(self, mode: str) -> None:
        """Configure audio processing mode via POST /v1/audiomode."""
        _LOG.debug(
            "[%s] Setting audio processing mode to: %s", self.log_id, mode
        )
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self._base_url}/v1/audiomode", json={"mode": mode}
            ) as resp:
                resp.raise_for_status()

    # =========================================================================
    # Command Sending
    # =========================================================================

    async def send_command(self, command: str, **kwargs: Any) -> None:
        """
        Send a command to the device.
        """
        _LOG.debug(
            "[%s] Sending command: %s with kwargs: %s",
            self.log_id,
            command,
            kwargs,
        )

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
