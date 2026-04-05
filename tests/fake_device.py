"""Fake Rainbird Device for testing."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from pyrainbird.encryption import decrypt
from pyrainbird.resources import RAINBIRD_COMMANDS

_LOGGER = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Base class for log entries."""

    pass


@dataclass
class RequestLogEntry(LogEntry):
    """A logged outgoing JSON-RPC request."""

    request: dict[str, Any]
    command: str | None = None
    raw_data: str | None = None

    def __str__(self) -> str:
        lines = ["[client >]"]
        if self.command:
            lines.append(f"Intent: {self.command} ({self.raw_data})")
        lines.append(f"Payload: {json.dumps(self.request, indent=2)}")
        return "\n".join(lines)


@dataclass
class ResponseLogEntry(LogEntry):
    """A logged incoming JSON-RPC response."""

    response: dict[str, Any]

    def __str__(self) -> str:
        lines = ["[server <]"]
        lines.append(f"Payload: {json.dumps(self.response, indent=2)}")
        return "\n".join(lines)


@dataclass
class ErrorLogEntry(LogEntry):
    """A completely failed or malformed intercept log."""

    error: str
    reason: str

    def __str__(self) -> str:
        lines = ["[error !]"]
        lines.append(f"{self.error}: {self.reason}")
        return "\n".join(lines)


class CapturedRequestLog(list[LogEntry]):
    """List of captured intercepted API requests."""

    def __str__(self) -> str:
        """Format the log as a sequential string."""
        return "\n\n".join(str(entry) for entry in self).strip()


class FakeRainbirdDevice:
    """Stateful fake Rain Bird device simulator."""

    def __init__(self) -> None:
        self.request_log = CapturedRequestLog()

    def process_request(self, body: bytes, pwd: str | None) -> dict[str, Any] | None:
        """Decode and log a request, returning the decoded JSON."""
        try:
            if pwd:
                decrypted_req = (
                    decrypt(body, pwd)
                    .decode("UTF-8")
                    .rstrip("\x10")
                    .rstrip("\x0a")
                    .rstrip("\x00")
                    .rstrip()
                )
                decoded_request = json.loads(decrypted_req)
            else:
                decoded_request = json.loads(body)

            log_entry = RequestLogEntry(request=decoded_request)

            if (
                decoded_request.get("method") == "tunnelSip"
                and "params" in decoded_request
            ):
                data = decoded_request["params"].get("data")
                if data and len(data) >= 2:
                    cmd_code = data[:2]
                    command_name = "Unknown"
                    for name, cmd_set in RAINBIRD_COMMANDS.items():
                        if cmd_set.get("command") == cmd_code:
                            command_name = name
                            break
                    log_entry.command = command_name
                    log_entry.raw_data = data

            self.request_log.append(log_entry)
            return decoded_request
        except Exception as e:
            self.request_log.append(ErrorLogEntry("Failed to decode request", str(e)))
            _LOGGER.exception("Failed to decode request")
            return None

    def process_response(
        self, response_body: bytes | None, status: int, pwd: str | None
    ) -> None:
        """Decode and log a response."""
        if status != 200:
            self.request_log.append(
                ErrorLogEntry(f"HTTP Status {status}", "Response had an error code")
            )

        if not response_body:
            return

        try:
            if pwd:
                decrypted_res = (
                    decrypt(response_body, pwd)
                    .decode("UTF-8")
                    .rstrip("\x10")
                    .rstrip("\x0a")
                    .rstrip("\x00")
                    .rstrip()
                )
                decoded_response = json.loads(decrypted_res)
            else:
                decoded_response = json.loads(response_body)

            self.request_log.append(ResponseLogEntry(response=decoded_response))
        except Exception as e:
            self.request_log.append(ErrorLogEntry("Failed to decrypt response", str(e)))
            _LOGGER.exception("Failed to decode response")
