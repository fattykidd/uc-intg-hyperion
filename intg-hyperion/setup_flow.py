"""
Setup flow for AudioControl Hyperion APR-16 integration.
"""

from __future__ import annotations

import logging
from typing import Any
import aiohttp

from config import APR16Config
from ucapi import RequestUserInput
from ucapi_framework import BaseSetupFlow

_LOG = logging.getLogger(__name__)

DEFAULT_NAME = "AudioControl Hyperion APR-16"


class HyperionSetupFlow(BaseSetupFlow[APR16Config]):
    """
    Setup flow for AudioControl Hyperion APR-16 integration.
    """

    def _existing_config(self) -> APR16Config | None:
        """Return the saved config when updating an existing device."""
        if self._add_mode:
            return None
        return self.selected_config_entry

    def _build_form(
        self,
        name: str,
        address: str,
        port: str,
        error: str | None = None,
    ) -> RequestUserInput:
        """Build the input form, optionally displaying an inline error message."""
        settings: list[dict[str, Any]] = []
        if error:
            settings.append(
                {
                    "id": "error",
                    "label": {"en": "Error"},
                    "field": {"label": {"value": {"en": error}}},
                }
            )

        settings.extend(
            [
                {
                    "id": "name",
                    "label": {"en": "Device Name"},
                    "field": {"text": {"value": name}},
                },
                {
                    "id": "address",
                    "label": {"en": "IP Address or Hostname"},
                    "field": {"text": {"value": address}},
                },
                {
                    "id": "port",
                    "label": {"en": "Port"},
                    "field": {"text": {"value": port}},
                },
            ]
        )
        return RequestUserInput({"en": "AudioControl Hyperion APR-16 Setup"}, settings)

    def get_manual_entry_form(self) -> RequestUserInput:
        """Define manual entry fields, prefilled with saved values on update."""
        existing = self._existing_config()
        if existing:
            return self._build_form(existing.name, existing.address, str(existing.port))
        return self._build_form(DEFAULT_NAME, "", "8080")

    async def query_device(
        self, input_values: dict[str, Any]
    ) -> APR16Config | RequestUserInput:
        """
        Create device configuration from user input, validating connectivity.
        """
        name = (input_values.get("name") or "").strip()
        address = (input_values.get("address") or "").strip()
        raw_port = (input_values.get("port") or "8080").strip()

        if not address:
            return self._build_form(name, address, raw_port, "IP address or hostname is required.")

        try:
            port = int(raw_port)
        except ValueError:
            return self._build_form(name, address, raw_port, f"Invalid port provided: {raw_port}")

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

                    existing = self._existing_config()
                    identifier = existing.identifier if existing else data.get(
                        "serial",
                        data.get("mac", address.replace(".", "_").replace(":", "_")),
                    )

            _LOG.info("Successfully connected to Hyperion APR-16 at %s:%s", address, port)
            return APR16Config(
                identifier=identifier,
                name=name,
                address=address,
                port=port,
            )

        except (aiohttp.ClientConnectionError, ConnectionError) as ex:
            _LOG.error("Connection refused to %s:%s: %s", address, port, ex)
            return self._build_form(
                name,
                address,
                raw_port,
                "Connection refused. Check that the device is powered on and reachable.",
            )
        except TimeoutError as ex:
            _LOG.error("Connection timeout to %s:%s: %s", address, port, ex)
            return self._build_form(
                name,
                address,
                raw_port,
                "Connection timed out. Please check the IP address and port.",
            )
        except Exception as ex:
            _LOG.error("Failed to connect to %s:%s: %s", address, port, ex)
            return self._build_form(
                name,
                address,
                raw_port,
                f"Connection failed: {ex}",
            )