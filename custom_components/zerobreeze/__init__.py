"""ZeroBreeze AC integration for Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_LOGIN_KEY, CONF_DEVICE_UUID, DOMAIN
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

    _LOGGER.info("Setting up ZeroBreeze device at %s", address)

    # Create device
    device = ZeroBreezeDevice(address, login_key, device_uuid, name)

    # Create coordinator
    coordinator = ZeroBreezeCoordinator(hass, device)

    # Set up coordinator
    if not await coordinator.async_setup():
        raise ConfigEntryNotReady(f"Failed to connect to ZeroBreeze at {address}")

    # Store coordinator
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator: ZeroBreezeCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()

    return unload_ok
