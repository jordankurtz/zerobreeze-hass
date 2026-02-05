"""BLE connection coordinator for ZeroBreeze."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Any

from homeassistant.components import bluetooth
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, UPDATE_INTERVAL
from .tuya_ble import ZeroBreezeDevice

_LOGGER = logging.getLogger(__name__)


class ZeroBreezeCoordinator(DataUpdateCoordinator[dict[int, Any]]):
    """Coordinator to manage BLE connection and data updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        device: ZeroBreezeDevice,
    ) -> None:
        """Initialize coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{device.address}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.device = device
        self._reconnect_task: asyncio.Task | None = None
        self._unregister_callback: callable | None = None

    async def async_setup(self) -> bool:
        """Set up the coordinator."""
        # Register for state updates from device
        self._unregister_callback = self.device.register_callback(self._on_device_state_update)

        # Initial connection
        if not await self.device.connect():
            _LOGGER.error("Failed initial connection to %s", self.device.address)
            return False

        return True

    async def async_shutdown(self) -> None:
        """Shutdown coordinator."""
        if self._unregister_callback:
            self._unregister_callback()

        if self._reconnect_task:
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        await self.device.disconnect()

    @callback
    def _on_device_state_update(self, state: dict[int, Any]) -> None:
        """Handle device state updates."""
        self.async_set_updated_data(state)

    async def _async_update_data(self) -> dict[int, Any]:
        """Fetch data from device (reconnect if needed)."""
        if not self.device.connected:
            _LOGGER.debug("Device disconnected, attempting reconnect")
            if not await self.device.connect():
                raise UpdateFailed("Failed to reconnect to device")

        return self.device.state

    async def async_ensure_connected(self) -> bool:
        """Ensure device is connected."""
        if self.device.connected:
            return True
        return await self.device.connect()

    # Proxy methods for device control

    async def async_set_power(self, on: bool) -> bool:
        """Turn device on/off."""
        if not await self.async_ensure_connected():
            return False
        return await self.device.set_power(on)

    async def async_set_mode(self, mode: int) -> bool:
        """Set device mode."""
        if not await self.async_ensure_connected():
            return False
        return await self.device.set_mode(mode)

    async def async_set_temperature(self, temp_f: int, mode: int | None = None) -> bool:
        """Set target temperature."""
        if not await self.async_ensure_connected():
            return False
        return await self.device.set_temperature(temp_f, mode)

    async def async_set_fan_speed(self, speed: int) -> bool:
        """Set fan speed."""
        if not await self.async_ensure_connected():
            return False
        return await self.device.set_fan_speed(speed)

    async def async_set_mode_and_temperature(self, mode: int, temp_f: int) -> bool:
        """Set mode and temperature together."""
        if not await self.async_ensure_connected():
            return False
        return await self.device.set_mode_and_temperature(mode, temp_f)

    async def async_trigger_drain(self) -> bool:
        """Trigger manual drain."""
        if not await self.async_ensure_connected():
            return False
        return await self.device.trigger_drain()
