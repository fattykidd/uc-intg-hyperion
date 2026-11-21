"""
Device communication module for the AudioControl Hyperion APR-16.

Holds the device's state, exposes one method per thing the device can do, and
keeps the Unfolded Circle entities up to date. HTTP lives in client.py, the Dirac
protocol bytes in atlas.py and the volume scale in volume.py.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import asyncio
import json
import logging
from asyncio import AbstractEventLoop
from typing import Any, NamedTuple

import aiohttp
from ucapi import media_player
from ucapi_framework import (
    BaseConfigManager,
    BaseIntegrationDriver,
    StatelessHTTPDevice,
)
from ucapi_framework.helpers import MediaPlayerAttributes

import atlas
from client import HyperionClient
from config import APR16Config
from const import (
    AUDIO_MODE_MAPPING,
    BRIGHTNESS_MAX,
    BRIGHTNESS_MIN,
    DEFAULT_DIRAC_SLOTS,
    DEFAULT_INPUTS,
    FULL_REFRESH_INTERVAL,
    POLL_INTERVAL,
    TONE_MAX_DB,
    TONE_MIN_DB,
    VOLUME_MODE_RELATIVE,
    SimpleCommands,
)
from volume import percent_to_db, step_percent

_LOG = logging.getLogger(__name__)

INPUT_ACTIVE_PATH = "/api/atlas/input/active"


class AudioSignal(NamedTuple):
    """The incoming audio signal as the device last reported it (bit depth and rate are 0 with no signal)."""

    codec: str
    bit_depth: int
    sample_rate: int


class Apr16(StatelessHTTPDevice):
    """
    The AudioControl Hyperion APR-16 processor.

    Volume is tracked as an integer percent (``volume_pct``), which is what the device
    understands. The remote's on-screen display shows either that percent or its dB
    equivalent, depending on the configured volume mode.
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
        :param driver: The integration driver that owns this device
        """
        super().__init__(
            device_config=device_config,
            loop=loop,
            config_manager=config_manager,
            driver=driver,
        )

        self._api = HyperionClient(device_config.address, device_config.port)

        # Volume: percent is the source of truth, everything shown is derived from it.
        self._volume_mode: str = device_config.volume_mode
        self._volume_pct: int = 0
        self._vol_lock = asyncio.Lock()  # keeps volume POSTs in the order they were pressed
        self._vol_changes = 0  # counts local volume changes, so a stale poll result can be discarded

        self._dirac_filtering: bool | None = None  # None until the device has been read
        self._dirac_slot: int | None = None
        self._audio_signal: AudioSignal | None = None

        self._poll_task: asyncio.Task | None = None

        # Names fetched from the device after connecting.
        self._input_names_map: dict[int, str] = {}
        self._dirac_slot_names_map: dict[int, str] = dict(DEFAULT_DIRAC_SLOTS)

        # Entity state, keyed by device identifier (not entity id).
        self._media_player_attributes: dict[str, MediaPlayerAttributes] = {
            device_config.identifier: MediaPlayerAttributes(
                STATE=media_player.States.OFF,
                VOLUME=0,
                MUTED=False,
                SOURCE=None,
                SOURCE_LIST=list(DEFAULT_INPUTS),
                SOUND_MODE="",
                SOUND_MODE_LIST=list(AUDIO_MODE_MAPPING),
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
    def log_id(self) -> str:
        """Return a log identifier for debugging."""
        return self.name if self.name else self.identifier

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
        """Return the list of available input sources (custom names where the user set them)."""
        attrs = self._media_player_attributes.get(self.identifier)
        return attrs.SOURCE_LIST if attrs else []

    @property
    def dirac_slot_names(self) -> dict[int, str]:
        """Return Dirac slot index -> name. Placeholder names until the device has been read."""
        return self._dirac_slot_names_map

    @property
    def audio_signal(self) -> AudioSignal | None:
        """The incoming audio signal, or None if it hasn't been read from the device yet."""
        return self._audio_signal

    @property
    def dirac_slot(self) -> int | None:
        """The active Dirac slot (0-2), or None if it hasn't been read from the device yet."""
        return self._dirac_slot

    @property
    def dirac_filtering(self) -> bool | None:
        """Whether Dirac filtering is on, or None if it hasn't been read from the device yet."""
        return self._dirac_filtering

    @property
    def volume_pct(self) -> int:
        """Current volume as a percent (0-100), from the local cache."""
        return self._volume_pct

    @property
    def volume_db(self) -> float:
        """Current volume in dB, derived from the cached percent."""
        return percent_to_db(self._volume_pct)

    @property
    def volume_mode(self) -> str:
        """Volume style shown on the remote: 'absolute' (percent) or 'relative' (dB)."""
        return self._volume_mode

    @property
    def is_relative_volume(self) -> bool:
        """True when the remote should show dB instead of percent."""
        return self._volume_mode == VOLUME_MODE_RELATIVE

    def get_media_player_attributes(self, device_id: str) -> MediaPlayerAttributes | None:
        """
        Return media player attributes for the given device_id.

        Called by the entity's sync_state() after push_update() fires.
        """
        return self._media_player_attributes.get(device_id)

    # =========================================================================
    # Connection management
    # =========================================================================

    async def verify_connection(self) -> None:
        """Verify the connection to the device and load its current state."""
        _LOG.debug("[%s] Verifying connection to device at %s", self.log_id, self.address)

        try:
            await self.refresh_state()

            # Diagnostics only: log them, but never fail the connection over them.
            for label, fetch in (("audio format", self.get_audio_format), ("video", self.get_video_detail)):
                try:
                    _LOG.debug("[%s] Active %s: %s", self.log_id, label, await fetch())
                except Exception as err:
                    _LOG.debug("[%s] Could not fetch %s during verification: %s", self.log_id, label, err)

            _LOG.debug(
                "[%s] Connection verified. State: %s, Vol: %s%%, Mute: %s",
                self.log_id,
                self.state,
                self._volume_pct,
                self._media_player_attributes[self.identifier].MUTED,
            )
        except Exception as err:
            _LOG.error("[%s] Connection verification failed: %s", self.log_id, err)
            raise

        # Custom input names and Dirac slot names are nice to have, not required.
        await asyncio.gather(
            self.async_fetch_dynamic_inputs(),
            self.async_fetch_dirac_slot_names(),
            return_exceptions=True,
        )

    async def connect(self) -> bool:
        """
        Connect to the device, refresh every entity and start watching the device for changes.

        The framework only tells entities that manage their own state (all of ours) to sync when the
        device pushes an update, and StatelessHTTPDevice.connect() doesn't. So without this push,
        entities would keep showing "unavailable" after a reconnect until something else changed.
        """
        connected = await super().connect()
        if connected:
            self.push_update()
            self._start_polling()
        return connected

    async def disconnect(self) -> None:
        """Stop watching the device, disconnect and release the shared HTTP session."""
        await self._stop_polling()
        try:
            await super().disconnect()
        finally:
            await self._api.close()

    # =========================================================================
    # State refresh & polling
    # =========================================================================
    #
    # The device has no way to tell us about changes made on its front panel or web UI,
    # so the core state is re-read every few seconds. The remote is only updated when
    # something actually changed, plus a slower refresh for the sensors that have no
    # cached state (signal formats, tone, brightness and so on).

    async def refresh_state(self) -> bool:
        """
        Read power, volume, mute, input, audio mode, Dirac and the audio signal from the device into the cached attributes.

        Returns True if anything the media player shows has changed. Does not notify the remote.
        """
        attrs = self._media_player_attributes[self.identifier]
        before = (attrs.STATE, attrs.VOLUME, attrs.MUTED, attrs.SOURCE, attrs.SOUND_MODE, self._dirac_filtering, self._dirac_slot, self._audio_signal)
        changes_at_start = self._vol_changes

        is_on = await self.get_system_power() == "1"
        volume_pct = await self.get_volume()
        muted = await self.get_mute()
        source = await self.get_active_input_name()  # same naming as the source list, or the Remote cannot match it
        try:
            sound_mode = await self.get_audio_mode() or "Stereo"
        except Exception:
            sound_mode = attrs.SOUND_MODE or "Stereo"

        try:  # the current source was read before the names were known
            attrs.SOURCE = await self.get_active_input_name()
        except Exception as err:
            _LOG.debug("[%s] Could not refresh the current source name: %s", self.log_id, err)
        
        try:
            self._dirac_filtering = await self.async_get_dirac_filtering()
            self._dirac_slot = await self.async_get_dirac_active_slot()
        except Exception as err:  # Dirac is not essential: keep what we knew
            _LOG.debug("[%s] Could not read Dirac state: %s", self.log_id, err)

        await self._refresh_audio_signal()

        attrs.STATE = media_player.States.ON if is_on else media_player.States.OFF
        attrs.MUTED = muted
        attrs.SOURCE = source
        attrs.SOUND_MODE = sound_mode

        # A volume change made through the remote while we were reading is newer than what we read.
        if not self._vol_lock.locked() and self._vol_changes == changes_at_start:
            self._volume_pct = volume_pct
            attrs.VOLUME = self._osd_volume()

        return before != (
            attrs.STATE, attrs.VOLUME, attrs.MUTED, attrs.SOURCE, attrs.SOUND_MODE,
            self._dirac_filtering, self._dirac_slot, self._audio_signal,
        )

    async def _refresh_audio_signal(self) -> None:
        """Read codec, bit depth and sample rate. One that can't be read keeps its last value; the rest still update."""
        known = self._audio_signal or AudioSignal("Unknown", 0, 0)
        codec, bit_depth, sample_rate = await asyncio.gather(
            self.get_audio_format(),
            self.get_audio_bit_depth(),
            self.get_audio_sample_rate(),
            return_exceptions=True,
        )
        for name, value in (("format", codec), ("bit depth", bit_depth), ("sample rate", sample_rate)):
            if isinstance(value, BaseException):
                _LOG.debug("[%s] Could not read audio %s: %s", self.log_id, name, value)

        self._audio_signal = AudioSignal(
            codec=known.codec if isinstance(codec, BaseException) else codec,
            bit_depth=known.bit_depth if isinstance(bit_depth, BaseException) else bit_depth,
            sample_rate=known.sample_rate if isinstance(sample_rate, BaseException) else sample_rate,
        )
    
    def _start_polling(self) -> None:
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())

    async def _stop_polling(self) -> None:
        task, self._poll_task = self._poll_task, None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _poll_loop(self) -> None:
        """Keep the remote in step with changes made on the device itself."""
        loop = asyncio.get_running_loop()
        last_full_refresh = loop.time()
        unreachable = False

        while True:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                changed = await self.refresh_state()
            except asyncio.CancelledError:
                raise
            except Exception as err:
                if not unreachable:
                    _LOG.warning("[%s] Lost contact with the device while polling: %s", self.log_id, err)
                    unreachable = True
                continue

            if unreachable:
                _LOG.info("[%s] Device is answering again", self.log_id)
                unreachable, changed = False, True

            if changed or loop.time() - last_full_refresh >= FULL_REFRESH_INTERVAL:
                last_full_refresh = loop.time()
                self.push_update()

    # =========================================================================
    # System & power
    # =========================================================================

    async def get_version(self) -> dict[str, Any]:
        """Fetch firmware version and build metadata via GET /v1/version."""
        return await self._api.get_json("/v1/version")

    async def get_mac_address(self) -> str:
        """Fetch the hardware MAC address via GET /v1/mac."""
        data = await self._api.get_json("/v1/mac")
        return data.get("mac", "00:00:00:00:00:00")

    async def get_system_power(self) -> str:
        """Get the power state via GET /v1/power: '1' for on, '0' for standby."""
        data = await self._api.get_json("/v1/power")
        return str(data.get("state", "0"))

    async def get_system_status(self) -> dict[str, Any]:
        """Retrieve overall system status and version/build metadata via GET /v1/status."""
        return await self._api.get_json("/v1/status")

    async def get_host_ip(self) -> str:
        """Get the system host IP address via GET /v1/hostip."""
        text = await self._api.get_text("/v1/hostip")
        try:
            data = json.loads(text)
        except ValueError:
            return text.strip()
        if isinstance(data, dict):
            return data.get("ip", data.get("hostip", ""))
        return text.strip()

    async def get_temperature(self) -> float:
        """Get the processor's internal temperature via GET /v1/temperature."""
        data = await self._api.get_json("/v1/temperature")
        return float(data["temperature"])
    
    async def reboot(self) -> None:
        """Initiate a controlled system restart via POST /v1/reboot (takes ~30-45 s)."""
        _LOG.warning("[%s] Initiating system reboot...", self.log_id)
        await self._api.post("/v1/reboot", {})
        _LOG.info("[%s] Reboot command sent successfully.", self.log_id)

    async def _set_power(self, on: bool) -> None:
        await self._api.post("/v1/power", {"state": "1" if on else "0"})

        attrs = self._media_player_attributes.get(self.identifier)
        if attrs:
            attrs.STATE = media_player.States.ON if on else media_player.States.OFF
        self.push_update()

    async def power_on(self) -> None:
        """Turn on the device."""
        _LOG.debug("[%s] Powering on", self.log_id)
        await self._set_power(True)

    async def power_off(self) -> None:
        """Turn off the device."""
        _LOG.debug("[%s] Powering off", self.log_id)
        await self._set_power(False)

    async def power_toggle(self) -> None:
        """Toggle the device power state."""
        _LOG.debug("[%s] Toggling power", self.log_id)
        await self._set_power(self.state != media_player.States.ON)

    async def trigger_hpd(self, state: bool = True) -> bool:
        """Trigger HDMI hotplug detection via POST /v1/hdmi/output/hpd."""
        _LOG.debug("[%s] Triggering HDMI HPD with state: %s", self.log_id, state)
        await self._api.post("/v1/hdmi/output/hpd", {"state": state})
        return True

    async def get_display_brightness(self) -> int:
        """Get front panel display brightness via GET /v1/displaybrightness."""
        data = await self._api.get_json("/v1/displaybrightness")
        return int(data.get("brightness", 0))

    async def set_display_brightness(self, brightness: int) -> bool:
        """Set front panel display brightness via POST /v1/displaybrightness."""
        _LOG.debug("[%s] Setting display brightness to: %s", self.log_id, brightness)
        await self._api.post("/v1/displaybrightness", {"brightness": brightness})
        return True

    async def step_display_brightness(self, delta: int) -> int:
        """Change the display brightness by delta percent (kept within 0-100). Returns the new level."""
        level = max(BRIGHTNESS_MIN, min(BRIGHTNESS_MAX, await self.get_display_brightness() + delta))
        await self.set_display_brightness(level)
        return level

    # =========================================================================
    # Volume & mute
    # =========================================================================
    #
    # The device only accepts integer percent on /v1/vol (floats with a fraction are
    # rejected, negative numbers are silently clamped to 0). So the percent is kept
    # locally, changed optimistically so the remote responds at once, and then sent.

    async def get_volume(self) -> int:
        """Ask the device for its volume as an integer percent."""
        data = await self._api.get_json("/v1/vol")
        return int(round(float(data.get("level", 0))))

    def _osd_volume(self) -> int:
        """The volume the remote displays: dB in relative mode, percent otherwise."""
        return int(round(self.volume_db)) if self.is_relative_volume else self._volume_pct

    def _publish_volume(self) -> None:
        """Show the cached volume on the remote."""
        attrs = self._media_player_attributes.get(self.identifier)
        if attrs:
            attrs.VOLUME = self._osd_volume()
        self.push_update()

    async def set_volume_pct(self, pct: int) -> None:
        """Set the volume. Updates the remote immediately, then sends the integer percent."""
        pct = max(0, min(100, int(round(pct))))
        if pct == self._volume_pct:
            return

        self._volume_pct = pct
        self._vol_changes += 1
        self._publish_volume()

        failed = False
        try:
            async with self._vol_lock:
                await self._api.post("/v1/vol", {"level": pct})
        except Exception:
            _LOG.exception("[%s] Volume change failed", self.log_id)
            failed = True

        # Put the real value back, unless more presses are queued (the last one will do it).
        if failed and not self._vol_lock.locked():
            await self.resync_volume()

    async def step_volume(self, direction: int) -> None:
        """Step the volume up (direction > 0) or down by one step in the current volume mode."""
        await self.set_volume_pct(step_percent(self._volume_pct, direction, relative=self.is_relative_volume))

    async def resync_volume(self) -> None:
        """Replace the cached volume with what the device reports."""
        if self._vol_lock.locked():
            return  # a change is in flight, don't overwrite it
        try:
            self._volume_pct = await self.get_volume()
        except Exception as err:
            _LOG.debug("[%s] Volume resync failed: %s", self.log_id, err)
            return
        self._publish_volume()

    async def get_mute(self) -> bool:
        """Get master mute status via GET /v1/mute."""
        data = await self._api.get_json("/v1/mute")
        return bool(data.get("state", False))

    async def set_mute(self, muted: bool) -> None:
        """Set master mute status via POST /v1/mute."""
        _LOG.debug("[%s] Setting mute to: %s", self.log_id, muted)
        await self._api.post("/v1/mute", {"state": muted})

        attrs = self._media_player_attributes.get(self.identifier)
        if attrs:
            attrs.MUTED = muted
        self.push_update()

    async def get_max_volume(self) -> float:
        """Get the maximum volume limit via GET /v1/maxvol."""
        data = await self._api.get_json("/v1/maxvol")
        return float(data.get("level", 100.0))

    async def set_max_volume(self, max_vol: float) -> None:
        """Set the maximum volume limit via POST /v1/maxvol."""
        await self._api.post("/v1/maxvol", {"level": max_vol})

    async def get_power_on_volume(self) -> float:
        """Get the default startup volume via GET /v1/onvol."""
        data = await self._api.get_json("/v1/onvol")
        return float(data.get("level", 0.0))

    async def set_power_on_volume(self, on_vol: float) -> None:
        """Set the default startup volume via POST /v1/onvol."""
        await self._api.post("/v1/onvol", {"level": on_vol})

    # =========================================================================
    # Inputs
    # =========================================================================

    async def get_active_input(self) -> str:
        """Get the active input via GET /api/atlas/input/active."""
        data = await self._api.get_json(INPUT_ACTIVE_PATH)
        return str(data.get("source", data.get("input", "")))

    async def async_fetch_dynamic_inputs(self) -> dict[int, str]:
        """Fetch the user's custom input names, keeping the default name for any that are not set."""
        input_names: dict[int, str] = {}

        for input_id in range(1, len(DEFAULT_INPUTS) + 1):
            try:
                data = await self._api.get_json("/api/atlas/input/name", params={"input": input_id}, timeout=1.0)
            except (aiohttp.ClientResponseError, ValueError):
                continue  # no usable name for this input, try the next one
            except (aiohttp.ClientError, TimeoutError, OSError) as err:
                _LOG.debug("[%s] Stopped fetching input names at input %d: %s", self.log_id, input_id, err)
                break

            name = data.get("name") if isinstance(data, dict) else None
            if isinstance(name, str) and name.strip():
                input_names[input_id] = name.strip()

        self._input_names_map = input_names

        attrs = self._media_player_attributes.get(self.identifier)
        if attrs:
            attrs.SOURCE_LIST = [input_names.get(i, default) for i, default in enumerate(DEFAULT_INPUTS, start=1)]
            try:  # the current source was read before the names were known
                attrs.SOURCE = await self.get_active_input_name()
            except Exception as err:
                _LOG.debug("[%s] Could not refresh the current source name: %s", self.log_id, err)
            self.push_update()
        return input_names

    def _resolve_input_key(self, source: str) -> str:
        """Turn a name the user picked (custom or default, any casing) into the device's input key."""
        wanted = source.strip().casefold()

        for input_id, custom_name in self._input_names_map.items():
            if custom_name.strip().casefold() == wanted and 1 <= input_id <= len(DEFAULT_INPUTS):
                return DEFAULT_INPUTS[input_id - 1]

        for default_name in DEFAULT_INPUTS:
            if default_name.casefold() == wanted:
                return default_name

        return source

    async def get_active_input_name(self) -> str:
        """Get the active input's friendly name, using the user's custom names where set."""
        raw_input = await self.get_active_input()
        if not raw_input:
            return "Unknown"

        names = self.source_list
        if not names:
            return raw_input

        if raw_input.isdigit():
            index = int(raw_input) - 1
            if 0 <= index < len(names):
                return names[index]

        for index, default_name in enumerate(DEFAULT_INPUTS):
            if raw_input.casefold() == default_name.casefold() and index < len(names):
                return names[index]

        return raw_input

    async def set_active_input(self, source: str) -> None:
        """Switch the active input via POST /api/atlas/input/active."""
        target_key = self._resolve_input_key(source)
        _LOG.debug("[%s] Setting active input '%s' (device key '%s')", self.log_id, source, target_key)

        await self._api.post(INPUT_ACTIVE_PATH, {"input": target_key})

        attrs = self._media_player_attributes.get(self.identifier)
        if attrs:
            attrs.SOURCE = source
        self.push_update()

    # =========================================================================
    # Dirac Live (Atlas RPC on port 80)
    # =========================================================================

    async def async_get_dirac_active_slot(self) -> int:
        """Ask the device which Dirac slot is active (an empty reply means slot 0). Raises if it can't be read."""
        status, body = await self._api.rpc(atlas.GET_ACTIVE_SLOT, timeout=2.0)
        if status != 200:
            raise RuntimeError(f"{atlas.GET_ACTIVE_SLOT} returned HTTP {status}")
        return atlas.parse_active_slot(body)

    async def async_get_dirac_filtering(self) -> bool:
        """Ask the device whether Dirac filtering is on. Raises if the device can't be read."""
        status, body = await self._api.rpc(atlas.GET_FILTERING, timeout=2.0)
        if status != 200:
            raise RuntimeError(f"{atlas.GET_FILTERING} returned HTTP {status}")
        return atlas.parse_filtering(body)

    async def async_fetch_dirac_slot_names(self) -> dict[int, str]:
        """Fetch the user's Dirac slot profile names (kept as-is if the device can't be read)."""
        try:
            status, body = await self._api.rpc(
                atlas.GET_FILTER_SLOTS,
                headers=atlas.browser_headers(self._api.atlas_origin),
                timeout=3.0,
            )
        except Exception as err:
            _LOG.error("[%s] Failed to fetch Dirac slot names: %s", self.log_id, err)
            return {}

        _LOG.debug("[%s] GetDiracFilterSlots status %d, %d bytes", self.log_id, status, len(body))
        slot_names = atlas.parse_slot_names(body) if status == 200 else {}
        if slot_names:
            self._dirac_slot_names_map = slot_names
            _LOG.debug("[%s] Dirac slot names: %s", self.log_id, slot_names)
        return slot_names

    async def async_set_dirac_filter_slot(self, slot_index: int) -> bool:
        """Switch the active Dirac filter slot (0, 1 or 2). Unknown indexes select slot 0."""
        payload = atlas.SLOT_PAYLOADS.get(slot_index, atlas.SLOT_PAYLOADS[0])
        success = await self._atlas_set(atlas.SET_FILTER_SLOT, payload)
        if success:
            self._dirac_slot = slot_index if slot_index in atlas.SLOT_PAYLOADS else 0
            self.push_update()
        return success

    async def async_set_dirac_filtering(self, enabled: bool) -> bool:
        """Enable or disable master Dirac filtering."""
        payload = atlas.FILTERING_ON if enabled else atlas.FILTERING_OFF
        success = await self._atlas_set(atlas.SET_FILTERING, payload)
        if success:
            self._dirac_filtering = enabled
            self.push_update()
        return success

    async def _atlas_set(self, method: str, payload: bytes) -> bool:
        try:
            status, _ = await self._api.rpc(method, payload, timeout=5.0)
        except Exception as err:
            _LOG.error("[%s] %s failed: %s", self.log_id, method, err)
            return False
        return status < 400

    # =========================================================================
    # Audio status, formats & processing modes
    # =========================================================================

    async def get_video_detail(self) -> dict[str, Any]:
        """Get video signal details (resolution, frame rate, colour space, HDR, HDCP) via GET /v1/videodetail."""
        return await self._api.get_json("/v1/videodetail")

    async def get_video_format(self) -> str:
        """Get the video resolution and frame rate (for example "3840x2160@23.98p") via GET /v1/videoformat."""
        data = await self._api.get_json("/v1/videoformat")
        return str(data.get("format") or "")
    
    async def get_audio_detail(self) -> dict[str, Any]:
        """Get audio signal details (format, rate, bit depth, channels) via GET /v1/audiodetail."""
        return await self._api.get_json("/v1/audiodetail")

    async def get_audio_format(self) -> str:
        """Get the detected codec (PCM, Dolby Atmos, DTS:X, ...) via GET /v1/audioformat."""
        data = await self._api.get_json("/v1/audioformat")
        return str(data.get("format", data.get("codec", "Unknown")))

    async def get_audio_bit_depth(self) -> int:
        """Get the detected bit depth via GET /v1/bit."""
        data = await self._api.get_json("/v1/bit")
        return int(data.get("bit", data.get("bits", 0)))

    async def get_audio_sample_rate(self) -> int:
        """Get the detected sample rate in Hz via GET /v1/sample."""
        data = await self._api.get_json("/v1/sample")
        return int(data.get("sample", data.get("rate", 0)))

    async def get_audio_mode(self) -> str:
        """Get the current audio processing mode via GET /v1/audiomode."""
        data = await self._api.get_json("/v1/audiomode")
        return str(data.get("mode", data.get("audiomode", "")))

    async def set_audio_mode(self, mode: str) -> None:
        """Set the audio processing mode via POST /v1/audiomode."""
        _LOG.debug("[%s] Setting audio processing mode to: %s", self.log_id, mode)
        await self._api.post("/v1/audiomode", {"mode": mode})

        attrs = self._media_player_attributes.get(self.identifier)
        if attrs:
            attrs.SOUND_MODE = mode
        self.push_update()

    async def get_input_bass(self, input_name: str) -> int:
        """Get an input's bass level via GET /api/atlas/input/{input}/bass."""
        data = await self._api.get_json(f"/api/atlas/input/{input_name}/bass")
        return int(data.get("level", 0))

    async def set_input_bass(self, input_name: str, bass: int) -> bool:
        """Set an input's bass level via POST /api/atlas/input/{input}/bass/{level}."""
        _LOG.debug("[%s] Setting input bass for %s to: %s", self.log_id, input_name, bass)
        await self._api.post(f"/api/atlas/input/{input_name}/bass/{bass}", {"inputId": 0})
        return True

    async def get_input_treble(self, input_name: str) -> int:
        """Get an input's treble level via GET /api/atlas/input/{input}/treb."""
        data = await self._api.get_json(f"/api/atlas/input/{input_name}/treb")
        return int(data.get("level", 0))

    async def set_input_treble(self, input_name: str, treble: int) -> bool:
        """Set an input's treble level via POST /api/atlas/input/{input}/treb/{level}."""
        _LOG.debug("[%s] Setting input treble for %s to: %s", self.log_id, input_name, treble)
        await self._api.post(f"/api/atlas/input/{input_name}/treb/{treble}", {"inputId": 0})
        return True

    async def step_input_tone(self, band: str, delta: int) -> int:
        """
        Change the active input's bass or treble by delta dB (kept within +/-12 dB).

        :param band: "bass" or "treble"
        :return: the new level
        """
        get_level, set_level = {
            "bass": (self.get_input_bass, self.set_input_bass),
            "treble": (self.get_input_treble, self.set_input_treble),
        }[band]

        active_input = await self.get_active_input() or DEFAULT_INPUTS[0]
        level = max(TONE_MIN_DB, min(TONE_MAX_DB, await get_level(active_input) + delta))
        await set_level(active_input, level)
        return level

    # =========================================================================
    # Simple commands
    # =========================================================================

    async def send_command(self, command: str, **kwargs: Any) -> None:
        """Run one of the simple commands (see const.SimpleCommands)."""
        _LOG.debug("[%s] Sending command: %s with kwargs: %s", self.log_id, command, kwargs)

        match command:
            case SimpleCommands.REBOOT:
                await self.reboot()
            case SimpleCommands.GET_STATUS:
                _LOG.debug("[%s] System status: %s", self.log_id, await self.get_system_status())
            case _:
                _LOG.warning("[%s] Unknown command: %s", self.log_id, command)
