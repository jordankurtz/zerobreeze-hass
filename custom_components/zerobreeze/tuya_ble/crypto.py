"""Tuya BLE cryptographic functions."""
from __future__ import annotations

import hashlib
import os
from typing import Final

from Crypto.Cipher import AES

BLOCK_SIZE: Final = 16


class TuyaBLECrypto:
    """Handles Tuya BLE AES-128-CBC encryption/decryption."""

    @staticmethod
    def md5_hex(data: str | bytes) -> str:
        """Compute MD5 hash and return as hex string."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.md5(data).hexdigest()

    @staticmethod
    def md5_bytes(data: str | bytes) -> bytes:
        """Compute MD5 hash and return as bytes."""
        if isinstance(data, str):
            data = data.encode("utf-8")
        return hashlib.md5(data).digest()

    @staticmethod
    def derive_auth_key(login_key: str) -> bytes:
        """Derive auth key from login key (MD5 of login_key as hex bytes)."""
        hex_str = TuyaBLECrypto.md5_hex(login_key)
        return bytes.fromhex(hex_str)

    @staticmethod
    def derive_session_key(login_key: str, srand: bytes) -> bytes:
        """Derive session key from login key and srand."""
        combined = login_key.encode("utf-8") + srand
        return TuyaBLECrypto.md5_bytes(combined)

    @staticmethod
    def pad(data: bytes) -> bytes:
        """Pad data to 16-byte boundary with zeros."""
        pad_len = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
        if pad_len == BLOCK_SIZE:
            return data
        return data + b"\x00" * pad_len

    @staticmethod
    def encrypt(plaintext: bytes, key: bytes, iv: bytes | None = None) -> tuple[bytes, bytes]:
        """
        Encrypt data with AES-128-CBC.

        Returns (iv, ciphertext) tuple.
        """
        if iv is None:
            iv = os.urandom(BLOCK_SIZE)
        padded = TuyaBLECrypto.pad(plaintext)
        cipher = AES.new(key, AES.MODE_CBC, iv)
        ciphertext = cipher.encrypt(padded)
        return iv, ciphertext

    @staticmethod
    def decrypt(ciphertext: bytes, key: bytes, iv: bytes) -> bytes:
        """Decrypt data with AES-128-CBC."""
        cipher = AES.new(key, AES.MODE_CBC, iv)
        return cipher.decrypt(ciphertext)


def crc16(data: bytes, init: int = 0xFFFF) -> int:
    """
    Calculate CRC-16 (XMODEM variant).

    Polynomial: 0xA001 (reversed 0x8005)
    """
    crc = init
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF
