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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> APR16Config | SetupError | RequestUserInput:
        """Handle the initial user setup step."""
        
        # If no user input has been submitted yet, render the form
        if user_input is None:
            return RequestUserInput(
                {"en": "AudioControl Hyperion APR-16 Setup"},
                [
                    {
                        "id": "info",
                        "label": {"en": "Configure Hyperion APR-16"},
                        "field": {
                            "label": {
                                "value": {
                                    "en": "Please enter the connection details for your AudioControl Hyperion APR-16 processor."
                                }
                            }
                        },
                    },
                    {
                        "field": {"text": {"value": ""}},
                        "id": "name",
                        "label": {"en": "Device Name"},
                    },
                    {
                        "field": {"text": {"value": ""}},
                        "id": "address",
                        "label": {"en": "IP Address or Hostname"},
                    },
                    {
                        "field": {"integer": {"value": 8080, "min": 1, "max": 65535}},
                        "id": "port",
                        "label": {"en": "Port"},
                    },
                ],
            )

        # User submitted the form, now process and validate input values
        name = user_input.get("name", "").strip()
        address = user_input.get("address", "").strip()
        port = user_input.get("port", 8080)

        if not address:
            _LOG.warning("Address is required, re-displaying form")
            return await self.async_step_user(None)

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