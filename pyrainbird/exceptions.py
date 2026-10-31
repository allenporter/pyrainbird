"""Exceptions from rainbird."""

from typing import Any

_NACK_REASONS: tuple[tuple[int, str], ...] = (
    (0x01, "Command not supported"),
    (0x02, "Invalid payload length or bad match"),
    (0x04, "Incompatible or out-of-range data"),
    (0x08, "Checksum error"),
)


def format_nack_reason(nak_code: int) -> str:
    """Return a human-readable description of a SIP NACK bitmask code."""
    reasons = [label for mask, label in _NACK_REASONS if nak_code & mask]
    return ", ".join(reasons) if reasons else "Unknown error"


class RainbirdApiException(Exception):
    """Exception from rainbird api."""


class RainbirdDeviceNackError(RainbirdApiException):
    """The device returned a Not Acknowledge (NACK) response."""

    def __init__(
        self,
        message: str = "Device returned a NACK response",
        *,
        command: str | None = None,
        command_echo: int | None = None,
        nak_code: int | None = None,
    ) -> None:
        """Initialize RainbirdDeviceNackError."""
        super().__init__(message)
        self.command = command
        self.command_echo = command_echo
        self.nak_code = nak_code

    @classmethod
    def from_decoded(
        cls,
        command: str,
        decoded: dict[str, Any],
    ) -> "RainbirdDeviceNackError":
        """Create a descriptive RainbirdDeviceNackError from a decoded NACK response."""
        echo = decoded.get("commandEcho")
        nak_code = decoded.get("NAKCode")
        msg = f"Device returned a NACK response for {command}"
        if isinstance(nak_code, int):
            msg = f"{msg} (nak_code=0x{nak_code:02X}: {format_nack_reason(nak_code)})"
        return cls(
            msg,
            command=command,
            command_echo=echo if isinstance(echo, int) else None,
            nak_code=nak_code if isinstance(nak_code, int) else None,
        )


class RainbirdDeviceBusyException(RainbirdApiException):
    """Device is busy processing another request."""


class RainbirdAuthException(RainbirdApiException):
    """Authentication exception from rainbird API."""


class RainbirdCertificateError(RainbirdApiException):
    """TLS certificate verification error when communicating with the device."""


class RainbirdConnectionError(RainbirdApiException):
    """Transport-level connection error when communicating with the device."""


class RainbirdCodingException(Exception):
    """Error while encoding or decoding objects indicating a bug."""
