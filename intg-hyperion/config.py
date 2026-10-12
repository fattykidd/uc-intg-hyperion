# config.py
from dataclasses import dataclass
from ucapi_framework import BaseConfigManager

@dataclass
class APR16Config:
    """
    Device configuration dataclass.

    This dataclass holds all the configuration needed to connect to and
    identify a device. Add or remove fields as needed for your device.
    """

    identifier: str
    """Unique identifier of the device (e.g., MAC address, serial number)."""

    name: str
    """Friendly name of the device for display purposes."""

    address: str
    """IP address or hostname of the device."""

    # TODO: Add any additional configuration fields your device needs
    # Examples:
    port: int = 8080
    """Port number for device communication."""
    # username: str = ""
    # """Username for authentication (if required)."""
    # password: str = ""
    # """Password for authentication (if required)."""
    # model: str = ""
    # """Device model for feature detection."""

class APR16ConfigManager(BaseConfigManager[APR16Config]):
    """Configuration manager with automatic JSON persistence."""
    pass