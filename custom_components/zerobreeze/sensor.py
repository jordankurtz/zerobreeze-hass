"""Sensor entities for ZeroBreeze AC."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    DP_ROOM_TEMP_F,
    DP_OUTPUT_TEMP_F,
    DP_EXHAUST_TEMP_F,
    DP_HUMIDITY,
    DP_COMPRESSOR_FREQ,
)
from .coordinator import ZeroBreezeCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, kw_only=True)
class ZeroBreezeSensorEntityDescription(SensorEntityDescription):
    """Describes ZeroBreeze sensor entity."""

    dp_id: int
    value_fn: Callable[[Any], Any] | None = None


SENSOR_DESCRIPTIONS: tuple[ZeroBreezeSensorEntityDescription, ...] = (
    ZeroBreezeSensorEntityDescription(
        key="room_temperature",
        name="Room Temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        dp_id=DP_ROOM_TEMP_F,
    ),
    ZeroBreezeSensorEntityDescription(
        key="output_temperature",
        name="Output Temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        dp_id=DP_OUTPUT_TEMP_F,
    ),
    ZeroBreezeSensorEntityDescription(
        key="exhaust_temperature",
        name="Exhaust Temperature",
        native_unit_of_measurement=UnitOfTemperature.FAHRENHEIT,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        dp_id=DP_EXHAUST_TEMP_F,
    ),
    ZeroBreezeSensorEntityDescription(
        key="humidity",
        name="Humidity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        dp_id=DP_HUMIDITY,
    ),
    ZeroBreezeSensorEntityDescription(
        key="compressor_frequency",
        name="Compressor Frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        dp_id=DP_COMPRESSOR_FREQ,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensor entities from config entry."""
    coordinator: ZeroBreezeCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        ZeroBreezeSensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class ZeroBreezeSensor(CoordinatorEntity[ZeroBreezeCoordinator], SensorEntity):
    """Sensor entity for ZeroBreeze AC."""

    entity_description: ZeroBreezeSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZeroBreezeCoordinator,
        entry: ConfigEntry,
        description: ZeroBreezeSensorEntityDescription,
    ) -> None:
        """Initialize sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.data['address']}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["address"])},
            name=coordinator.device.name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )

    @property
    def native_value(self) -> Any:
        """Return sensor value."""
        value = self.coordinator.device.state.get(self.entity_description.dp_id)
        if value is not None and self.entity_description.value_fn:
            return self.entity_description.value_fn(value)
        return value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
