"""AES-256-CBC encryption, zero-padding, and Manchester RMT wire framing."""

from __future__ import annotations

import hashlib
import os

from Crypto.Cipher import AES

_STUFF_MAP: dict[int, tuple[int, int]] = {
    0x1C: (0x1B, 0x01),
    0x1B: (0x1B, 0x02),
    0x1D: (0x1B, 0x03),
}

_UNSTUFF_MAP: dict[int, int] = {
    0x01: 0x1C,
    0x02: 0x1B,
    0x03: 0x1D,
}


def derive_aes256_key(password: str | bytes) -> bytes:
    """Derive 32-byte AES-256 key from UTF-8 password via unsalted SHA-256."""
    pwd_bytes = password.encode("utf-8") if isinstance(password, str) else password
    return hashlib.sha256(pwd_bytes).digest()


def zero_pad_16(data: bytes) -> tuple[bytes, int]:
    """Zero-pad plaintext to a 16-byte multiple without adding an extra block when aligned."""
    rem = len(data) % 16
    if rem == 0:
        return data, 0
    pad_len = 16 - rem
    return data + (b"\x00" * pad_len), pad_len


def zero_unpad(data: bytes, strip_legacy_x10: bool = True) -> bytes:
    """Strip trailing 0x00 bytes (and optionally legacy 0x10/0x0A bytes)."""
    res = data.rstrip(b"\x00")
    if strip_legacy_x10:
        res = res.rstrip(b"\x10").rstrip(b"\x0a").rstrip(b"\x00")
    return res


def encrypt_lnk2_envelope(
    plaintext: str | bytes,
    password: str,
    iv: bytes | None = None,
    sha256_over_padded: bool = False,
) -> bytes:
    """Encrypt plaintext into the 48-byte header + AES-256-CBC binary envelope."""
    raw = plaintext.encode("utf-8") if isinstance(plaintext, str) else plaintext
    padded, _ = zero_pad_16(raw)
    iv_bytes = iv if iv is not None else os.urandom(16)
    key = derive_aes256_key(password)
    cipher = AES.new(key, AES.MODE_CBC, iv_bytes)
    ciphertext = cipher.encrypt(padded)
    digest_source = padded if sha256_over_padded else raw
    digest = hashlib.sha256(digest_source).digest()
    return digest + iv_bytes + ciphertext


def decrypt_lnk2_envelope(packet: bytes, password: str) -> tuple[bool, bytes | None]:
    """Decrypt and verify a LNK2 AES-256-CBC binary envelope."""
    if len(packet) < 48 or (len(packet) - 48) % 16 != 0:
        return False, None
    expected_sha256 = packet[:32]
    iv = packet[32:48]
    ciphertext = packet[48:]
    key = derive_aes256_key(password)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    decrypted_padded = cipher.decrypt(ciphertext)

    unpadded_null = decrypted_padded.rstrip(b"\x00")
    unpadded_legacy = zero_unpad(decrypted_padded, strip_legacy_x10=True)

    candidates = [unpadded_null, decrypted_padded, unpadded_legacy]
    for candidate in candidates:
        if hashlib.sha256(candidate).digest() == expected_sha256:
            return True, unpadded_legacy
    return False, None


def encode_sip_wire_frame(payload: bytes) -> bytes:
    """Encode raw SIP payload bytes into a byte-stuffed LNK2 UART/Manchester wire frame."""
    if len(payload) > 255:
        raise ValueError(f"SIP wire payload exceeds 255 bytes: {len(payload)}")
    length_byte = len(payload) & 0xFF
    checksum_byte = (length_byte + sum(payload)) & 0xFF
    body = bytes([length_byte]) + payload + bytes([checksum_byte])
    stuffed = bytearray([0xF5, 0x1C])
    for b in body:
        esc_seq = _STUFF_MAP.get(b)
        if esc_seq is not None:
            stuffed.extend(esc_seq)
        else:
            stuffed.append(b)
    stuffed.append(0x1D)
    return bytes(stuffed)


