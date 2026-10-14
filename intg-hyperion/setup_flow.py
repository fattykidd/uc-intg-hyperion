"""
Setup Flow Module for AudioControl Hyperion APR-16.

This module handles the device setup and configuration process. It provides
forms for manual device entry and validation of device connections.

:license: Mozilla Public License Version 2.0, see LICENSE for more details.
"""

import logging
from typing import Any
import aiohttp

from config import APR16Config
from ucapi import IntegrationSetupError, RequestUserInput, SetupError
from ucapi_framework import BaseSetupFlow

_LOG = logging.getLogger(__name__)


class HyperionSetupFlow(BaseSetupFlow[APR16Config]):
    """
    Setup flow for AudioControl Hyperion APR-16 integration.

    Handles device configuration through manual entry and verifies connectivity.
    """

    def get_manual_entry_form(self) -> RequestUserInput:
        """
        Return the manual entry form for device setup.
        """
        return RequestUserInput(
            {"en": "AudioControl Hyperion APR-16 Setup"},
            [
                {
                    "id": "info",
                    "label": {
                        "en": "Configure Hyperion APR-16",
                    },
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Please enter the connection details for your AudioControl Hyperion APR-16 processor.",
                                ),
                            }
                        }
                    },
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "name",
                    "label": {
                        "en": "Device Name",
                    },
                },
                {
                    "field": {"text": {"value": ""}},
                    "id": "address",
                    "label": {
                        "en": "IP Address or Hostname",
                    },
                },
                {
                    "field": {"text": {"value": "8080", "min": 1, "max": 65535}},
                    "id": "port",
                    "label": {
                        "en": "Port",
                    },
                },
            ],
        )

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> APR16Config | SetupError | RequestUserInput:
        """
        Create device configuration from user input, validating connectivity
        against the Hyperion APR-16 system status endpoint.
        """
        name = input_values.get("name", "").strip()
        address = input_values.get("address", "").strip()
        port = input_values.get("port", "8080")

        if not address:
            _LOG.warning("Address is required, re-displaying form")
            return self.get_manual_entry_form()

        if not name:
            name = f"Hyperion APR-16 ({address})"

        _LOG.debug(
            "Attempting to connect to AudioControl Hyperion APR-16 at %s:%s",
            address,
            port,
        )
        base_url = f"http://{address}:{port}"

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{base_url}/v1/status",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    resp.raise_for_status()
                    data = await resp.json()

                    identifier = data.get(
                        "serial",
                        data.get(
                            "mac", address.replace(".", "_").replace(":", "_")
                        ),
                    )

            return APR16Config(
                identifier=identifier,
                name=name,
                address=address,
                port=port,
            )

        except (aiohttp.ClientConnectionError, ConnectionError) as ex:
            _LOG.error("Connection refused to %s:%s: %s", address, port, ex)
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)

        except TimeoutError as ex:
            _LOG.error("Connection timeout to %s:%s: %s", address, port, ex)
            return SetupError(IntegrationSetupError.TIMEOUT)

        except Exception as ex:
            _LOG.error("Failed to connect to %s:%s: %s", address, port, ex)
            return SetupError(IntegrationSetupError.CONNECTION_REFUSED)
