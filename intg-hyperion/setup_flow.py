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
                        "en": "Setup your Hyperion APR-16",
                    },
                    "field": {
                        "label": {
                            "value": {
                                "en": (
                                    "Please supply the IP address and Port for your AudioControl Hyperion APR-16 processor."
                                )
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
                    # Use text field just like Jack's driver to ensure frontend compatibility
                    "field": {"text": {"value": "8080"}},
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
        Create device configuration from user input, validating connectivity.
        """
        name = input_values.get("name", "").strip()
        address = input_values.get("address", "").strip()
        raw_port = str(input_values.get("port", "8080")).strip()

        if not address or not raw_port:
            _LOG.warning("Address and port are required, re-displaying form")
            return self.get_manual_entry_form()

        try:
            port = int(raw_port)
        except ValueError:
            _LOG.error("Invalid port provided: %s", raw_port)
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