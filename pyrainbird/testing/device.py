"""Stateful Fake Rain Bird Device Simulator backed by RainbirdDeviceEmulator."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from datetime import date, time
from typing import Any

import aiohttp

from pyrainbird.encryption import decrypt, encrypt
from pyrainbird.resources import MODEL_INFO, RAINBIRD_COMMANDS

from .emulator import RainbirdDeviceEmulator, create_device_for_model

_LOGGER = logging.getLogger(__name__)


@dataclass
class LogEntry:
    """Base class for log entries."""


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


class FakeRainbirdDevice(RainbirdDeviceEmulator):
    """Stateful fake Rain Bird device simulator backed by RainbirdDeviceEmulator."""

    def __init__(
        self,
        output_dir: str = "./extracted_fw",
        model: str | int = "ESP_TM2",
        *,
        version_major: int = 1,
        version_minor: int = 3,
        password: str | None = None,
    ) -> None:
        super().__init__(
            model,
            version_major=version_major,
            version_minor=version_minor,
            password=password,
        )
        object.__setattr__(self, "request_log", CapturedRequestLog())
        object.__setattr__(self, "output_dir", output_dir)
        object.__setattr__(self, "schedule", {})
        object.__setattr__(self, "zone_states", {})
        object.__setattr__(self, "_update_task", None)
        self.serial_number = 0x12635436566
        self.time = time(12, 34, 56)
        self.date = date(2023, 1, 1)

    @property
    def stations(self) -> set[int]:
        return self.device.available_stations

    @stations.setter
    def stations(self, val: set[int]) -> None:
        self.device.available_stations = set(val)

    @property
    def serial_number(self) -> int:
        return int(self.device.serial_number_hex, 16)

    @serial_number.setter
    def serial_number(self, val: int) -> None:
        self.device.serial_number_hex = f"{int(val):016X}"

    @property
    def time(self) -> time:
        return time(self.device.hour, self.device.minute, self.device.second)

    @time.setter
    def time(self, val: time) -> None:
        self.device.hour, self.device.minute, self.device.second = (
            val.hour,
            val.minute,
            val.second,
        )

    @property
    def date(self) -> date:
        return date(self.device.year, self.device.month, self.device.day)

    @date.setter
    def date(self, val: date) -> None:
        self.device.year, self.device.month, self.device.day = (
            val.year,
            val.month,
            val.day,
        )

    @property
    def water_budget_pct(self) -> int:
        return self.device.seasonal_adjust

    @water_budget_pct.setter
    def water_budget_pct(self, val: int) -> None:
        self.device.seasonal_adjust = int(val)
        for p in self.device.water_budget:
            self.device.water_budget[p] = int(val)

    @property
    def rain_sensor_state(self) -> bool:
        return bool(self.device.sensor_state)

    @rain_sensor_state.setter
    def rain_sensor_state(self, val: bool) -> None:
        self.device.sensor_state = 1 if val else 0

    @property
    def rain_delay(self) -> int:
        return self.device.rain_delay_days

    @rain_delay.setter
    def rain_delay(self, val: int) -> None:
        self.device.rain_delay_days = int(val)

    @property
    def irrigation_state(self) -> bool:
        return bool(self.device.controller_state)

    @irrigation_state.setter
    def irrigation_state(self, val: bool) -> None:
        self.device.controller_state = 1 if val else 0

    @property
    def update_status(self) -> int:
        return self.device.fw_update_status

    @update_status.setter
    def update_status(self, val: int) -> None:
        self.device.fw_update_status = int(val)

    @property
    def lnk_progress(self) -> int:
        return self.device.fw_lnk_progress

    @lnk_progress.setter
    def lnk_progress(self, val: int) -> None:
        self.device.fw_lnk_progress = int(val)

    @property
    def unv_progress(self) -> int:
        return self.device.fw_unv_progress

    @unv_progress.setter
    def unv_progress(self, val: int) -> None:
        self.device.fw_unv_progress = int(val)

    def set_model(self, model_identifier: str | int) -> None:
        """Switch the underlying device emulator to the specified controller model."""
        prev = self.device
        try:
            new_dev = create_device_for_model(
                model_identifier,
                version_major=prev.version_major,
                version_minor=prev.version_minor,
                password=prev.password,
            )
        except ValueError:
            for info in MODEL_INFO:
                if (
                    info.get("code") == model_identifier
                    or info.get("name") == model_identifier
                ):
                    new_dev = create_device_for_model(
                        int(info["device_id"], 16),
                        version_major=prev.version_major,
                        version_minor=prev.version_minor,
                        password=prev.password,
                    )
                    break
            else:
                raise
        new_dev.serial_number_hex = prev.serial_number_hex
        object.__setattr__(self, "device", new_dev)
        object.__setattr__(self, "stick", new_dev.stick)

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
        """Generate a JSON-RPC response using RainbirdDeviceEmulator."""
        method = request.get("method")
        if not isinstance(method, str):
            return None
        req_id = request.get("id", 1)

        if method == "tunnelSip":
            data = (request.get("params") or {}).get("data", "")
            if not data:
                return None
            cmd_code = data[:2].upper()
            if cmd_code == "20" and self.schedule:
                sub = data[2:6] if len(data) >= 6 else data[2:]
                resp_hex = self.schedule.get(sub, f"80{sub}00000000")
            elif cmd_code == "0C" and self.schedule and data in self.schedule:
                resp_hex = self.schedule[data]
            elif cmd_code == "3F" and self.zone_states:
                sub = data[2:4] if len(data) >= 4 else data[2:]
                resp_hex = self.zone_states.get(sub, f"BF{sub}00000000")
            else:
                resp_hex = self.device.handle_sip(data, transport="STICK_TUNNEL_SIP")
            payload = json.dumps(
                {"jsonrpc": "2.0", "result": {"data": resp_hex}, "id": req_id}
            )
        else:
            rpc_req = {"jsonrpc": "2.0", **request}
            rpc_resp = self.stick.handle_jsonrpc(rpc_req, request_encrypted=bool(pwd))
            if "error" in rpc_resp:
                return None
            payload = json.dumps(rpc_resp)

        return encrypt(payload, pwd) if pwd else payload.encode("UTF-8")

    def generate_nack(self, request: dict[str, Any], pwd: str | None) -> bytes:
        """Generate a NotAcknowledgeResponse for an unsupported command."""
        req_id = request.get("id", 1)
        data = request.get("params", {}).get("data", "00")
        command_echo = data[:2] if len(data) >= 2 else "00"
        resp_hex = f"00{command_echo}00"
        payload = json.dumps(
            {"jsonrpc": "2.0", "result": {"data": resp_hex}, "id": req_id}
        )
        return encrypt(payload, pwd) if pwd else payload.encode("UTF-8")

    async def start_firmware_update(self, update_url: str) -> None:
        """Trigger an asynchronous firmware update download task."""
        if self._update_task and not self._update_task.done():
            self._update_task.cancel()
        object.__setattr__(
            self,
            "_update_task",
            asyncio.create_task(self._firmware_update_runner(update_url)),
        )

    async def _firmware_update_runner(self, update_url: str) -> None:
        _LOGGER.info("Starting simulated firmware update from URL: %s", update_url)
        self.update_status = 2
        self.lnk_progress = 0
        self.unv_progress = 0

        try:
            async with aiohttp.ClientSession() as session:
                if update_url.endswith("/"):
                    files_to_download = ["release.json", "filesystem.bin"]
                    base_url = update_url
                else:
                    files_to_download = [os.path.basename(update_url)]
                    base_url = os.path.dirname(update_url) + "/"

                total_files = len(files_to_download)
                os.makedirs(self.output_dir, exist_ok=True)

                for idx, filename in enumerate(files_to_download):
                    file_url = f"{base_url}{filename}"
                    async with session.get(file_url) as resp:
                        if resp.status != 200:
                            raise RuntimeError(
                                f"HTTP status {resp.status} for {filename}"
                            )
                        dest_path = os.path.join(self.output_dir, filename)
                        with open(dest_path, "wb") as f:  # noqa: ASYNC230
                            downloaded = 0
                            content_length = resp.content_length or 102400
                            async for chunk in resp.content.iter_chunked(4096):
                                f.write(chunk)
                                downloaded += len(chunk)
                                progress = min(
                                    100,
                                    max(0, int((downloaded / content_length) * 100)),
                                )
                                file_weight = 1.0 / total_files
                                overall = int(
                                    (
                                        idx * file_weight
                                        + (progress / 100.0) * file_weight
                                    )
                                    * 100
                                )
                                self.lnk_progress = overall
                                self.unv_progress = overall
                                await asyncio.sleep(0.01)

                self.update_status = 0
                self.lnk_progress = 100
                self.unv_progress = 100
        except Exception:
            _LOGGER.exception("Error during firmware update download")
            self.update_status = 1

    def get_firmware_update_status(self) -> dict[str, int]:
        """Return the current firmware update status payload."""
        return {
            "updateStatus": self.update_status,
            "lnkProgress": self.lnk_progress,
            "unvProgress": self.unv_progress,
        }
