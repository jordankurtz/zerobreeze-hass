"""ZeroBreeze AC integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_LOGIN_KEY, CONF_DEVICE_UUID, CONF_SCANNER_SOURCE, DOMAIN
from .coordinator import ZeroBreezeCoordinator
from .tuya_ble import ZeroBreezeDevice

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.CLIMATE, Platform.SENSOR, Platform.BUTTON]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ZeroBreeze AC from a config entry."""
    address = entry.data[CONF_ADDRESS]
    login_key = entry.data[CONF_LOGIN_KEY]
    device_uuid = entry.data[CONF_DEVICE_UUID]
    name = entry.data.get("name", f"ZeroBreeze {address[-5:]}")
    scanner_source = entry.options.get(CONF_SCANNER_SOURCE, entry.data.get(CONF_SCANNER_SOURCE))

    _LOGGER.info("Setting up ZeroBreeze device at %s (scanner: %s)", address, scanner_source or "auto")

    device = ZeroBreezeDevice(hass, address, login_key, device_uuid, name, scanner_source)
    coordinator = ZeroBreezeCoordinator(hass, device)

    if not await coordinator.async_setup():
        raise ConfigEntryNotReady(f"Failed to connect to ZeroBreeze at {address}")

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update — reload so the new scanner source takes effect."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: ZeroBreezeCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
