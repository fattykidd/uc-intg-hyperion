"""
Constants for the AudioControl Hyperion APR-16 Integration.

This module contains configuration defaults, timeouts, and simple command enums
used throughout the integration.
"""

from enum import StrEnum

# Default connection settings
DEFAULT_PORT = 8080
DEFAULT_TIMEOUT = 10.0  # seconds


class SimpleCommands(StrEnum):
    """
    Additional simple commands for the APR-16 processor.

    These appear as standalone buttons or actions in the Unfolded Circle remote UI.
    """

    REBOOT = "reboot"
    GET_STATUS = "get_status"