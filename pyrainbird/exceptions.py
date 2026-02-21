"""Exceptions from rainbird."""


class RainbirdApiException(Exception):
    """Exception from rainbird api."""


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
