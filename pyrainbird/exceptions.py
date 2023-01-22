"""Exceptions from rainbird."""


class RainbirdApiException(Exception):
    """Exception from rainbird api."""


class RainbirdDeviceBusyException(RainbirdApiException):
    """Device is busy processing another request."""


class RainbirdAuthException(RainbirdApiException):
    """Authentication exception from rainbird API."""


class RainbirdCodingException(RainbirdApiException):
    """Error while encoding or decoding objects."""
