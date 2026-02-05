"""Config flow for ZeroBreeze AC integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, SERVICE_UUID, CONF_LOGIN_KEY, CONF_DEVICE_UUID

_LOGGER = logging.getLogger(__name__)


class ZeroBreezeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZeroBreeze AC."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._selected_device: BluetoothServiceInfoBleak | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> FlowResult:
        """Handle bluetooth discovery."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()

        self._selected_device = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }

        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Confirm bluetooth discovery and get login key and device UUID."""
        assert self._selected_device is not None

        if user_input is not None:
            return self.async_create_entry(
                title=self._selected_device.name or f"ZeroBreeze {self._selected_device.address[-5:]}",
                data={
                    CONF_ADDRESS: self._selected_device.address,
                    CONF_NAME: self._selected_device.name,
                    CONF_LOGIN_KEY: user_input[CONF_LOGIN_KEY],
                    CONF_DEVICE_UUID: user_input[CONF_DEVICE_UUID],
                },
            )

        return self.async_show_form(
            step_id="bluetooth_confirm",
            data_schema=vol.Schema({
                vol.Required(CONF_LOGIN_KEY): str,
                vol.Required(CONF_DEVICE_UUID): str,
            }),
            description_placeholders={
                "name": self._selected_device.name or self._selected_device.address,
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user-initiated config flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            login_key = user_input[CONF_LOGIN_KEY]
            device_uuid = user_input[CONF_DEVICE_UUID]

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            device_info = self._discovered_devices.get(address)
            name = device_info.name if device_info else f"ZeroBreeze {address[-5:]}"

            return self.async_create_entry(
                title=name,
                data={
                    CONF_ADDRESS: address,
                    CONF_NAME: name,
                    CONF_LOGIN_KEY: login_key,
                    CONF_DEVICE_UUID: device_uuid,
                },
            )

        # Discover ZeroBreeze devices
        self._discovered_devices = {}
        for discovery_info in async_discovered_service_info(self.hass):
            if SERVICE_UUID.lower() in [s.lower() for s in discovery_info.service_uuids]:
                self._discovered_devices[discovery_info.address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

        # Build device selection schema
        device_options = {
            address: f"{info.name or 'ZeroBreeze'} ({address})"
            for address, info in self._discovered_devices.items()
        }

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_ADDRESS): vol.In(device_options),
                vol.Required(CONF_LOGIN_KEY): str,
                vol.Required(CONF_DEVICE_UUID): str,
            }),
            errors=errors,
        )
