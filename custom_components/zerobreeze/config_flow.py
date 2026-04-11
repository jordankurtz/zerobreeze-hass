"""Config flow for ZeroBreeze AC integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
    async_scanner_devices_by_address,
)
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, SERVICE_UUID, CONF_LOGIN_KEY, CONF_DEVICE_UUID, CONF_SCANNER_SOURCE

_LOGGER = logging.getLogger(__name__)

SCANNER_SOURCE_AUTO = "auto"


def _get_scanner_options(hass, address: str) -> dict[str, str]:
    """Return {source: label} for all scanners that can see the device."""
    options = {SCANNER_SOURCE_AUTO: "Automatic (best available)"}
    for scanner_device in async_scanner_devices_by_address(hass, address, connectable=True):
        scanner = scanner_device.scanner
        options[scanner.source] = f"{scanner.name} ({scanner.source})"
    return options


class ZeroBreezeConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for ZeroBreeze AC."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> ZeroBreezeOptionsFlow:
        """Return the options flow."""
        return ZeroBreezeOptionsFlow()

    def __init__(self) -> None:
        """Initialize config flow."""
        self._discovered_devices: dict[str, BluetoothServiceInfoBleak] = {}
        self._selected_device: BluetoothServiceInfoBleak | None = None
        self._pending_data: dict[str, Any] = {}

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
            # Use the scanner that discovered the device
            self._pending_data = {
                CONF_ADDRESS: self._selected_device.address,
                CONF_NAME: self._selected_device.name,
                CONF_LOGIN_KEY: user_input[CONF_LOGIN_KEY],
                CONF_DEVICE_UUID: user_input[CONF_DEVICE_UUID],
                CONF_SCANNER_SOURCE: self._selected_device.source,
            }
            return await self.async_step_scanner()

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

    async def async_step_scanner(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Allow user to override the Bluetooth adapter."""
        address = self._pending_data[CONF_ADDRESS]
        scanner_options = _get_scanner_options(self.hass, address)

        # Skip this step if only one option (auto)
        if len(scanner_options) <= 2 and user_input is None:
            user_input = {CONF_SCANNER_SOURCE: self._pending_data.get(CONF_SCANNER_SOURCE, SCANNER_SOURCE_AUTO)}

        if user_input is not None:
            source = user_input[CONF_SCANNER_SOURCE]
            self._pending_data[CONF_SCANNER_SOURCE] = None if source == SCANNER_SOURCE_AUTO else source
            title = self._pending_data.pop(CONF_NAME, None) or f"ZeroBreeze {address[-5:]}"
            return self.async_create_entry(title=title, data=self._pending_data)

        pre_selected = self._pending_data.get(CONF_SCANNER_SOURCE, SCANNER_SOURCE_AUTO)
        return self.async_show_form(
            step_id="scanner",
            data_schema=vol.Schema({
                vol.Required(CONF_SCANNER_SOURCE, default=pre_selected): vol.In(scanner_options),
            }),
            description_placeholders={"address": address},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle user-initiated config flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            address = user_input[CONF_ADDRESS]

            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()

            device_info = self._discovered_devices.get(address)
            self._pending_data = {
                CONF_ADDRESS: address,
                CONF_NAME: device_info.name if device_info else f"ZeroBreeze {address[-5:]}",
                CONF_LOGIN_KEY: user_input[CONF_LOGIN_KEY],
                CONF_DEVICE_UUID: user_input[CONF_DEVICE_UUID],
                CONF_SCANNER_SOURCE: SCANNER_SOURCE_AUTO,
            }
            return await self.async_step_scanner()

        # Discover ZeroBreeze devices
        self._discovered_devices = {}
        for discovery_info in async_discovered_service_info(self.hass):
            if SERVICE_UUID.lower() in [s.lower() for s in discovery_info.service_uuids]:
                self._discovered_devices[discovery_info.address] = discovery_info

        if not self._discovered_devices:
            return self.async_abort(reason="no_devices_found")

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


class ZeroBreezeOptionsFlow(config_entries.OptionsFlow):
    """Handle options for ZeroBreeze AC."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage ZeroBreeze options."""
        address = self.config_entry.data[CONF_ADDRESS]
        scanner_options = _get_scanner_options(self.hass, address)
        current_source = (
            self.config_entry.options.get(CONF_SCANNER_SOURCE)
            or self.config_entry.data.get(CONF_SCANNER_SOURCE)
            or SCANNER_SOURCE_AUTO
        )

        if user_input is not None:
            source = user_input[CONF_SCANNER_SOURCE]
            return self.async_create_entry(
                data={CONF_SCANNER_SOURCE: None if source == SCANNER_SOURCE_AUTO else source}
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_SCANNER_SOURCE, default=current_source): vol.In(scanner_options),
            }),
        )
