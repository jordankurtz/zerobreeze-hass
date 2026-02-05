"""Tuya BLE P1 protocol implementation."""
from __future__ import annotations

import logging
import struct
from dataclasses import dataclass
from typing import Any, Final

from .crypto import TuyaBLECrypto, crc16
from ..const import (
    CMD_AUTH,
    CMD_CONTROL,
    CMD_RESPONSE_OFFSET,
    DP_TYPE_BOOL,
    DP_TYPE_ENUM,
    DP_TYPE_VALUE,
    FUNC_SENDER_DPS_V4,
)

# Additional function codes
FUNC_SENDER_PAIR: Final = 0x0001  # Registration
FUNC_SENDER_DEVICE_STATUS: Final = 0x0003  # Status request

_LOGGER = logging.getLogger(__name__)


@dataclass
class DataPoint:
    """Represents a Tuya datapoint."""

    dp_id: int
    dp_type: int
    value: int | bool

    def encode(self) -> bytes:
        """Encode datapoint to bytes."""
        if self.dp_type == DP_TYPE_BOOL:
            value_bytes = bytes([1 if self.value else 0])
        elif self.dp_type == DP_TYPE_ENUM:
            value_bytes = bytes([self.value & 0xFF])
        else:  # DP_TYPE_VALUE - 4 byte big-endian
            value_bytes = struct.pack(">I", self.value & 0xFFFFFFFF)

        return bytes([self.dp_id, self.dp_type]) + struct.pack(">H", len(value_bytes)) + value_bytes

    @classmethod
    def decode(cls, data: bytes, offset: int = 0) -> tuple[DataPoint, int]:
        """Decode datapoint from bytes, return (DataPoint, bytes_consumed)."""
        dp_id = data[offset]
        dp_type = data[offset + 1]
        length = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
        value_bytes = data[offset + 4 : offset + 4 + length]

        if dp_type == DP_TYPE_BOOL:
            value = bool(value_bytes[0]) if value_bytes else False
        elif dp_type == DP_TYPE_ENUM:
            value = value_bytes[0] if value_bytes else 0
        else:  # DP_TYPE_VALUE
            if length == 4:
                value = struct.unpack(">I", value_bytes)[0]
            elif length == 2:
                value = struct.unpack(">H", value_bytes)[0]
            elif length == 1:
                value = value_bytes[0]
            else:
                value = int.from_bytes(value_bytes, "big")

        return cls(dp_id=dp_id, dp_type=dp_type, value=value), 4 + length


