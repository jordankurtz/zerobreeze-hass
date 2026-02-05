"""Climate entity for ZeroBreeze AC."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.components.climate.const import (
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    PRESET_BOOST,
    PRESET_NONE,
    PRESET_SLEEP,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DOMAIN,
    MANUFACTURER,
    MODEL,
    MIN_TEMP_F,
    MAX_TEMP_F,
    MODE_COOL,
    MODE_DRY,
    MODE_FAN,
    MODE_HEAT,
    MODE_OFF,
    MODE_ROCKET,
    MODE_SLEEP,
    FAN_SPEED_1,
    FAN_SPEED_2,
    FAN_SPEED_3,
    FAN_SPEED_4,
    DP_POWER,
    DP_MODE_READ,
    DP_SET_TEMP_F,
    DP_FAN_SPEED,
)
from .coordinator import ZeroBreezeCoordinator

_LOGGER = logging.getLogger(__name__)

# Map ZeroBreeze modes to HVAC modes
MODE_TO_HVAC: dict[int, HVACMode] = {
    MODE_OFF: HVACMode.OFF,
    MODE_COOL: HVACMode.COOL,
    MODE_SLEEP: HVACMode.COOL,  # Sleep is a preset of cool
    MODE_ROCKET: HVACMode.COOL,  # Rocket/Boost is a preset of cool
    MODE_FAN: HVACMode.FAN_ONLY,
    MODE_DRY: HVACMode.DRY,
    MODE_HEAT: HVACMode.HEAT,
}

# Map HVAC modes back to ZeroBreeze modes (defaults)
HVAC_TO_MODE: dict[HVACMode, int] = {
    HVACMode.OFF: MODE_OFF,
    HVACMode.COOL: MODE_COOL,
    HVACMode.FAN_ONLY: MODE_FAN,
    HVACMode.DRY: MODE_DRY,
    HVACMode.HEAT: MODE_HEAT,
}

# Fan speed mappings
FAN_SPEED_TO_NAME: dict[int, str] = {
    FAN_SPEED_1: FAN_LOW,
    FAN_SPEED_2: FAN_MEDIUM,
    FAN_SPEED_3: FAN_HIGH,
    FAN_SPEED_4: "max",
}

FAN_NAME_TO_SPEED: dict[str, int] = {v: k for k, v in FAN_SPEED_TO_NAME.items()}

# Preset mappings (only available in COOL mode)
MODE_TO_PRESET: dict[int, str] = {
    MODE_SLEEP: PRESET_SLEEP,
    MODE_ROCKET: PRESET_BOOST,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up climate entity from config entry."""
    coordinator: ZeroBreezeCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ZeroBreezeClimate(coordinator, entry)])


class ZeroBreezeClimate(CoordinatorEntity[ZeroBreezeCoordinator], ClimateEntity):
    """Climate entity for ZeroBreeze AC."""

    _attr_has_entity_name = True
    _attr_name = None  # Use device name
    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_target_temperature_step = 1
    _attr_min_temp = MIN_TEMP_F
    _attr_max_temp = MAX_TEMP_F
    _attr_hvac_modes = [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
        HVACMode.DRY,
        HVACMode.FAN_ONLY,
    ]
    _attr_fan_modes = [FAN_LOW, FAN_MEDIUM, FAN_HIGH, "max"]
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.FAN_MODE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(
        self,
        coordinator: ZeroBreezeCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize climate entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.data['address']}_climate"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["address"])},
            name=coordinator.device.name,
            manufacturer=MANUFACTURER,
            model=MODEL,
        )
        self._current_mode: int = MODE_OFF

    @property
    def hvac_mode(self) -> HVACMode:
        """Return current HVAC mode."""
        state = self.coordinator.device.state
        power = state.get(DP_POWER, False)
        if not power:
            return HVACMode.OFF

        mode = state.get(DP_MODE_READ, MODE_OFF)
        self._current_mode = mode
        return MODE_TO_HVAC.get(mode, HVACMode.OFF)

    @property
    def preset_modes(self) -> list[str] | None:
        """Return available preset modes (only in COOL mode)."""
        if self.hvac_mode == HVACMode.COOL:
            return [PRESET_NONE, PRESET_SLEEP, PRESET_BOOST]
        return None

    @property
    def preset_mode(self) -> str | None:
        """Return current preset mode."""
        if self.hvac_mode != HVACMode.COOL:
            return None

        mode = self.coordinator.device.state.get(DP_MODE_READ, MODE_OFF)
        return MODE_TO_PRESET.get(mode, PRESET_NONE)

    @property
    def target_temperature(self) -> float | None:
        """Return target temperature."""
        return self.coordinator.device.state.get(DP_SET_TEMP_F)

    @property
    def current_temperature(self) -> float | None:
        """Return current room temperature."""
        return self.coordinator.device.room_temperature_f

    @property
    def fan_mode(self) -> str | None:
        """Return current fan mode."""
        speed = self.coordinator.device.state.get(DP_FAN_SPEED, FAN_SPEED_1)
        return FAN_SPEED_TO_NAME.get(speed, FAN_LOW)

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set HVAC mode."""
        if hvac_mode == HVACMode.OFF:
            await self.coordinator.async_set_power(False)
        else:
            # Turn on if needed
            if not self.coordinator.device.is_on:
                await self.coordinator.async_set_power(True)

            # Set mode
            mode = HVAC_TO_MODE.get(hvac_mode, MODE_COOL)
            target_temp = self.target_temperature or 72
            await self.coordinator.async_set_mode_and_temperature(mode, int(target_temp))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set preset mode."""
        if preset_mode == PRESET_NONE:
            mode = MODE_COOL
        elif preset_mode == PRESET_SLEEP:
            mode = MODE_SLEEP
        elif preset_mode == PRESET_BOOST:
            mode = MODE_ROCKET
        else:
            return

        target_temp = self.target_temperature or 72
        await self.coordinator.async_set_mode_and_temperature(mode, int(target_temp))

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        # Clamp to valid range
        temp_f = max(MIN_TEMP_F, min(MAX_TEMP_F, int(temperature)))

        # Get current mode for command
        mode = self.coordinator.device.state.get(DP_MODE_READ, MODE_COOL)
        await self.coordinator.async_set_mode_and_temperature(mode, temp_f)

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set fan mode."""
        speed = FAN_NAME_TO_SPEED.get(fan_mode, FAN_SPEED_1)
        await self.coordinator.async_set_fan_speed(speed)

    async def async_turn_on(self) -> None:
        """Turn on the device."""
        await self.coordinator.async_set_power(True)

    async def async_turn_off(self) -> None:
        """Turn off the device."""
        await self.coordinator.async_set_power(False)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()