def decode_sip_wire_frame(frame: bytes) -> bytes:
    """Decode a byte-stuffed LNK2 UART/Manchester wire frame and verify its 8-bit checksum."""
    idx = 1 if (frame and frame[0] == 0xF5) else 0
    if idx >= len(frame) or frame[idx] != 0x1C:
        raise ValueError("Missing STX (0x1C) in SIP wire frame")
    idx += 1
    if frame[-1] != 0x1D:
        raise ValueError("Missing ETX (0x1D) in SIP wire frame")

    unstuffed = bytearray()
    end = len(frame) - 1
    while idx < end:
        b = frame[idx]
        if b == 0x1B:
            idx += 1
            if idx >= end:
                raise ValueError("Truncated ESC sequence in SIP wire frame")
            esc = frame[idx]
            if esc not in _UNSTUFF_MAP:
                raise ValueError(f"Invalid ESC code {esc:#x}")
            unstuffed.append(_UNSTUFF_MAP[esc])
        else:
            unstuffed.append(b)
        idx += 1

    if len(unstuffed) < 2:
        raise ValueError("Frame body too short")
    length_byte = unstuffed[0]
    payload = bytes(unstuffed[1:-1])
    checksum_byte = unstuffed[-1]
    if len(payload) != length_byte:
        raise ValueError(f"Length mismatch: expected {length_byte}, got {len(payload)}")
    expected_checksum = (length_byte + sum(payload)) & 0xFF
    if checksum_byte != expected_checksum:
        raise ValueError(
            f"Checksum mismatch: expected {expected_checksum:#x}, got {checksum_byte:#x}"
        )
    return payload


def manchester_encode_bytes(data: bytes, half_bit_ticks: int = 200) -> list[int]:
    """Encode bytes into Differential Manchester pulse durations."""
    pulses: list[int] = []
    for byte in data:
        for bit_idx in range(8):
            bit = (byte >> bit_idx) & 1
            if bit == 0:
                pulses.extend([half_bit_ticks, half_bit_ticks])
            else:
                pulses.append(half_bit_ticks * 2)
    return pulses


def manchester_decode_pulses(pulses: list[int], threshold_ticks: int = 0x187) -> bytes:
    """Decode Differential Manchester pulse durations using threshold 0x187 (391 ticks)."""
    bits: list[int] = []
    idx = 0
    while idx < len(pulses):
        p = pulses[idx]
        if p >= threshold_ticks:
            bits.append(1)
            idx += 1
        else:
            bits.append(0)
            idx += 2
    out = bytearray()
    for b_idx in range(0, len(bits) // 8 * 8, 8):
        val = 0
        for bit_idx in range(8):
            val |= (bits[b_idx + bit_idx] & 1) << bit_idx
        out.append(val)
    return bytes(out)


def pad_zero_16(data: bytes) -> bytes:
    """Zero-pad plaintext to a 16-byte multiple and return the padded bytes."""
    padded, _ = zero_pad_16(data)
    return padded


strip_stick_padding = zero_unpad
encrypt_stick_payload = encrypt_lnk2_envelope
decrypt_stick_payload = decrypt_lnk2_envelope
encode_manchester_frame = encode_sip_wire_frame
decode_manchester_frame = decode_sip_wire_frame

__all__ = [
    "decode_manchester_frame",
    "decode_sip_wire_frame",
    "decrypt_lnk2_envelope",
    "decrypt_stick_payload",
    "derive_aes256_key",
    "encode_manchester_frame",
    "encode_sip_wire_frame",
    "encrypt_lnk2_envelope",
    "encrypt_stick_payload",
    "manchester_decode_pulses",
    "manchester_encode_bytes",
    "pad_zero_16",
    "strip_stick_padding",
    "zero_pad_16",
    "zero_unpad",
]