class TuyaBLEProtocol:
    """Handles Tuya BLE packet encoding and decoding."""

    def __init__(self, login_key: str, device_uuid: str) -> None:
        """Initialize protocol with login key and device UUID."""
        self._login_key = login_key
        self._device_uuid = device_uuid
        self._auth_key = TuyaBLECrypto.derive_auth_key(login_key)
        self._session_key: bytes | None = None
        self._seq: int = 0
        self._dp_counter: int = 0
        self._authenticated = False

    @property
    def is_authenticated(self) -> bool:
        """Return True if session key is established."""
        return self._authenticated and self._session_key is not None

    def build_auth_packet(self) -> bytes:
        """
        Build authentication packet (cmd=0x04).

        Format: [0x00] [length] [0x20] [cmd] [IV 16B] [encrypted payload]

        Payload format (16 bytes):
        - Sequence (4 bytes BE)
        - Type = 0 (4 bytes)
        - Internal command = 0x00000002 (4 bytes)
        - Fixed challenge = 0x00f3784e (4 bytes)
        """
        self._seq += 1

        # Build payload (16 bytes)
        payload = struct.pack(">I", self._seq)  # Sequence
        payload += struct.pack(">I", 0)  # Type = 0
        payload += struct.pack(">I", 0x02)  # Internal command = 0x00000002
        payload += bytes([0x00, 0xf3, 0x78, 0x4e])  # Fixed challenge

        iv, ciphertext = TuyaBLECrypto.encrypt(payload, self._auth_key)

        length = 1 + 16 + len(ciphertext)
        packet = bytes([0x00, length, 0x20, CMD_AUTH]) + iv + ciphertext

        _LOGGER.debug("Built auth packet: %s", packet.hex())
        return packet

    def parse_auth_response(self, data: bytes) -> bool:
        """
        Parse authentication response and extract srand.

        Response format: [0x00] [length] [frag/seq] [cmd] [secFlag] [IV 16B] [encrypted]
        srand is at offset 18 in decrypted payload (6 bytes).
        """
        if len(data) < 22:
            _LOGGER.error("Auth response too short: %d bytes", len(data))
            return False

        cmd = data[3]
        if cmd != (CMD_RESPONSE_OFFSET + CMD_AUTH):
            _LOGGER.error("Unexpected auth response cmd: 0x%02x", cmd)
            return False

        # Extract IV (at offset 5 for auth response - has secFlag byte)
        iv = data[5:21]
        ciphertext = data[21:]

        try:
            decrypted = TuyaBLECrypto.decrypt(ciphertext, self._auth_key, iv)
            _LOGGER.debug("Auth response decrypted: %s", decrypted.hex())

            # Extract srand at offset 18 (6 bytes)
            if len(decrypted) < 24:
                _LOGGER.error("Decrypted auth response too short")
                return False

            srand = decrypted[18:24]
            _LOGGER.debug("Extracted srand: %s", srand.hex())

            # Derive session key
            self._session_key = TuyaBLECrypto.derive_session_key(self._login_key, srand)
            self._authenticated = True
            _LOGGER.info("Authentication successful, session key derived")
            return True

        except Exception as e:
            _LOGGER.error("Failed to decrypt auth response: %s", e)
            return False

    def build_registration_packet(self) -> bytes:
        """
        Build registration packet (cmd=0x05, func=0x0001).

        Sent after auth to complete session setup.
        Data: UUID (16) + login_key (6) + padding (24)
        """
        if not self._session_key:
            raise RuntimeError("Not authenticated - cannot send registration")

        self._seq += 1

        # Build data: UUID (16) + login_key (6) + padding (24)
        data = bytearray()

        # UUID as ASCII (16 bytes, zero-padded)
        uuid_bytes = self._device_uuid.encode("ascii")[:16]
        data.extend(uuid_bytes)
        data.extend(b"\x00" * (16 - len(uuid_bytes)))

        # Login key (6 bytes)
        key_bytes = self._login_key.encode("ascii")[:6]
        data.extend(key_bytes)
        data.extend(b"\x00" * (6 - len(key_bytes)))

        # Padding (24 bytes)
        data.extend(b"\x00" * 24)

        # Build inner message
        inner_msg = struct.pack(">I", self._seq)  # seq
        inner_msg += struct.pack(">I", 0)  # resp_to
        inner_msg += struct.pack(">H", FUNC_SENDER_PAIR)  # func_code = 0x0001
        inner_msg += struct.pack(">H", len(data))  # data_len
        inner_msg += bytes(data)

        # CRC
        crc = crc16(inner_msg)
        inner_msg += struct.pack(">H", crc)

        # Encrypt with session key
        iv, ciphertext = TuyaBLECrypto.encrypt(inner_msg, self._session_key)

        # Build packet
        length = 1 + 16 + len(ciphertext)
        packet = bytes([0x00, length, 0x20, CMD_CONTROL]) + iv + ciphertext

        _LOGGER.debug("Built registration packet: %s", packet.hex())
        return packet

    def build_status_request_packet(self) -> bytes:
        """
        Build status request packet (cmd=0x05, func=0x0003).

        Requests current device state after registration.
        """
        if not self._session_key:
            raise RuntimeError("Not authenticated - cannot request status")

        self._seq += 1

        # Build inner message (no data for status request)
        inner_msg = struct.pack(">I", self._seq)  # seq
        inner_msg += struct.pack(">I", 0)  # resp_to
        inner_msg += struct.pack(">H", FUNC_SENDER_DEVICE_STATUS)  # func_code = 0x0003
        inner_msg += struct.pack(">H", 0)  # data_len = 0

        # CRC
        crc = crc16(inner_msg)
        inner_msg += struct.pack(">H", crc)

        # Encrypt with session key
        iv, ciphertext = TuyaBLECrypto.encrypt(inner_msg, self._session_key)

        # Build packet
        length = 1 + 16 + len(ciphertext)
        packet = bytes([0x00, length, 0x20, CMD_CONTROL]) + iv + ciphertext

        _LOGGER.debug("Built status request packet: %s", packet.hex())
        return packet

    def build_control_packet(self, datapoints: list[DataPoint]) -> bytes:
        """
        Build control packet (cmd=0x05) with datapoints.

        Inner message format:
        [seq 4B BE] [resp_to 4B BE] [func_code 2B BE] [data_len 2B BE] [data...] [crc 2B BE]

        Data format (senderDpsV4):
        [padding 4B] [counter 1B] [dp1...] [dp2...]
        """
        if not self._session_key:
            raise RuntimeError("Not authenticated - call build_auth_packet first")

        self._seq += 1
        self._dp_counter += 1

        # Build DP data
        dp_data = bytes(4)  # 4 bytes padding
        dp_data += bytes([self._dp_counter & 0xFF])
        for dp in datapoints:
            dp_data += dp.encode()

        # Build inner message (before CRC)
        inner_msg = struct.pack(">I", self._seq)  # seq
        inner_msg += struct.pack(">I", 0)  # resp_to
        inner_msg += struct.pack(">H", FUNC_SENDER_DPS_V4)  # func_code
        inner_msg += struct.pack(">H", len(dp_data))  # data_len
        inner_msg += dp_data

        # Calculate and append CRC
        crc = crc16(inner_msg)
        inner_msg += struct.pack(">H", crc)

        # Encrypt
        iv, ciphertext = TuyaBLECrypto.encrypt(inner_msg, self._session_key)

        # Build packet
        length = 1 + 16 + len(ciphertext)
        packet = bytes([0x00, length, 0x20, CMD_CONTROL]) + iv + ciphertext

        _LOGGER.debug("Built control packet: %s", packet.hex())
        return packet

    def parse_status_notification(self, data: bytes) -> dict[int, Any]:
        """
        Parse status notification (cmd=0x05 response).

        Notification format: [0x00] [length] [seq] [cmd] [IV 16B] [encrypted]
        (No secFlag byte for status notifications)

        Decrypted format:
        [seq 4B BE] [type 4B BE] [inner_cmd 4B BE] [DP data...]

        DP data (at offset ~19 from decrypted start):
        [flags 4B] [counter 3B] [dpId 1B] [dpType 1B] [len 2B BE] [value N B] [crc 2B]
        """
        if len(data) < 21:
            _LOGGER.debug("Status notification too short: %d bytes", len(data))
            return {}

        cmd = data[3]
        if cmd != CMD_CONTROL:
            _LOGGER.debug("Not a status notification, cmd=0x%02x", cmd)
            return {}

        if not self._session_key:
            _LOGGER.warning("Cannot parse status - not authenticated")
            return {}

        # For status notifications, IV is at offset 4 (no secFlag)
        iv = data[4:20]
        ciphertext = data[20:]

        try:
            decrypted = TuyaBLECrypto.decrypt(ciphertext, self._session_key, iv)
            _LOGGER.debug("Status decrypted: %s", decrypted.hex())

            # Parse datapoints from decrypted payload
            # Skip header: seq(4) + type(4) + inner_cmd(4) = 12 bytes
            # Then flags(4) + counter(3) = 7 bytes
            # DP starts at offset 19
            return self._parse_dp_payload(decrypted)

        except Exception as e:
            _LOGGER.error("Failed to decrypt status notification: %s", e)
            return {}

    def _parse_dp_payload(self, decrypted: bytes) -> dict[int, Any]:
        """Parse datapoints from decrypted status payload."""
        result: dict[int, Any] = {}

        # DP starts at offset 19 (after header + flags + counter)
        offset = 19
        if len(decrypted) <= offset:
            return result

        try:
            while offset + 4 <= len(decrypted):
                dp_id = decrypted[offset]
                if dp_id == 0:  # End of DPs or padding
                    break

                dp_type = decrypted[offset + 1]
                length = struct.unpack(">H", decrypted[offset + 2 : offset + 4])[0]

                if offset + 4 + length > len(decrypted):
                    break

                value_bytes = decrypted[offset + 4 : offset + 4 + length]

                if dp_type == DP_TYPE_BOOL:
                    value = bool(value_bytes[0]) if value_bytes else False
                elif dp_type == DP_TYPE_ENUM:
                    value = value_bytes[0] if value_bytes else 0
                else:  # DP_TYPE_VALUE
                    if length == 4:
                        value = struct.unpack(">I", value_bytes)[0]
                    elif length == 2:
                        value = struct.unpack(">H", value_bytes)[0]
                    elif length == 1:
                        value = value_bytes[0]
                    else:
                        value = int.from_bytes(value_bytes, "big")

                result[dp_id] = value
                _LOGGER.debug("Parsed DP %d (type=%d): %s", dp_id, dp_type, value)

                offset += 4 + length

        except Exception as e:
            _LOGGER.warning("Error parsing DP payload at offset %d: %s", offset, e)

        return result

    def parse_response(self, data: bytes) -> dict[int, Any]:
        """
        Parse any response packet and extract datapoints if present.

        Handles both auth responses (cmd=0x44) and control responses (cmd=0x45).
        """
        if len(data) < 4:
            return {}

        cmd = data[3]

        # Control response (cmd=0x45)
        if cmd == CMD_RESPONSE_OFFSET + CMD_CONTROL:
            return self._parse_control_response(data)

        return {}

    def _parse_control_response(self, data: bytes) -> dict[int, Any]:
        """Parse control response (cmd=0x45)."""
        if len(data) < 22 or not self._session_key:
            return {}

        # Control response has secFlag, so IV at offset 5
        iv = data[5:21]
        ciphertext = data[21:]

        try:
            decrypted = TuyaBLECrypto.decrypt(ciphertext, self._session_key, iv)
            _LOGGER.debug("Control response decrypted: %s", decrypted.hex())
            return self._parse_dp_payload(decrypted)
        except Exception as e:
            _LOGGER.error("Failed to decrypt control response: %s", e)
            return {}

    def reset(self) -> None:
        """Reset protocol state (for reconnection)."""
        self._session_key = None
        self._authenticated = False
        self._seq = 0
        # Don't reset dp_counter - device may expect it to keep incrementing
