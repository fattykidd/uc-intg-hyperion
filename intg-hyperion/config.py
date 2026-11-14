"""Device configuration for the AudioControl Hyperion APR-16 integration."""

from dataclasses import dataclass

from ucapi_framework import BaseConfigManager

from const import DEFAULT_PORT, VOLUME_MODE_ABSOLUTE


@dataclass
class APR16Config:
    """Everything needed to find and talk to one APR-16."""

    identifier: str
    """Unique identifier of the device (serial number, MAC address or address)."""

    name: str
    """Friendly name shown on the remote."""

    address: str
    """IP address or hostname of the device."""

    port: int = DEFAULT_PORT
    """HTTP port of the device's REST API."""

    volume_mode: str = VOLUME_MODE_ABSOLUTE
    """Volume style on the remote: 'absolute' for percent, 'relative' for decibels."""


class APR16ConfigManager(BaseConfigManager[APR16Config]):
    """Configuration manager with automatic JSON persistence."""
