"""
Remote Two/3 Integration Driver for AudioControl Hyperion APR-16.

This is the main entry point for the integration driver. It initializes
the driver, sets up logging, and starts the integration API.
"""

import asyncio
import logging
import os

from ucapi_framework import (
    BaseConfigManager,
    BaseIntegrationDriver,
    get_config_path,
)

from config import APR16Config
from device import Apr16
from media_player import Apr16MediaPlayer
from selector import Apr16AudioModeSelect
from button import (
    Apr16RebootButton, 
    Apr16HpdButton,
    Apr16VolumeUpButton,
    Apr16VolumeDownButton,
    Apr16InputBassUpButton,
    Apr16InputBassDownButton,
    Apr16InputTrebleUpButton,
    Apr16InputTrebleDownButton,
    Apr16DisplayBrightnessUpButton,
    Apr16DisplayBrightnessDownButton,
)
from sensor import (
    Apr16AudioFormatSensor,
    Apr16VideoDetailSensor,
    Apr16AbsoluteVolumeSensor,
    Apr16RelativeVolumeSensor,
    Apr16MuteSensor,
    Apr16DisplayBrightnessSensor,
    Apr16AudioDetailSensor,
    Apr16HostIpSensor,
    Apr16InputBassSensor,
    Apr16InputTrebleSensor,
)
from setup_flow import HyperionSetupFlow

_LOG = logging.getLogger(__name__)


class Apr16Driver(BaseIntegrationDriver[Apr16, APR16Config]):
    """AudioControl Hyperion APR-16 integration driver."""

    def __init__(self):
        super().__init__(
            device_class=Apr16,
            entity_classes=[
                Apr16MediaPlayer,
                Apr16AudioModeSelect,
                Apr16AudioFormatSensor,
                Apr16VideoDetailSensor,
                Apr16AbsoluteVolumeSensor,
                Apr16RelativeVolumeSensor,
                Apr16MuteSensor,
                Apr16DisplayBrightnessSensor,
                Apr16AudioDetailSensor,
                Apr16HostIpSensor,
                Apr16InputBassSensor,
                Apr16InputTrebleSensor,
                Apr16RebootButton, 
                Apr16HpdButton,
                Apr16VolumeUpButton,
                Apr16VolumeDownButton,
                Apr16InputBassUpButton,
                Apr16InputBassDownButton,
                Apr16InputTrebleUpButton,
                Apr16InputTrebleDownButton,
                Apr16DisplayBrightnessUpButton,
                Apr16DisplayBrightnessDownButton,
            ],
            driver_id="audiocontrol_hyperion_apr16",
            require_connection_before_registry=True,
        )


async def main():
    """Start the Remote Two/3 integration driver."""
    logging.basicConfig()

    # Configure logging level from environment variable
    level = os.getenv("UC_LOG_LEVEL", "DEBUG").upper()
    logging.getLogger("driver").setLevel(level)
    logging.getLogger("media_player").setLevel(level)
    logging.getLogger("device").setLevel(level)
    logging.getLogger("setup_flow").setLevel(level)

    # Instantiate our custom driver class
    driver = Apr16Driver()

    # Configure and initialize configuration manager using APR16Config
    driver.config_manager = BaseConfigManager(
        get_config_path(driver.api.config_dir_path),
        driver.on_device_added,
        driver.on_device_removed,
        config_class=APR16Config,
    )

    # Register all configured devices from config file
    await driver.register_all_configured_devices()

    # Setup handler for manual IP/port entry
    setup_handler = HyperionSetupFlow.create_handler(driver, discovery=None)

    # Initialize the API with the driver configuration
    await driver.api.init("driver.json", setup_handler)

    # Keep the driver running
    await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())