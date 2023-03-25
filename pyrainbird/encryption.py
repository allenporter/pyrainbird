"""Libraries related to encoding and decoding requests."""

import enum
import json
import logging
import sys
import time
from typing import Any, Optional

from Crypto import Random
from Crypto.Cipher import AES
from Crypto.Hash import SHA256

from .exceptions import RainbirdApiException

BLOCK_SIZE = 16
INTERRUPT = "\x00"
PAD = "\x10"


class ErrorCode(enum.IntEnum):
    """Error codes from the device."""

    COMMAND_NOT_SUPPORTED = 0
    BAD_LENGTH = 1
    INCOMPATIBLE_DATA = 2
    CHECKSUM_ERROR = 3
    UNKNOWN = 4
    METOD_NOT_SUPPORTED = -32601


def _add_padding(data):
    new_data = data
    new_data_len = len(new_data)
    remaining_len = BLOCK_SIZE - new_data_len
    to_pad_len = remaining_len % BLOCK_SIZE
    pad_string = PAD * to_pad_len
    return "".join([new_data, pad_string])


def decrypt(encrypted_data, decrypt_key):
    iv = bytes(encrypted_data[32:48])
    encrypted_data = bytes(encrypted_data[48 : len(encrypted_data)])

    m = SHA256.new()
    m.update(to_bytes(decrypt_key))

    symmetric_key = m.digest()
    symmetric_key = symmetric_key[:32]

    aes_decryptor = AES.new(symmetric_key, AES.MODE_CBC, iv)
    return aes_decryptor.decrypt(encrypted_data)


def encrypt(data, encryptkey):
    tocodedata = data + "\x00\x10"
    m = SHA256.new()
    m.update(to_bytes(encryptkey))
    b = m.digest()
    iv = Random.new().read(16)
    c = to_bytes(_add_padding(tocodedata))
    m = SHA256.new()
    m.update(to_bytes(data))
    b2 = m.digest()

    eas_encryptor = AES.new(b, AES.MODE_CBC, iv)
    encrypteddata = eas_encryptor.encrypt(c)
    return b2 + iv + encrypteddata


def to_bytes(string):
    return to_bytes_old(string) if sys.version_info < (3, 0) else bytes(string, "UTF-8")


def to_bytes_old(string):
    return bytes(string.encode("UTF-8"))


class PayloadCoder:
    """PayloadCoder holds encoding/decoding information for the client."""

    def __init__(self, password: Optional[str], logger: logging.Logger):
        """Initialize RainbirdSession."""
        self._password = password
        self._logger = logger

    def encode_command(self, method: str, params: dict[str, Any]) -> str:
        """Encode a request payload."""
        request_id = time.time()
        data = {
            "id": request_id,
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
        }
        send_data = json.dumps(data)
        self._logger.debug("Request: %s", send_data)
        if self._password is None:
            return send_data
        return encrypt(send_data, self._password)

    def decode_command(self, content: bytes) -> str:
        """Decode a response payload."""
        if self._password is not None:
            decrypted_data = (
                decrypt(content, self._password)
                .decode("UTF-8")
                .rstrip("\x10")
                .rstrip("\x0A")
                .rstrip("\x00")
                .rstrip()
            )
            content = decrypted_data
        self._logger.debug("Response: %s" % content)
        response = json.loads(content)
        if error := response.get("error"):
            msg = ["Error from controller"]
            if code := error.get("code"):
                try:
                    value = ErrorCode(code)
                except ValueError:
                    value = ErrorCode.UNKNOWN
                msg.append(f"Code: {str(value)}({code})")
            if message := error.get("message"):
                msg.append(f"Message: {message}")
            ", ".join(msg)
            raise RainbirdApiException(", ".join(msg))
        return response["result"]
