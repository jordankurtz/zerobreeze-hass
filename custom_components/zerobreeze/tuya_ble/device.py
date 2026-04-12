"""ZeroBreeze device abstraction."""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

from bleak import BleakClient
from bleak.exc import BleakError

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import async_scanner_devices_by_address
from homeassistant.core import HomeAssistant

from .protocol import TuyaBLEProtocol, DataPoint
from ..const import (
    SERVICE_UUID,
    WRITE_CHAR_UUID,
    NOTIFY_CHAR_UUID,
    DP_POWER,
    DP_MODE_WRITE,
    DP_SET_TEMP_F,
    DP_FAN_SPEED,
    DP_MANUAL_DRAIN,
    DP_TYPE_BOOL,
    DP_TYPE_ENUM,
    DP_TYPE_VALUE,
    DP_ROOM_TEMP_F,
    DP_OUTPUT_TEMP_F,
    DP_EXHAUST_TEMP_F,
    DP_HUMIDITY,
    DP_COMPRESSOR_FREQ,
    DP_MODE_READ,
    MODE_OFF,
)

_LOGGER = logging.getLogger(__name__)

BLE_TIMEOUT = 10.0
AUTH_TIMEOUT = 5.0


class ZeroBreezeDevice:
    """Represents a ZeroBreeze AC device."""

    def __init__(
        self,
        hass: HomeAssistant,
        address: str,
        login_key: str,
        device_uuid: str,
        name: str | None = None,
        scanner_source: str | None = None,
    ) -> None:
        """Initialize device."""
        self._hass = hass
        self._address = address
        self._scanner_source = scanner_source
        self._name = name or f"ZeroBreeze {address[-5:].replace(':', '')}"
        self._protocol = TuyaBLEProtocol(login_key, device_uuid)
        self._client: BleakClient | None = None
        self._lock = asyncio.Lock()
        self._connected = False
        self._auth_event = asyncio.Event()
        self._response_event = asyncio.Event()
        self._last_response: dict[int, Any] = {}
        self._state: dict[int, Any] = {}
        self._state_callbacks: list[Callable[[dict[int, Any]], None]] = []

    @property
    def address(self) -> str:
        """Return device address."""
        return self._address

    @property
    def name(self) -> str:
        """Return device name."""
        return self._name

    @property
    def connected(self) -> bool:
        """Return True if connected and authenticated."""
        return self._connected and self._protocol.is_authenticated

    @property
    def state(self) -> dict[int, Any]:
        """Return current device state (DP values)."""
        return self._state.copy()

    def _get_ble_device(self):
        """Return a BLEDevice for the configured scanner, or best available."""
        if self._scanner_source:
            for scanner_device in async_scanner_devices_by_address(
                self._hass, self._address, connectable=True
            ):
                if scanner_device.scanner.source == self._scanner_source:
                    return scanner_device.ble_device
            _LOGGER.warning(
                "Configured scanner %s cannot see %s, falling back to best available",
                self._scanner_source,
                self._address,
            )
        return bluetooth.async_ble_device_from_address(
            self._hass, self._address, connectable=True
        )

    def register_callback(self, callback: Callable[[dict[int, Any]], None]) -> Callable[[], None]:
        """Register callback for state updates. Returns unregister function."""
        self._state_callbacks.append(callback)
        return lambda: self._state_callbacks.remove(callback)

    async def connect(self) -> bool:
        """Connect to device and authenticate."""
        async with self._lock:
            if self._connected:
                return True

            try:
                _LOGGER.info("Connecting to %s", self._address)

                ble_device = self._get_ble_device()
                if ble_device is None:
                    _LOGGER.error(
                        "Device %s not found via Bluetooth scanner", self._address
                    )
                    return False

                self._client = BleakClient(
                    ble_device,
                    disconnected_callback=self._on_disconnect,
                    services=[SERVICE_UUID],
                    dangerous_use_bleak_cache=True,
                )
                await self._client.connect(timeout=BLE_TIMEOUT)
                _LOGGER.debug("BLE connected, starting notifications")

                # Start notifications
                await self._client.start_notify(NOTIFY_CHAR_UUID, self._on_notification)

                # Authenticate
                self._auth_event.clear()
                auth_packet = self._protocol.build_auth_packet()
                await self._client.write_gatt_char(WRITE_CHAR_UUID, auth_packet)

                # Wait for auth response
                try:
                    await asyncio.wait_for(self._auth_event.wait(), AUTH_TIMEOUT)
                except asyncio.TimeoutError:
                    _LOGGER.error("Authentication timeout")
                    await self.disconnect()
                    return False

                if not self._protocol.is_authenticated:
                    _LOGGER.error("Authentication failed")
                    await self.disconnect()
                    return False

                # Send registration packet
                _LOGGER.debug("Sending registration packet")
                reg_packet = self._protocol.build_registration_packet()
                await self._client.write_gatt_char(WRITE_CHAR_UUID, reg_packet)
                await asyncio.sleep(0.1)  # Small delay between packets

                # Send status request
                _LOGGER.debug("Sending status request")
                status_packet = self._protocol.build_status_request_packet()
                await self._client.write_gatt_char(WRITE_CHAR_UUID, status_packet)

                self._connected = True
                _LOGGER.info("Connected and authenticated to %s", self._address)
                return True

            except BleakError as e:
                _LOGGER.error("Failed to connect to %s: %s", self._address, e)
                await self.disconnect()
                return False

    async def disconnect(self) -> None:
        """Disconnect from device."""
        self._connected = False
        self._protocol.reset()

        if self._client:
            try:
                await self._client.disconnect()
            except BleakError:
                pass
            self._client = None

    def _on_disconnect(self, client: BleakClient) -> None:
        """Handle disconnection."""
        _LOGGER.info("Disconnected from %s", self._address)
        self._connected = False
        self._protocol.reset()

    def _on_notification(self, sender: int, data: bytearray) -> None:
        """Handle incoming BLE notifications."""
        _LOGGER.debug("Notification from %s: %s", sender, data.hex())

        data_bytes = bytes(data)
        if len(data_bytes) < 4:
            return

        cmd = data_bytes[3]

        # Auth response (0x44)
        if cmd == 0x44:
            if self._protocol.parse_auth_response(data_bytes):
                self._auth_event.set()
            return

        # Control response (0x45)
        if cmd == 0x45:
            dps = self._protocol.parse_response(data_bytes)
            if dps:
                self._last_response = dps
                self._update_state(dps)
            self._response_event.set()
            return

        # Status notification (0x05)
        if cmd == 0x05:
            dps = self._protocol.parse_status_notification(data_bytes)
            if dps:
                self._update_state(dps)
            return

    def _update_state(self, dps: dict[int, Any]) -> None:
        """Update internal state and notify callbacks."""
        self._state.update(dps)
        _LOGGER.debug("State updated: %s", self._state)

        for callback in self._state_callbacks:
            try:
                callback(self._state)
            except Exception as e:
                _LOGGER.error("State callback error: %s", e)

    async def _send_command(self, datapoints: list[DataPoint]) -> bool:
        """Send control command with datapoints."""
        if not self._connected or not self._client:
            _LOGGER.error("Not connected")
            return False

        async with self._lock:
            try:
                self._response_event.clear()
                packet = self._protocol.build_control_packet(datapoints)
                await self._client.write_gatt_char(WRITE_CHAR_UUID, packet)

                # Wait for response
                try:
                    await asyncio.wait_for(self._response_event.wait(), BLE_TIMEOUT)
                except asyncio.TimeoutError:
                    _LOGGER.warning("Command response timeout")
                    # Command may still have worked

                return True

            except BleakError as e:
                _LOGGER.error("Failed to send command: %s", e)
                return False

    # High-level control methods

    async def set_power(self, on: bool) -> bool:
        """Turn device on or off."""
        return await self._send_command([
            DataPoint(DP_POWER, DP_TYPE_BOOL, on)
        ])

    async def set_mode(self, mode: int) -> bool:
        """Set device mode."""
        return await self._send_command([
            DataPoint(DP_MODE_WRITE, DP_TYPE_ENUM, mode)
        ])

    async def set_temperature(self, temp_f: int, mode: int | None = None) -> bool:
        """Set target temperature (Fahrenheit)."""
        dps = [DataPoint(DP_SET_TEMP_F, DP_TYPE_VALUE, temp_f)]
        if mode is not None:
            dps.insert(0, DataPoint(DP_MODE_WRITE, DP_TYPE_ENUM, mode))
        return await self._send_command(dps)

    async def set_fan_speed(self, speed: int) -> bool:
        """Set fan speed (0-3)."""
        return await self._send_command([
            DataPoint(DP_FAN_SPEED, DP_TYPE_ENUM, speed)
        ])

    async def set_mode_and_temperature(self, mode: int, temp_f: int) -> bool:
        """Set mode and temperature together (as app does)."""
        return await self._send_command([
            DataPoint(DP_MODE_WRITE, DP_TYPE_ENUM, mode),
            DataPoint(DP_SET_TEMP_F, DP_TYPE_VALUE, temp_f),
        ])

    async def trigger_drain(self) -> bool:
        """Trigger manual drain cycle."""
        return await self._send_command([
            DataPoint(DP_MANUAL_DRAIN, DP_TYPE_BOOL, True)
        ])

    # State getters

    @property
    def is_on(self) -> bool:
        """Return True if device is powered on."""
        return bool(self._state.get(DP_POWER, False))

    @property
    def mode(self) -> int:
        """Return current mode."""
        return self._state.get(DP_MODE_READ, MODE_OFF)

    @property
    def target_temperature_f(self) -> int | None:
        """Return target temperature in Fahrenheit."""
        return self._state.get(DP_SET_TEMP_F)

    @property
    def room_temperature_f(self) -> float | None:
        """Return room temperature in Fahrenheit."""
        return self._state.get(DP_ROOM_TEMP_F)

    @property
    def output_temperature_f(self) -> float | None:
        """Return output temperature in Fahrenheit."""
        return self._state.get(DP_OUTPUT_TEMP_F)

    @property
    def exhaust_temperature_f(self) -> float | None:
        """Return exhaust temperature in Fahrenheit."""
        return self._state.get(DP_EXHAUST_TEMP_F)

    @property
    def humidity(self) -> int | None:
        """Return current humidity percentage."""
        return self._state.get(DP_HUMIDITY)

    @property
    def compressor_frequency(self) -> int | None:
        """Return compressor frequency in Hz."""
        return self._state.get(DP_COMPRESSOR_FREQ)

    @property
    def fan_speed(self) -> int:
        """Return current fan speed (0-3)."""
        return self._state.get(DP_FAN_SPEED, 0)
