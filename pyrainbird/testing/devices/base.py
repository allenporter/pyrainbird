"""BaseControllerDevice implementing core SIP opcodes via a dispatch table."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ..profiles import ControllerProfile, get_controller_profile
from ..stick import LNK2StickEmulator
from .state import init_core_state, init_stick_state

SipHandler = Callable[[str, int, str | None], str]


class BaseControllerDevice:
    """Base Rain Bird controller device implementing core SIP opcodes (0x00-0x4D / 0x82-0xCD)."""

    def __init__(
        self,
        model: str | int,
        *,
        version_major: int = 1,
        version_minor: int = 0,
        password: str | None = None,
    ) -> None:
        self.profile: ControllerProfile = get_controller_profile(model)
        self.sip_model_hex: str = self.profile.sip_model_hex
        self.model_code: int = (
            0xFFFF
            if self.sip_model_hex == "-0001"
            else int(self.sip_model_hex, 16) & 0xFFFF
        )
        self.version_major: int = version_major
        self.version_minor: int = version_minor

        self._init_device_state()
        init_stick_state(self, password)

        self.stick: LNK2StickEmulator = LNK2StickEmulator(self)
        self._sip_handlers: dict[str, SipHandler] = self._build_sip_handlers()

    def _init_device_state(self) -> None:
        """Initialize device-specific state attributes."""
        init_core_state(self)

    def _build_sip_handlers(self) -> dict[str, SipHandler]:
        return {
            "02": self._op_model_and_version,
            "03": self._op_available_stations,
            "04": self._op_command_support,
            "05": self._op_serial_number,
            "0B": self._op_firmware_version,
            "10": self._op_current_time,
            "11": self._op_set_current_time,
            "12": self._op_current_date,
            "13": self._op_set_current_date,
            "20": self._op_retrieve_schedule,
            "21": self._op_set_schedule,
            "2B": self._op_stack_run_station_seconds,
            "2C": self._op_test_all_stations_seconds,
            "2D": self._op_pause_irrigation,
            "2E": self._op_resume_irrigation,
            "30": self._op_water_budget,
            "31": self._op_set_water_budget,
            "32": self._op_zone_or_monthly_adjust,
            "33": self._op_set_zone_or_monthly_adjust,
            "36": self._op_rain_delay,
            "37": self._op_set_rain_delay,
            "38": self._op_manually_run_program,
            "39": self._op_manually_run_station,
            "3A": self._op_test_all_stations,
            "3B": self._op_current_queue,
            "3D": self._op_current_station_error,
            "3E": self._op_rain_sensor_state,
            "3F": self._op_stations_active,
            "40": self._op_stop_irrigation,
            "42": self._op_advance_station,
            "48": self._op_current_irrigation_state,
            "49": self._op_set_controller_state,
            "4A": self._op_event_timestamp,
            "4B": self._op_stack_manual_run,
            "4C": self._op_combined_controller_state,
            "4D": self._op_irrigation_statistics,
        }

    # --- Stick & State Delegation ---

    def handle_http_post(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Delegate /stick HTTP POST handling to LNK2StickEmulator."""
        return self.stick.handle_http_post(*args, **kwargs)

    def handle_jsonrpc(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        """Delegate Stick JSON-RPC 2.0 request to LNK2StickEmulator."""
        return self.stick.handle_jsonrpc(*args, **kwargs)

    # --- Core SIP Command Dispatch ---

    def _nak(self, cmd_hex: str, reason: int = 1) -> str:
        return f"00{cmd_hex[:2].upper()}{reason:02X}"

    def _ack(self, cmd_hex: str) -> str:
        return f"01{cmd_hex[:2].upper()}"

    @staticmethod
    def _pack_date_3bytes_hex(day: int, month: int, year: int) -> str:
        b1 = day & 0xFF
        b2 = ((month & 0x0F) << 4) | ((year >> 8) & 0x0F)
        b3 = year & 0xFF
        return f"{b1:02X}{b2:02X}{b3:02X}"

    def handle_sip(self, payload_hex: str, *, transport: str | None = None) -> str:
        """Execute a raw hexadecimal SIP command via the _sip_handlers dispatch table."""
        data = payload_hex.strip().upper()
        if len(data) < 2 or len(data) % 2 != 0:
            return "000002"
        cmd = data[:2]
        handler = self._sip_handlers.get(cmd)
        if handler is None:
            return self._nak(cmd, 1)
        return handler(data, len(data) // 2, transport)

    def _op_model_and_version(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        w = (
            "FFFF"
            if self.sip_model_hex == "-0001"
            else f"{self.model_code & 0xFFFF:04X}"
        )
        return f"82{w}{self.version_major & 0xFF:02X}{self.version_minor & 0xFF:02X}"

    def _op_available_stations(self, d: str, bl: int, _t: str | None) -> str:
        if bl not in (1, 2):
            return self._nak(d, 2)
        page = int(d[2:4], 16) if bl == 2 else 0
        if page in self.available_stations_page_overrides:
            return f"83{page:02X}{self.available_stations_page_overrides[page]}"
        mask_hex = ""
        for b_idx in range(4):
            b_val = sum(
                1 << bit
                for bit in range(8)
                if (page * 32 + b_idx * 8 + bit + 1) in self.available_stations
            )
            mask_hex += f"{b_val:02X}"
        return f"83{page:02X}{mask_hex}"

    def _op_command_support(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        cmd = d[2:4]
        ok = (
            cmd in self.supported_commands
            if self.supported_commands is not None
            else self._is_command_supported_by_default(cmd)
        )
        return f"84{cmd}{'01' if ok else '00'}"

    def _is_command_supported_by_default(self, cmd: str) -> bool:
        cap_map = {
            "4C": self.profile.combined_controller_state,
            "4B": self.profile.stack_manual_run_station,
            "49": self.profile.controller_state_set,
            "4A": self.profile.schedule_timestamp,
        }
        if cmd in cap_map:
            return cap_map[cmd]
        return cmd in self._sip_handlers

    def _op_serial_number(self, d: str, bl: int, _t: str | None) -> str:
        s = self.serial_number_hex.zfill(16)[:16]
        return f"85{s}" if bl == 1 else self._nak(d, 2)

    def _op_firmware_version(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        sub = "".join(s.zfill(8)[:8] for s in self.fw_submodules)
        n = len(self.fw_submodules) & 0xFF
        return f"8B{self.fw_major & 0xFF:02X}{self.fw_minor & 0xFF:02X}{self.fw_build & 0xFF:02X}{n:02X}{sub}"

    def _op_current_time(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        return (
            f"90{self.hour & 0xFF:02X}{self.minute & 0xFF:02X}{self.second & 0xFF:02X}"
        )

    def _op_set_current_time(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 4:
            return self._nak(d, 2)
        h, m, s = int(d[2:4], 16), int(d[4:6], 16), int(d[6:8], 16)
        if not (0 <= h <= 23 and 0 <= m <= 59 and 0 <= s <= 59):
            return self._nak(d, 4)
        self.hour, self.minute, self.second = h, m, s
        return self._ack(d)

    def _op_current_date(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        return f"92{self._pack_date_3bytes_hex(self.day, self.month, self.year)}"

    def _op_set_current_date(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 4:
            return self._nak(d, 2)
        dv, mv, yv = int(d[2:4], 16), int(d[4:5], 16), int(d[5:8], 16)
        if not (1 <= mv <= 12 and 1 <= dv <= 31):
            return self._nak(d, 4)
        self.day, self.month, self.year = dv, mv, yv
        return self._ack(d)

    def _op_retrieve_schedule(self, d: str, bl: int, _t: str | None) -> str:
        return (
            self._handle_retrieve_schedule(int(d[2:6], 16))
            if bl == 3
            else self._nak(d, 2)
        )

    def _op_set_schedule(self, d: str, bl: int, _t: str | None) -> str:
        if bl < 4:
            return self._nak(d, 2)
        return self._handle_set_schedule(int(d[2:6], 16), bytes.fromhex(d[6:]))

    def _handle_retrieve_schedule(self, _page_id: int) -> str:
        return "002002"

    def _handle_set_schedule(self, _page_id: int, _payload: bytes) -> str:
        return "002102"

    def _enqueue_manual_run(self, stn: int, dur_sec: int) -> None:
        if self.active_station == 0:
            self.active_station = stn
            self.remaining_runtime_sec = dur_sec
            self.manual_queue_count = 1
        else:
            self.queue.append({"station": stn, "seconds": dur_sec})
            self.manual_queue_count += 1
        self.queued_entries.append({"station_id": stn, "remaining_seconds": dur_sec})

    def _op_stack_run_station_seconds(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 5:
            return self._nak(d, 2)
        self._enqueue_manual_run(int(d[2:6], 16), int(d[6:10], 16))
        return self._ack(d)

    def _op_test_all_stations_seconds(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 3:
            return self._nak(d, 2)
        stns = sorted(self.available_stations)
        if stns:
            self.active_station = stns[0]
            self.remaining_runtime_sec = int(d[2:6], 16)
            self.manual_queue_count = len(stns)
        return self._ack(d)

    def _op_pause_irrigation(self, d: str, bl: int, _t: str | None) -> str:
        if bl not in (1, 3):
            return self._nak(d, 2)
        self.paused = True
        self.status_flags |= 0x08
        return self._ack(d)

    def _op_resume_irrigation(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        self.paused = False
        self.status_flags &= ~0x08
        return self._ack(d)

    def _op_water_budget(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        prog = int(d[2:4], 16)
        pct = self.water_budget.get(prog, self.seasonal_adjust)
        return f"B0{prog & 0xFF:02X}{pct & 0xFFFF:04X}"

    def _op_set_water_budget(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 4:
            return self._nak(d, 2)
        prog, pct = int(d[2:4], 16), int(d[4:8], 16)
        self.water_budget[prog] = pct
        self.seasonal_adjust = pct
        self._on_water_budget_updated(prog, pct)
        return self._ack(d)

    def _on_water_budget_updated(self, prog: int, pct: int) -> None:
        """Hook for program-based subclasses to synchronize program seasonal adjust."""

    def _op_zone_or_monthly_adjust(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        param = int(d[2:4], 16)
        pct = self.monthly_water_budget.get(param, 100)
        return f"B2{param:02X}{pct & 0xFFFF:04X}"

    def _op_set_zone_or_monthly_adjust(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 4:
            return self._nak(d, 2)
        param = int(d[2:4], 16)
        self.monthly_water_budget[param] = int(d[4:8], 16)
        return self._ack(d)

    def _op_rain_delay(self, d: str, bl: int, _t: str | None) -> str:
        rd = self.rain_delay_days & 0xFFFF
        return f"B6{rd:04X}" if bl == 1 else self._nak(d, 2)

    def _op_set_rain_delay(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 3:
            return self._nak(d, 2)
        self.rain_delay_days = int(d[2:6], 16)
        return self._ack(d)

    def _op_manually_run_program(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        prog = int(d[2:4], 16)
        self.active_program = prog
        if self.program_0_stations and prog == 0:
            first = self.program_0_stations[0]
            self.active_station = int(first["station"])
            self.remaining_runtime_sec = int(first.get("minutes", 0)) * 60
        elif not self._expand_program_schedule(prog) and self.active_station == 0:
            self.active_station = 1
        return self._ack(d)

    def _collect_program_runnable_stations(self, prog: int) -> list[tuple[int, int]]:
        _ = prog
        return []

    def _expand_program_schedule(self, prog: int) -> bool:
        runnable = self._collect_program_runnable_stations(prog)
        if not runnable:
            return False
        self.active_station, self.remaining_runtime_sec = runnable[0]
        self.queued_entries = [
            {"station_id": s, "program_id": prog, "remaining_seconds": sec}
            for s, sec in runnable
        ]
        self.auto_queue_count = len(runnable)
        self.queue = [{"station": s, "seconds": sec} for s, sec in runnable[1:]]
        return True

    def _op_manually_run_station(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 4:
            return self._nak(d, 2)
        self.active_station = int(d[2:6], 16)
        self.active_program = 0xFF
        self.remaining_runtime_sec = int(d[6:8], 16) * 60
        self.manual_queue_count = 1
        return self._ack(d)

    def _op_test_all_stations(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        stns = sorted(self.available_stations)
        if stns:
            self.active_station = stns[0]
            self.remaining_runtime_sec = int(d[2:4], 16) * 60
            self.manual_queue_count = len(stns)
        return self._ack(d)

    def _op_current_queue(self, d: str, bl: int, _t: str | None) -> str:
        return (
            self._handle_current_queue(int(d[2:4], 16)) if bl == 2 else self._nak(d, 2)
        )

    def _handle_current_queue(self, page: int) -> str:
        return f"BB{page & 0xFF:02X}"

    def _op_current_station_error(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        page = int(d[2:4], 16)
        sm = self.short_mask_by_page.get(page, 0) & 0xFF
        om = self.open_mask_by_page.get(page, 0) & 0xFF
        return f"BD{page:02X}{sm:02X}{om:02X}0000"

    def _op_rain_sensor_state(self, d: str, bl: int, _t: str | None) -> str:
        return f"BE{self.sensor_state & 0xFF:02X}" if bl == 1 else self._nak(d, 2)

    def _op_stations_active(self, d: str, bl: int, _t: str | None) -> str:
        if bl not in (1, 2):
            return self._nak(d, 2)
        page = int(d[2:4], 16) if bl == 2 else 0
        mb = [0, 0, 0, 0]
        if self.active_station > 0 and (self.active_station - 1) // 32 == page:
            off = (self.active_station - 1) % 32
            mb[off // 8] |= 1 << (off % 8)
        return f"BF{page:02X}" + "".join(f"{b:02X}" for b in mb)

    def _op_stop_irrigation(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        self.active_station = 0
        self.remaining_runtime_sec = 0
        self.manual_queue_count = 0
        self.auto_queue_count = 0
        self.queue.clear()
        self.queued_entries.clear()
        return self._ack(d)

    def _op_advance_station(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        if len(self.queued_entries) > 1:
            self.queued_entries.pop(0)
            nxt = self.queued_entries[0]
            self.active_station = int(nxt["station_id"])
            self.remaining_runtime_sec = int(nxt["remaining_seconds"])
            self.manual_queue_count = len(self.queued_entries)
        elif self.queue:
            item = self.queue.pop(0)
            if isinstance(item, dict):
                self.active_station = int(item["station"])
                self.remaining_runtime_sec = int(item.get("seconds", 0))
            else:
                self.active_station = int(item)
        else:
            self.active_station = 0
            self.remaining_runtime_sec = 0
            self.manual_queue_count = 0
            self.queued_entries.clear()
        return self._ack(d)

    def _op_current_irrigation_state(self, d: str, bl: int, _t: str | None) -> str:
        return f"C8{self.controller_state & 0xFF:02X}" if bl == 1 else self._nak(d, 2)

    def _op_set_controller_state(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        self.controller_state = int(d[2:4], 16)
        self.controller_state_str = "Auto" if self.controller_state == 1 else "Off"
        return self._ack(d)

    def _op_event_timestamp(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        ev = int(d[2:4], 16)
        return f"CA{ev:02X}{self.event_timestamps.get(ev, 0) & 0xFFFFFFFF:08X}"

    def _op_stack_manual_run(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 4:
            return self._nak(d, 2)
        self._enqueue_manual_run(int(d[4:6], 16), int(d[6:8], 16) * 60)
        return self._ack(d)

    def _op_combined_controller_state(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        if not self.profile.combined_controller_state and not (
            self.supported_commands and "4C" in self.supported_commands
        ):
            return self._nak(d, 1)
        dh = self._pack_date_3bytes_hex(self.day, self.month, self.year)
        return (
            f"CC{self.hour & 0xFF:02X}{self.minute & 0xFF:02X}{self.second & 0xFF:02X}"
            f"{dh}{self.rain_delay_days & 0xFFFF:04X}"
            f"{self.sensor_state & 0xFF:02X}{self.controller_state & 0xFF:02X}"
            f"{self.seasonal_adjust & 0xFFFF:04X}"
            f"{self.remaining_runtime_sec & 0xFFFF:04X}"
            f"{self.active_station & 0xFF:02X}"
        )

    def _op_irrigation_statistics(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 3:
            return self._nak(d, 2)
        page, stn = int(d[2:4], 16), int(d[4:6], 16)
        if page == 0:
            st = self.stats_page0.get(stn, {"programmed": 0, "applied": 0})
            return f"CD00{stn:02X}{st['programmed'] & 0xFFFF:04X}{st['applied'] & 0xFFFF:04X}"
        arr = self.stats_monthly.get((page, stn), [0] * 12)
        return f"CD{page:02X}{stn:02X}" + "".join(f"{m & 0xFFFF:04X}" for m in arr[:12])
