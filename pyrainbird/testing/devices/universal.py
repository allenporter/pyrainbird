"""UniversalCDTDevice for ESP_ME3, RC2, ARC8, ESP_2WIRE, LX_ME2, and LX_IVM*.

How Universal Controllers Work
------------------------------
Universal controllers inherit basic status and manual-control commands from
`BaseControllerDevice` (such as model ID, active station, rain delay, and
seasonal adjust), disable the legacy fixed-page schedule commands (`0x20`,
`0x21`), and tunnel a structured sub-protocol inside SIP command `0x0C`
(response `0x8C`).

Incoming Universal messages address either:
1. **The Controller Data Table (`CDTStore` in `cdt_store.py`)**: The
   controller's indexed configuration database holding schedules, runtimes,
   sensor bypasses, and hardware options (`0x0C` subsystem).
2. **Runtime Subsystems**: Live operational handlers for system clock and
   timezone (`0x03`), live irrigation queue and flow totalizers (`0x09` in
   `universal_irrigation.py`), controller mode and alarms (`0x13`), front-panel
   session lock (`0x18`), and 2-wire/module diagnostics (`0x04`, `0x05`, `0x0D`
   in `universal_diagnostics.py`).

Two settings — Rain Delay and per-program Seasonal Adjust — are reachable
through both legacy SIP commands (`0x36`/`0x37`, `0x30`/`0x31`) and CDT tables
(`1400`, `1800`), reading and updating the same controller state directly.
"""

from __future__ import annotations

import struct
from collections.abc import Callable
from typing import Any

from .base import BaseControllerDevice, SipHandler
from .cdt_store import CDTStore
from .constants import ALARM_STATUS_MASKS
from .state import init_ble_state, init_universal_state
from .universal_diagnostics import (
    handle_uni_ac_current_test,
    handle_uni_get_discovery_progress,
    handle_uni_get_discovery_results,
    handle_uni_get_module_info,
    handle_uni_get_module_list,
    handle_uni_get_raster_test_status,
    handle_uni_get_responding_devices,
    handle_uni_get_segment_info,
    handle_uni_get_two_wire_line_survey,
    handle_uni_get_weather_sensor_status,
    handle_uni_ping_device,
    handle_uni_ping_device_setup,
    handle_uni_set_diagnostic_mode,
    handle_uni_set_raster_test,
)
from .universal_irrigation import (
    collect_universal_program_stations,
    format_uni_irrigation_queue_6720,
    format_universal_sip_queue_bb,
    handle_uni_advance_station,
    handle_uni_clear_flow_totalizers,
    handle_uni_get_current_flow_rates,
    handle_uni_get_flow_totalizers,
    handle_uni_get_mv_open_duration,
    handle_uni_run_program,
    handle_uni_run_station,
    handle_uni_stop_all,
    handle_uni_stop_station,
    record_sip_manual_run_in_queue,
    refresh_active_station_state,
)

UniRes = tuple[str, str]
UniHandler = Callable[[str, bytes], UniRes]

_CDT_GET_RESP_MAP = {"070B": "080B", "030B": "040B", "0207": "0307"}
_CDT_SET_RESP_MAP = {"050B": "060B", "010B": "020B", "0507": "0607"}


