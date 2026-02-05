"""Button entity for ZeroBreeze AC."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MANUFACTURER, MODEL
from .coordinator import ZeroBreezeCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button entity from config entry."""
    coordinator: ZeroBreezeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZeroBreezeDrainButton(coordinator, entry)])


class ZeroBreezeDrainButton(ButtonEntity):
    """Button entity to trigger manual drain cycle."""

    _attr_has_entity_name = True
    _attr_name = "Manual Drain"
    _attr_icon = "mdi:water-pump"

    def __init__(
        self,
        coordinator: ZeroBreezeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize button entity."""
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.data['address']}_drain"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["address"])},
            name=coordinator.device.name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    async def async_press(self) -> None:
        """Handle button press."""
        _LOGGER.info("Triggering manual drain cycle")
        await self._coordinator.async_trigger_drain()
