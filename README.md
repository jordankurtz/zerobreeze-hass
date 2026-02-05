# ZeroBreeze AC Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)

A native Home Assistant integration for the ZeroBreeze Mark 3 portable AC unit via Bluetooth Low Energy (BLE).

## Features

- **Climate Control**: Power on/off, mode selection (Cool, Heat, Dry, Fan), temperature control (61-82°F)
- **Presets**: Sleep and Boost modes (available in Cool mode)
- **Fan Speed**: 4 speeds (Low, Medium, High, Max)
- **Sensors**: Room temperature, output temperature, exhaust temperature, humidity, compressor frequency
- **Manual Drain**: Button to trigger the drain cycle

## Requirements

- Home Assistant 2024.1.0 or newer
- One of the following:
  - A Bluetooth adapter on your Home Assistant host
  - An ESPHome Bluetooth Proxy (recommended for remote placement)
- Your ZeroBreeze device credentials (see [Getting Credentials](#getting-credentials))

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots in the top right corner
3. Select "Custom repositories"
4. Add this repository URL and select "Integration" as the category
5. Click "Add"
6. Search for "ZeroBreeze" and install it
7. Restart Home Assistant

### Manual Installation

1. Download the latest release
2. Copy the `custom_components/zerobreeze` folder to your Home Assistant `config/custom_components/` directory
3. Restart Home Assistant

## Configuration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "ZeroBreeze"
4. Select your device from the discovered Bluetooth devices
5. Enter your credentials:
   - **Login Key**: First 6 characters of your Tuya `localKey`
   - **Device UUID**: 16-character Tuya device ID

## Getting Credentials

The ZeroBreeze uses Tuya's BLE protocol. You'll need to obtain two credentials:

- **Device UUID**: 16-character Tuya device identifier
- **Login Key**: First 6 characters of the Tuya `localKey`

Since the ZeroBreeze app is a white-label Tuya product, standard methods like tinytuya or the Tuya IoT Platform may not work directly. Extracting these credentials requires intercepting the app's communication with Tuya's cloud API.

If you're familiar with reverse engineering Android apps or using tools like Frida, you can extract these values from the ZeroBreeze app's API responses.

## ESPHome Bluetooth Proxy (Optional)

For better range or if your HA host lacks Bluetooth, use an ESP32 as a BLE proxy:

```yaml
esphome:
  name: zerobreeze-proxy

esp32:
  board: esp32dev
  framework:
    type: esp-idf

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

api:
  encryption:
    key: !secret api_key

esp32_ble_tracker:
  scan_parameters:
    active: true

bluetooth_proxy:
  active: true
```

## Entities

| Entity | Type | Description |
|--------|------|-------------|
| Climate | `climate` | Main AC control (mode, temperature, fan, presets) |
| Room Temperature | `sensor` | Current room temperature |
| Output Temperature | `sensor` | AC output air temperature |
| Exhaust Temperature | `sensor` | Exhaust air temperature |
| Humidity | `sensor` | Current humidity percentage |
| Compressor Frequency | `sensor` | Compressor frequency in Hz |
| Manual Drain | `button` | Trigger drain cycle |

## Troubleshooting

### Device not discovered
- Ensure the ZeroBreeze is powered on
- Check that Bluetooth is enabled on your HA host
- Try moving closer to the device or using an ESPHome Bluetooth Proxy

### Authentication timeout
- Verify your Login Key and Device UUID are correct
- The Login Key should be exactly 6 characters
- The Device UUID should be 16 characters

### Connection drops
- BLE connections can be unreliable over distance
- Consider using an ESPHome Bluetooth Proxy placed closer to the AC

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

This integration was developed through reverse engineering of the Tuya BLE protocol used by the ZeroBreeze Mark 3.