class UniversalCDTDevice(BaseControllerDevice):
    """Universal controller emulator routing Core SIP and 0x0C subsystem/CDT commands."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.cdt_engine: CDTStore = CDTStore(self)
        self._universal_handlers: dict[str, UniHandler] = (
            self._build_universal_handlers()
        )
        super().__init__(*args, **kwargs)

    def _init_device_state(self) -> None:
        super()._init_device_state()
        init_universal_state(self)
        init_ble_state(self)

    def _build_sip_handlers(self) -> dict[str, SipHandler]:
        handlers = super()._build_sip_handlers()
        for unsupported in ("20", "21", "32", "33"):
            handlers.pop(unsupported, None)
        for cmd, ok in (
            ("49", self.profile.controller_state_set),
            ("4A", self.profile.schedule_timestamp),
            ("4B", self.profile.stack_manual_run_station),
            ("4C", self.profile.combined_controller_state),
        ):
            if not ok:
                handlers.pop(cmd, None)
        handlers["0C"] = self._op_universal_envelope
        handlers["80"] = self._op_universal_envelope
        handlers["61"] = self._op_cancel_flow_learn_61
        return handlers

    def _op_universal_envelope(self, d: str, _bl: int, _t: str | None) -> str:
        return self.handle_universal(d)

    def handle_sip(self, payload_hex: str, *, transport: str | None = None) -> str:
        cmd = payload_hex.strip().upper()[:2]
        if cmd == "39":
            self.queue.clear()
            self.queued_entries.clear()
        resp = super().handle_sip(payload_hex, transport=transport)
        if resp.startswith("01") and cmd in ("2B", "2C", "39", "3A", "4B"):
            record_sip_manual_run_in_queue(self)
        return resp

    def _op_rain_delay(self, d: str, bl: int, _t: str | None) -> str:
        rd = int(self.cdt_store.get("1400", self.rain_delay_days)) & 0xFFFF
        return f"B6{rd:04X}" if bl == 1 else self._nak(d, 2)

    def _op_set_rain_delay(self, d: str, bl: int, _t: str | None) -> str:
        resp = super()._op_set_rain_delay(d, bl, _t)
        if resp.startswith("01") and "1400" in self.cdt_store:
            self.cdt_store["1400"] = self.rain_delay_days
        return resp

    def _op_water_budget(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        prog = int(d[2:4], 16)
        if prog >= max(1, self.profile.maximum_programs):
            return self._nak(d, 4)
        tbl = self.cdt_store.get("1800")
        pct = (
            int(tbl[prog])
            if isinstance(tbl, list) and prog < len(tbl)
            else self.water_budget.get(prog, self.seasonal_adjust)
        )
        return f"B0{prog & 0xFF:02X}{pct & 0xFFFF:04X}"

    def _on_water_budget_updated(self, prog: int, pct: int) -> None:
        tbl = self.cdt_store.get("1800")
        if isinstance(tbl, list) and prog < len(tbl):
            tbl[prog] = pct

    def _collect_program_runnable_stations(self, prog: int) -> list[tuple[int, int]]:
        return collect_universal_program_stations(self, prog)

    def _op_manually_run_program(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        prog = int(d[2:4], 16)
        if prog >= self.profile.maximum_programs:
            return self._nak(d, 4)
        handle_uni_run_program(self, bytes([0x01, prog]))
        return self._ack(d)

    def _op_stop_irrigation(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 1:
            return self._nak(d, 2)
        self.uni_irrigation_queue.clear()
        refresh_active_station_state(self)
        return self._ack(d)

    def _op_advance_station(self, d: str, bl: int, _t: str | None) -> str:
        if bl != 2:
            return self._nak(d, 2)
        if not self.uni_irrigation_queue:
            return super()._op_advance_station(d, bl, _t)
        handle_uni_advance_station(self)
        return self._ack(d)

    def _handle_current_queue(self, page: int) -> str:
        return format_universal_sip_queue_bb(self, page)

    def _op_cancel_flow_learn_61(self, data: str, bl: int, _tr: str | None) -> str:
        if bl != 1:
            return self._nak(data, 2)
        self.flow_learn_active = False
        self.flow_learn_state = 0
        return self._ack(data)

    def _build_universal_handlers(self) -> dict[str, UniHandler]:
        return {
            "070B": self._uni_data_bunch_get,
            "030B": self._uni_data_bunch_get,
            "0207": self._uni_data_bunch_get,
            "050B": self._uni_data_bunch_set,
            "010B": self._uni_data_bunch_set,
            "0507": self._uni_data_bunch_set,
            "1B0B": self._uni_data_bunch_get_same,
            "0407": self._uni_data_bunch_get_same,
            "0405": self._uni_get_calendar,
            "0605": self._uni_set_calendar,
            "0905": self._uni_set_timezone,
            "0B05": self._uni_get_timezone,
            "0D05": self._uni_set_prevent_sntp,
            "0F05": self._uni_get_prevent_sntp,
            "0A20": self._uni_manually_run_program,
            "0620": self._uni_stop_program,
            "0820": self._uni_stop_program,
            "0220": self._uni_manually_run_station,
            "0420": self._uni_stop_single_station,
            "0C20": self._uni_advance_station,
            "0E20": self._uni_advance_delay_soak,
            "4B20": self._uni_set_mv_open_duration,
            "4C20": self._uni_get_mv_open_duration,
            "6220": self._uni_get_mv_status,
            "2F20": self._uni_initiate_flow_learn,
            "2D20": self._uni_cancel_flow_learn,
            "4E20": self._uni_get_flow_totalizers,
            "5020": self._uni_clear_flow_totalizers,
            "6420": self._uni_get_current_flow_rates,
            "6620": self._uni_get_irrigation_queue,
            "0A30": self._uni_get_controller_state,
            "2D30": self._uni_set_controller_state,
            "1330": self._uni_get_alarm_status,
            "0114": self._uni_session_start,
            "0314": self._uni_session_end,
            "0714": self._uni_session_beacon,
            "3509": self._uni_set_raster_test,
            "3709": self._uni_get_raster_test_status,
            "3109": self._uni_ping_device_setup_polling,
            "1D09": self._uni_ping_device,
            "3309": self._uni_ping_device,
            "3B09": self._uni_get_weather_sensor_status,
            "4C09": self._uni_get_discovery_progress,
            "2F09": self._uni_get_two_wire_line_survey,
            "2009": self._uni_get_responding_or_not_device,
            "2209": self._uni_get_responding_or_not_device,
            "4209": self._uni_get_short_status,
            "4E09": self._uni_get_discovery_results,
            "1F50": self._uni_ac_current_test,
            "2150": self._uni_get_segment_info,
            "2350": self._uni_set_diagnostic_mode,
            "240B": self._uni_get_module_list,
            "220B": self._uni_get_module_info,
        }

    def handle_universal(self, payload_hex: str) -> str:
        """Dispatch Universal (0x0C / 0x80) messages via _universal_handlers."""
        data = payload_hex.strip().upper()
        if len(data) < 50 or len(data) % 2 != 0:
            return "000C02"
        try:
            raw_bytes = bytes.fromhex(data)
        except ValueError:
            return "000C02"
        declared_len = struct.unpack("<H", raw_bytes[21:23])[0]
        if declared_len != len(raw_bytes) - 23 or declared_len < 2:
            return "000C02"

        header_21b_hex = data[:42]
        req_opcode = data[46:50]
        req_body = raw_bytes[25:]

        handler = self._universal_handlers.get(req_opcode)
        if handler is None:
            resp_opcode, resp_body_hex = "0100", "03"
        else:
            resp_opcode, resp_body_hex = handler(req_opcode, req_body)

        total_len = 2 + (len(resp_body_hex) // 2)
        len_le_hex = struct.pack("<H", total_len).hex().upper()
        resp_hdr = (
            f"8C{header_21b_hex[2:]}"
            if header_21b_hex.startswith("0C")
            else header_21b_hex
        )
        return f"{resp_hdr}{len_le_hex}{resp_opcode}{resp_body_hex}"

    # --- 1. Subsystem 0x0C (CDT data table) ---

    def _uni_data_bunch_get(self, op: str, body: bytes) -> UniRes:
        return _CDT_GET_RESP_MAP.get(op, "080B"), self.cdt_engine.handle_bunch_get(body)

    def _uni_data_bunch_set(self, op: str, body: bytes) -> UniRes:
        return _CDT_SET_RESP_MAP.get(op, "060B"), self.cdt_engine.handle_bunch_set(body)

    def _uni_data_bunch_get_same(self, op: str, body: bytes) -> UniRes:
        return (
            "1C0B" if op == "1B0B" else "0307"
        ), self.cdt_engine.handle_bunch_get_same(body)

    # --- 2. Subsystem 0x03 (system time) ---

    def _uni_get_calendar(self, _op: str, _body: bytes) -> UniRes:
        year_le = struct.pack("<H", self.year & 0xFFFF).hex().upper()
        body = (
            f"{year_le}{self.month & 0xFF:02X}{self.day & 0xFF:02X}"
            f"{self.hour & 0xFF:02X}{self.minute & 0xFF:02X}{self.second & 0xFF:02X}"
        )
        return "0505", body

    def _uni_set_calendar(self, _op: str, body: bytes) -> UniRes:
        if len(body) < 7:
            return "0705", "01"
        yr = struct.unpack("<H", body[0:2])[0]
        mo, dy, hr, mn, sc = body[2], body[3], body[4], body[5], body[6]
        if not (1 <= mo <= 12 and 1 <= dy <= 31 and hr <= 23 and mn <= 59 and sc <= 59):
            return "0705", "01"
        self.year, self.month, self.day = yr, mo, dy
        self.hour, self.minute, self.second = hr, mn, sc
        return "0705", "00"

    def _uni_set_timezone(self, _op: str, body: bytes) -> UniRes:
        self.posix_timezone = body.rstrip(b"\x00").decode("utf-8", errors="ignore")
        return "0A05", "00"

    def _uni_get_timezone(self, _op: str, _body: bytes) -> UniRes:
        return "0C05", (self.posix_timezone.encode("utf-8") + b"\x00").hex().upper()

    def _uni_set_prevent_sntp(self, _op: str, body: bytes) -> UniRes:
        if body:
            self.prevent_sntp_updates = body[0] == 1
        return "0E05", "00"

    def _uni_get_prevent_sntp(self, _op: str, _body: bytes) -> UniRes:
        return "1005", "01" if self.prevent_sntp_updates else "00"

    # --- 3. Subsystem 0x09 (irrigation control) ---

    def _uni_manually_run_program(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_run_program(self, body)

    def _uni_stop_program(self, op: str, _body: bytes) -> UniRes:
        return handle_uni_stop_all(self, op)

    def _uni_manually_run_station(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_run_station(self, body)

    def _uni_stop_single_station(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_stop_station(self, body)

    def _uni_advance_station(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_advance_station(self)

    def _uni_advance_delay_soak(self, _op: str, _body: bytes) -> UniRes:
        return "0F20", "00"

    def _uni_set_mv_open_duration(self, _op: str, body: bytes) -> UniRes:
        if len(body) >= 2:
            self.mv_manual_open_duration_minutes = struct.unpack("<H", body[0:2])[0]
        return "6820", "00"

    def _uni_get_mv_open_duration(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_mv_open_duration(self)

    def _uni_get_mv_status(self, _op: str, _body: bytes) -> UniRes:
        return "6320", "01" if self.mv_open_status else "00"

    def _uni_initiate_flow_learn(self, _op: str, _body: bytes) -> UniRes:
        self.flow_learn_active = True
        return "3020", "00"

    def _uni_cancel_flow_learn(self, _op: str, _body: bytes) -> UniRes:
        self.flow_learn_active = False
        return "2E20", "00"

    def _uni_get_flow_totalizers(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_flow_totalizers(self)

    def _uni_clear_flow_totalizers(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_clear_flow_totalizers(self)

    def _uni_get_current_flow_rates(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_current_flow_rates(self)

    def _uni_get_irrigation_queue(self, _op: str, body: bytes) -> UniRes:
        return format_uni_irrigation_queue_6720(self, body)

    # --- 4. Subsystem 0x13 (controller status & alarms) & 5. Subsystem 0x18 (panel session) ---

    def _uni_get_controller_state(self, _op: str, _body: bytes) -> UniRes:
        uni_val = 0x00 if self.controller_state_str.lower() == "auto" else 0x01
        return "0B30", f"00{uni_val:02X}00"

    def _uni_set_controller_state(self, _op: str, body: bytes) -> UniRes:
        if body:
            self.controller_state_str = "Auto" if body[0] == 2 else "Off"
            self.controller_state = 1 if body[0] == 2 else 0
        return "2E30", "00"

    def _uni_get_alarm_status(self, _op: str, _body: bytes) -> UniRes:
        mask = 0
        for alarm_name in self.alarms:
            mask |= ALARM_STATUS_MASKS.get(str(alarm_name), 0)
        return "1430", struct.pack("<Q", mask).hex().upper()

    def _uni_session_start(self, _op: str, body: bytes) -> UniRes:
        self.front_panel_locked = True
        ref_id_hex = body[:8].hex().upper() if len(body) >= 8 else "0102030405060708"
        return "0214", f"{ref_id_hex}{self.session_id}00"

    def _uni_session_end(self, _op: str, _body: bytes) -> UniRes:
        self.front_panel_locked = False
        return "0414", "00"

    def _uni_session_beacon(self, _op: str, _body: bytes) -> UniRes:
        return "0814", "00"

    # --- 6. Subsystems 0x04 (field/2-wire), 0x05 (diagnostics), 0x0D (modules) ---

    def _uni_set_raster_test(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_set_raster_test(self, body)

    def _uni_get_raster_test_status(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_raster_test_status(self)

    def _uni_ping_device_setup_polling(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_ping_device_setup(self, body)

    def _uni_ping_device(self, op: str, _body: bytes) -> UniRes:
        return handle_uni_ping_device(self, op)

    def _uni_get_weather_sensor_status(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_weather_sensor_status(self)

    def _uni_get_discovery_progress(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_discovery_progress(self)

    def _uni_get_two_wire_line_survey(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_two_wire_line_survey(self)

    def _uni_get_responding_or_not_device(self, op: str, _body: bytes) -> UniRes:
        return handle_uni_get_responding_devices(self, op)

    def _uni_get_short_status(self, _op: str, _body: bytes) -> UniRes:
        return "4309", "00000000"

    def _uni_get_discovery_results(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_get_discovery_results(self, body)

    def _uni_ac_current_test(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_ac_current_test(self, body)

    def _uni_get_segment_info(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_segment_info(self)

    def _uni_set_diagnostic_mode(self, _op: str, body: bytes) -> UniRes:
        return handle_uni_set_diagnostic_mode(self, body)

    def _uni_get_module_list(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_module_list(self)

    def _uni_get_module_info(self, _op: str, _body: bytes) -> UniRes:
        return handle_uni_get_module_info(self)
