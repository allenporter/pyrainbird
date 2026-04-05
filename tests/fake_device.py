"""Fake Rainbird Device for testing."""

import json
import logging
from dataclasses import dataclass
from typing import Any

from pyrainbird.encryption import decrypt, encrypt
from pyrainbird.resources import MODEL_INFO, RAINBIRD_COMMANDS

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

        # Phase 2: Simulator State variables
        self.model_code = 0x07  # Default to ESP-TM2
        self.version_major = 1
        self.version_minor = 3

        self.stations: set[int] = {
            1,
            2,
            3,
            4,
            5,
            6,
            7,
        }

        # Command handlers
        self.handlers = {
            "02": self._handle_model_and_version,
            "03": self._handle_available_stations,
        }

    def _handle_model_and_version(self, data: str) -> str:
        """Handle ModelAndVersionRequest (02)."""
        return (
            f"82{self.model_code:04X}{self.version_major:02X}{self.version_minor:02X}"
        )

    def _handle_available_stations(self, data: str) -> str:
        """Handle AvailableStationsRequest (03)."""
        page = int(data[2:4], 16) if len(data) >= 4 else 0
        mask_str = ""
        # 4 bytes per page (32 stations)
        for b in range(4):
            byte_val = 0
            for bit in range(8):
                station_num = page * 32 + b * 8 + bit + 1
                if station_num in self.stations:
                    byte_val |= 1 << bit
            mask_str += f"{byte_val:02X}"
        return f"83{page:02X}{mask_str}"

    def set_model(self, model_identifier: str) -> None:
        """Lookup and set the model code from pyrainbird's device registry."""
        for info in MODEL_INFO:
            if (
                info.get("code") == model_identifier
                or info.get("name") == model_identifier
            ):
                self.model_code = int(info["device_id"], 16)
                return
        raise ValueError(
            f"Unknown model identifier '{model_identifier}' in models.yaml registry."
        )

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

    def generate_response(
        self, request: dict[str, Any], pwd: str | None
    ) -> bytes | None:
        """Autonomously generate a response for a decoded request. If unsupported, return None."""
        if not pwd or request.get("method") != "tunnelSip" or "params" not in request:
            return None

        data = request["params"].get("data")
        if not data:
            return None

        req_id = request.get("id", 1)
        cmd_code = data[:2]
        handler = self.handlers.get(cmd_code)

        if handler:
            resp_hex = handler(data)
            payload = json.dumps(
                {"jsonrpc": "2.0", "result": {"data": resp_hex}, "id": req_id}
            )
            return encrypt(payload, pwd)

        return None  # Pass to conftest.py to decide manual queue vs NACK

    def generate_nack(self, request: dict[str, Any], pwd: str | None) -> bytes:
        """Autonomously generate a NotAcknowledgeResponse for an unsupported command."""
        req_id = request.get("id", 1)
        data = request.get("params", {}).get("data", "00")

        command_echo = data[:2] if len(data) >= 2 else "00"
        nak_code = "00"  # generic NAK
        resp_hex = f"00{command_echo}{nak_code}"

        payload = json.dumps(
            {"jsonrpc": "2.0", "result": {"data": resp_hex}, "id": req_id}
        )
        return encrypt(payload, pwd)

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
