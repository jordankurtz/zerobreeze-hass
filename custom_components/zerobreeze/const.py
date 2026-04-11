"""Constants for ZeroBreeze AC integration."""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "zerobreeze"

# BLE UUIDs
SERVICE_UUID: Final = "0000fd50-0000-1000-8000-00805f9b34fb"
WRITE_CHAR_UUID: Final = "00000001-0000-1001-8001-00805f9b07d0"
NOTIFY_CHAR_UUID: Final = "00000002-0000-1001-8001-00805f9b07d0"

# Tuya BLE Protocol Commands
CMD_AUTH: Final = 0x04
CMD_CONTROL: Final = 0x05
CMD_RESPONSE_OFFSET: Final = 0x40

# Tuya BLE Protocol Function Codes
FUNC_SENDER_DPS_V4: Final = 0x0027

# Data Point IDs
DP_POWER: Final = 1
DP_MODE_READ: Final = 4
DP_SET_TEMP_C: Final = 5
DP_SET_TEMP_F: Final = 6
DP_MODE_WRITE: Final = 7
DP_TEMP_UNIT: Final = 8
DP_FAN_SPEED: Final = 9
DP_HUMIDITY_SET: Final = 101
DP_OUTPUT_TEMP_C: Final = 107
DP_ROOM_TEMP_C: Final = 108
DP_EXHAUST_TEMP_F: Final = 110
DP_COMPRESSOR_FREQ: Final = 114
DP_MANUAL_DRAIN: Final = 118
DP_HUMIDITY: Final = 123
DP_ROOM_TEMP_F: Final = 125
DP_OUTPUT_TEMP_F: Final = 126

# Data Point Types
DP_TYPE_BOOL: Final = 0x01
DP_TYPE_VALUE: Final = 0x02
DP_TYPE_ENUM: Final = 0x04

# Mode values (for DP 4/7)
MODE_ROCKET: Final = 0x00  # Strong cold / Boost
MODE_COOL: Final = 0x01
MODE_SLEEP: Final = 0x02
MODE_FAN: Final = 0x03
MODE_DRY: Final = 0x04
MODE_ECO: Final = 0x05
MODE_HEAT: Final = 0x06
MODE_OFF: Final = 0x07

# Fan speed values (for DP 9)
FAN_SPEED_1: Final = 0x00
FAN_SPEED_2: Final = 0x01
FAN_SPEED_3: Final = 0x02
FAN_SPEED_4: Final = 0x03

# Temperature range (Fahrenheit)
MIN_TEMP_F: Final = 61
MAX_TEMP_F: Final = 82

# Configuration keys
CONF_LOGIN_KEY: Final = "login_key"
CONF_DEVICE_UUID: Final = "device_uuid"
CONF_SCANNER_SOURCE: Final = "scanner_source"

# Update interval
UPDATE_INTERVAL: Final = 30  # seconds

# Manufacturer name
MANUFACTURER: Final = "ZeroBreeze"
MODEL: Final = "Mark 3"
