"""Stateful Fake Rain Bird Device Simulator."""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, time
from typing import Any

import aiohttp

from pyrainbird import rainbird
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

    def __init__(self, output_dir: str = "./extracted_fw") -> None:
        self.request_log = CapturedRequestLog()
        self.output_dir = output_dir

        # Device State variables
        self.model_code = 0x07  # Default to ESP-TM2
        self.version_major = 1
        self.version_minor = 3

        self.stations: set[int] = {1, 2, 3, 4, 5, 6, 7}
        self.schedule: dict[str, str] = {}
        self.zone_states: dict[str, str] = {}

        self.serial_number: int = 0x12635436566
        self.time: time = time(12, 34, 56)
        self.date: date = date(2023, 1, 1)
        self.water_budget_pct: int = 100
        self.rain_sensor_state: bool = False
        self.rain_delay: int = 0
        self.irrigation_state: bool = False

        # Firmware Update State variables (0 = OK, 1 = Error, 2 = Busy)
        self.update_status = 0
        self.lnk_progress = 0
        self.unv_progress = 0
        self._update_task: asyncio.Task[None] | None = None

        # Command handlers
        self.handlers = {
            "02": self._handle_model_and_version,
            "03": self._handle_available_stations,
            "05": self._handle_serial_number,
            "10": self._handle_current_time,
            "12": self._handle_current_date,
            "20": self._handle_retrieve_schedule,
            "30": self._handle_water_budget,
            "36": self._handle_rain_delay,
            "3E": self._handle_rain_sensor,
            "3F": self._handle_zone_state,
            "48": self._handle_current_irrigation,
            # Setters reply with ACK
            "11": self._handle_ack,
            "13": self._handle_ack,
            "37": self._handle_ack,
            "38": self._handle_ack,
            "39": self._handle_ack,
            "3A": self._handle_ack,
            "40": self._handle_ack,
            "42": self._handle_ack,
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

    def _handle_retrieve_schedule(self, data: str) -> str:
        """Handle RetrieveScheduleRequest (20)."""
        subcommand = data[2:6] if len(data) >= 6 else data[2:]
        return self.schedule.get(subcommand, "80" + subcommand + "00000000")

    def _handle_zone_state(self, data: str) -> str:
        """Handle RequestZoneState (3F)."""
        subcommand = data[2:4] if len(data) >= 4 else data[2:]
        return self.zone_states.get(subcommand, "BF" + subcommand + "00000000")

    def _encode(self, cmd: str, *args: Any) -> str:
        cmd_set = RAINBIRD_COMMANDS.get(cmd) or next(
            v for v in RAINBIRD_COMMANDS.values() if v.get("command") == cmd
        )
        return rainbird.encode_command(cmd_set, *args)

    def _handle_ack(self, data: str) -> str:
        return self._encode("AcknowledgeResponse", int(data[:2], 16))

    def _handle_serial_number(self, data: str) -> str:
        return self._encode("SerialNumberResponse", self.serial_number)

    def _handle_current_time(self, data: str) -> str:
        return self._encode(
            "CurrentTimeResponse", self.time.hour, self.time.minute, self.time.second
        )

    def _handle_current_date(self, data: str) -> str:
        return self._encode(
            "CurrentDateResponse", self.date.day, self.date.month, self.date.year
        )

    def _handle_water_budget(self, data: str) -> str:
        return self._encode("WaterBudgetResponse", 1, self.water_budget_pct)

    def _handle_rain_sensor(self, data: str) -> str:
        return self._encode("CurrentRainSensorStateResponse", self.rain_sensor_state)

    def _handle_rain_delay(self, data: str) -> str:
        return self._encode("RainDelaySettingResponse", self.rain_delay)

    def _handle_current_irrigation(self, data: str) -> str:
        return self._encode("CurrentIrrigationStateResponse", self.irrigation_state)

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
                decoded_request = json.loads(body.decode("UTF-8"))

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
        if request.get("method") != "tunnelSip" or "params" not in request:
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
            if pwd:
                return encrypt(payload, pwd)
            return payload.encode("UTF-8")

        return None

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
        if pwd:
            return encrypt(payload, pwd)
        return payload.encode("UTF-8")

    async def start_firmware_update(self, update_url: str) -> None:
        """Trigger an asynchronous firmware update download task."""
        # Cancel any previous task
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()

        self._update_task = asyncio.create_task(
            self._firmware_update_runner(update_url)
        )

    async def _firmware_update_runner(self, update_url: str) -> None:
        _LOGGER.info("Starting simulated firmware update from URL: %s", update_url)
        self.update_status = 2  # Busy
        self.lnk_progress = 0
        self.unv_progress = 0

        try:
            async with aiohttp.ClientSession() as session:
                if update_url.endswith("/"):
                    # LNK update: download release.json and filesystem.bin
                    files_to_download = ["release.json", "filesystem.bin"]
                    base_url = update_url
                else:
                    # Controller update: download direct firmware.bin
                    files_to_download = [os.path.basename(update_url)]
                    base_url = os.path.dirname(update_url) + "/"

                total_files = len(files_to_download)
                os.makedirs(self.output_dir, exist_ok=True)

                for idx, filename in enumerate(files_to_download):
                    file_url = f"{base_url}{filename}"
                    _LOGGER.info("Downloading %s from %s...", filename, file_url)

                    async with session.get(file_url) as resp:
                        if resp.status != 200:
                            raise RuntimeError(
                                f"HTTP status {resp.status} for {filename}"
                            )

                        dest_path = os.path.join(self.output_dir, filename)
                        with open(dest_path, "wb") as f:
                            chunk_size = 4096
                            downloaded = 0
                            content_length = resp.content_length or 102400

                            async for chunk in resp.content.iter_chunked(chunk_size):
                                f.write(chunk)
                                downloaded += len(chunk)

                                progress = int((downloaded / content_length) * 100)
                                progress = min(100, max(0, progress))

                                file_weight = 1.0 / total_files
                                current_overall_progress = int(
                                    (
                                        idx * file_weight
                                        + (progress / 100.0) * file_weight
                                    )
                                    * 100
                                )
                                self.lnk_progress = current_overall_progress
                                self.unv_progress = current_overall_progress
                                await asyncio.sleep(0.01)

                _LOGGER.info(
                    "Successfully downloaded all firmware files to %s", self.output_dir
                )
                self.update_status = 0  # OK
                self.lnk_progress = 100
                self.unv_progress = 100
        except Exception as e:
            _LOGGER.exception("Error during firmware update download: %s", e)
            self.update_status = 1  # Error

    def get_firmware_update_status(self) -> dict[str, int]:
        """Return the current firmware update status payload."""
        return {
            "updateStatus": self.update_status,
            "lnkProgress": self.lnk_progress,
            "unvProgress": self.unv_progress,
        }
