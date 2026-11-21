"""
Constants for the AudioControl Hyperion APR-16 integration.

Connection defaults, volume modes, the default input list, the audio mode
mapping and the Dirac slot defaults. Nothing in here talks to the device.
"""

from enum import StrEnum

# --- Connection -------------------------------------------------------------
DEFAULT_PORT = 8080
ATLAS_PORT = 80  # Connect/protobuf endpoint used for Dirac Live control
ATLAS_SERVICE = "commands.v1.AtlasService"
STATE_STREAM_PATH = "/ws/state"  # WebSocket on the Atlas port that tells us about every change
DEFAULT_TIMEOUT = 5.0  # seconds

# Keeping the remote in step with changes made on the device itself (front panel, web UI).
# Normally the device's state streams do this. Polling takes over whenever they are down.
POLL_INTERVAL = 5.0  # seconds between checks of power, volume, mute, input and audio mode
FULL_REFRESH_INTERVAL = 30.0  # seconds between refreshes of every sensor, even if nothing above changed

# State streams (see stream.py)
STREAM_SILENCE_TIMEOUT = 30.0  # seconds without a message (the device sends a heartbeat every ~15 s) before reconnecting
STREAM_CONNECT_TIMEOUT = 10.0  # seconds to open a stream
STREAM_RECONNECT_MIN = 1.0  # seconds before the first reconnect attempt, doubled after each failure
STREAM_RECONNECT_MAX = 30.0  # longest wait between reconnect attempts
STREAM_STABLE_AFTER = 30.0  # a connection that lasted this long is healthy: the next reconnect starts at the minimum

# --- Volume -----------------------------------------------------------------
VOLUME_SETTLE = 1.5  # seconds after a volume change we made, during which the device's own reports of it are not trusted
VOLUME_MODE_ABSOLUTE = "absolute"  # remote shows percent (0-100)
VOLUME_MODE_RELATIVE = "relative"  # remote shows decibels (-127.5 to 0)

# --- Adjustment limits -----------------------------------------------------
TONE_MIN_DB = -12
TONE_MAX_DB = 12
BRIGHTNESS_MIN = 0
BRIGHTNESS_MAX = 100

# --- Inputs -----------------------------------------------------------------
# Hardware input keys, in the device's own order (input id 1 is index 0).
DEFAULT_INPUTS: tuple[str, ...] = (
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
)

# --- Audio modes ------------------------------------------------------------
# Friendly name shown on the remote -> string the device API expects.
AUDIO_MODE_MAPPING: dict[str, str] = {
    "Direct Mode": "dspdirectmode",
    "DTS Neural:X": "dts-nx",
    "Stereo": "2ch",
    "All Channel Stereo": "multich",
    "Dolby Mode": "dolby mode",
    "Native": "native",
    "Dolby Surround": "dolby surround",
}
API_TO_UI_AUDIO_MODE = {api: ui for ui, api in AUDIO_MODE_MAPPING.items()}

# --- Dirac Live -------------------------------------------------------------
# Used until the real slot names have been read from the device.
DEFAULT_DIRAC_SLOTS: dict[int, str] = {
    0: "Slot 0",
    1: "Slot 1",
    2: "Slot 2",
}


class SimpleCommands(StrEnum):
    """
    Additional simple commands for the APR-16 processor.

    These appear as standalone buttons or actions in the Unfolded Circle remote UI.
    """

    REBOOT = "reboot"
    GET_STATUS = "get_status"
