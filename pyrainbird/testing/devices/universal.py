"""UniversalCDTDevice for ESP_ME3, RC2, ARC8, ESP_2WIRE, LX_ME2, and LX_IVM*."""

from __future__ import annotations

import struct
from collections.abc import Callable
from typing import Any

from .base import SipHandler
from .cdt_store import CDTStore
from .constants import (
    ALARM_STATUS_MASKS,
    DISCOVERY_PROGRESS_STATUS_CODES,
    MANUAL_RUN_SOURCE_NAMES,
    PROGRAM_SOURCE_CODES,
    STATION_STATE_CODES,
    WEATHER_SENSOR_STATUS_CODES,
)
from .legacy_sip import UpgradedTM2Device
from .state import init_ble_state, init_universal_state

UniRes = tuple[str, str]
UniHandler = Callable[[str, bytes], UniRes]


class UniversalCDTDevice(UpgradedTM2Device):
    """Universal CDT/UPT controller emulator routing 0x0C/0x80 commands across subsystems and CDT blocks."""

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
        handlers["0C"] = self._op_universal_envelope
        handlers["80"] = self._op_universal_envelope
        handlers["61"] = self._op_cancel_flow_learn_61
        return handlers

    def _op_universal_envelope(self, d: str, _bl: int, _t: str | None) -> str:
        return self.handle_universal(d)

    def handle_sip(self, payload_hex: str, *, transport: str | None = None) -> str:
        resp = super().handle_sip(payload_hex, transport=transport)
        if not payload_hex.strip().upper().startswith(("0C", "80")):
            self.cdt_engine.sync_from_device()
        return resp

    def _op_cancel_flow_learn_61(self, data: str, bl: int, _tr: str | None) -> str:
        if bl != 1:
            return self._nak(data, 2)
        self.flow_learn_active = False
        self.flow_learn_state = 0
        return self._ack(data)

    def _build_universal_handlers(self) -> dict[str, UniHandler]:
        return {
            "070B": self._uni_data_bunch_get,
            "0207": self._uni_data_bunch_get,
            "050B": self._uni_data_bunch_set,
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
        if len(data) < 50:
            return "000C02"
        header_21b_hex = data[:42]
        req_opcode = data[46:50]
        req_body = bytes.fromhex(data[50:])

        handler = self._universal_handlers.get(req_opcode)
        if handler is None:
            resp_opcode, resp_body_hex = "0100", "03"
        else:
            resp_opcode, resp_body_hex = handler(req_opcode, req_body)

        total_len = 2 + (len(resp_body_hex) // 2)
        len_le_hex = struct.pack("<H", total_len).hex().upper()
        return f"{header_21b_hex}{len_le_hex}{resp_opcode}{resp_body_hex}"

    # --- 1. Subsystem 0x0C (CDT data table) ---

    def _uni_data_bunch_get(self, op: str, body: bytes) -> UniRes:
        return ("080B" if op == "070B" else "0307"), self.cdt_engine.handle_bunch_get(
            body
        )

    def _uni_data_bunch_set(self, op: str, body: bytes) -> UniRes:
        return ("060B" if op == "050B" else "0607"), self.cdt_engine.handle_bunch_set(
            body
        )

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
        if len(body) >= 7:
            self.year = struct.unpack("<H", body[0:2])[0]
            self.month, self.day = body[2], body[3]
            self.hour, self.minute, self.second = body[4], body[5], body[6]
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
        if len(body) >= 2:
            self.uni_irrigation_queue.append(
                {
                    "program": body[1],
                    "source": MANUAL_RUN_SOURCE_NAMES.get(body[0], "FROM_REMOTE"),
                }
            )
        return "0B20", "00"

    def _uni_stop_program(self, op: str, _body: bytes) -> UniRes:
        self.uni_irrigation_queue.clear()
        self.active_station = 0
        return ("0720" if op == "0620" else "0920"), "00"

    def _uni_manually_run_station(self, _op: str, _body: bytes) -> UniRes:
        return "0320", "00"

    def _uni_stop_single_station(self, _op: str, _body: bytes) -> UniRes:
        return "0520", "00"

    def _uni_advance_station(self, _op: str, _body: bytes) -> UniRes:
        if self.uni_irrigation_queue:
            self.uni_irrigation_queue.pop(0)
        return "0D20", "00"

    def _uni_advance_delay_soak(self, _op: str, _body: bytes) -> UniRes:
        return "0F20", "00"

    def _uni_set_mv_open_duration(self, _op: str, body: bytes) -> UniRes:
        if len(body) >= 2:
            self.mv_manual_open_duration_minutes = struct.unpack("<H", body[0:2])[0]
        return "6820", "00"

    def _uni_get_mv_open_duration(self, _op: str, _body: bytes) -> UniRes:
        if (
            not self.profile.master_valves_settings
            and "mv_manual_open_duration_minutes" not in self._applied_state
        ):
            return "0100", "03"
        dur_le = (
            struct.pack("<H", self.mv_manual_open_duration_minutes & 0xFFFF)
            .hex()
            .upper()
        )
        return "4D20", dur_le

    def _uni_get_mv_status(self, _op: str, _body: bytes) -> UniRes:
        return "6320", "01" if self.mv_open_status else "00"

    def _uni_initiate_flow_learn(self, _op: str, _body: bytes) -> UniRes:
        self.flow_learn_active = True
        return "3020", "00"

    def _uni_cancel_flow_learn(self, _op: str, _body: bytes) -> UniRes:
        self.flow_learn_active = False
        return "2E20", "00"

    def _uni_get_flow_totalizers(self, _op: str, _body: bytes) -> UniRes:
        ft = self.flow_totalizer
        body = struct.pack(
            "<IIII",
            int(ft.get("current_month", 0)),
            int(ft.get("previous_month", 0)),
            int(ft.get("last_30_days", 0)),
            int(ft.get("previous_30_days", 0)),
        )
        return "4F20", body.hex().upper()

    def _uni_clear_flow_totalizers(self, _op: str, _body: bytes) -> UniRes:
        self.flow_totalizer = {
            "current_month": 0,
            "previous_month": 0,
            "last_30_days": 0,
            "previous_30_days": 0,
        }
        return "5120", "00"

    def _uni_get_current_flow_rates(self, _op: str, _body: bytes) -> UniRes:
        buf = bytearray(struct.pack("<I", len(self.current_flow_rates_gpm)))
        for rate in self.current_flow_rates_gpm:
            buf.extend(struct.pack("<f", float(rate)))
        return "6520", buf.hex().upper()

    def _uni_get_irrigation_queue(self, _op: str, _body: bytes) -> UniRes:
        records = bytearray([0x00, 0x00, len(self.uni_irrigation_queue) & 0xFF])
        for rec in self.uni_irrigation_queue:
            stn_idx = max(0, int(rec.get("station_number", 1)) - 1)
            st_val = rec.get("state", "Cycling")
            st_code = (
                STATION_STATE_CODES.get(st_val, 2)
                if isinstance(st_val, str)
                else int(st_val)
            )
            prog_num = rec.get("program_number")
            prog_byte = 0xFF if prog_num is None else int(prog_num) & 0xFF
            src_val = rec.get("program_source", "AutoProgram")
            src_code = (
                PROGRAM_SOURCE_CODES.get(src_val, 7)
                if isinstance(src_val, str)
                else int(src_val)
            )
            rem_t = int(rec.get("remaining_state_time_s", 0))
            sec_t = int(rec.get("secondary_time_s", rem_t))
            records.extend(
                struct.pack(
                    "<HBBBII", stn_idx, st_code, prog_byte, src_code, rem_t, sec_t
                )
            )
        return "6720", records.hex().upper()

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

    # --- 6. Subsystem 0x04 (field devices & 2-wire) ---

    def _uni_set_raster_test(self, _op: str, body: bytes) -> UniRes:
        if body:
            active = body[0] == 1
            self.uni_raster_test["active"] = active
            self.uni_raster_test["progress"] = 0 if active else 100
        return "3609", "01"

    def _uni_get_raster_test_status(self, _op: str, _body: bytes) -> UniRes:
        is_act = 1 if self.uni_raster_test.get("active", False) else 0
        prog = int(self.uni_raster_test.get("progress", 100)) & 0xFF
        stn_bytes, short_bytes = bytearray(3), bytearray(3)
        for s in self.uni_raster_test.get("open_stations", []):
            s_idx = int(s) - 1
            if 0 <= s_idx < 24:
                stn_bytes[s_idx // 8] |= 1 << (s_idx % 8)
        for s in self.uni_raster_test.get("shorted_stations", []):
            s_idx = int(s) - 1
            if 0 <= s_idx < 24:
                short_bytes[s_idx // 8] |= 1 << (s_idx % 8)
        body = (
            f"{is_act:02X}{prog:02X}00000000000000"
            f"0000{short_bytes.hex().upper()}{stn_bytes.hex().upper()}0000"
        )
        return "3809", body

    def _uni_ping_device_setup_polling(self, _op: str, body: bytes) -> UniRes:
        if len(body) >= 3:
            self.ping_polling_target = {
                "device_number": struct.unpack("<H", body[0:2])[0],
                "device_type": body[2],
            }
        return "3209", "00"

    def _uni_ping_device(self, op: str, _body: bytes) -> UniRes:
        lp = self.last_ping
        volt_byte = round(float(lp.get("voltage", 28.5)) / 0.25) & 0xFF
        rec = struct.pack(
            "<HBHB6sB",
            int(lp.get("device_number", 1)),
            int(lp.get("device_type", 1)),
            int(lp.get("address", 1001)),
            1 if lp.get("status", True) else 0,
            b"\x00" * 6,
            volt_byte,
        )
        if op == "3309":
            return "3409", f"{1 if lp.get('ready', True) else 0:02X}{rec.hex().upper()}"
        return "1E09", rec.hex().upper()

    def _uni_get_weather_sensor_status(self, _op: str, _body: bytes) -> UniRes:
        codes = [
            WEATHER_SENSOR_STATUS_CODES.get(s, 1) for s in self.weather_sensor_status
        ]
        return "3C09", bytes([len(codes), *codes]).hex().upper()

    def _uni_get_discovery_progress(self, _op: str, _body: bytes) -> UniRes:
        st_str = str(self.discovery.get("status", "DISCOVERY_COMPLETED"))
        st_code = DISCOVERY_PROGRESS_STATUS_CODES.get(st_str, 2)
        pct = int(self.discovery.get("percent_complete", 100)) & 0xFF
        return "4D09", f"{st_code:02X}{pct:02X}"

    def _uni_get_two_wire_line_survey(self, _op: str, _body: bytes) -> UniRes:
        ls = self.line_survey
        peak_raw = int(ls.get("peak_voltage_v", 28)) * 10
        curr_ma = int(ls.get("current_ma", 45))
        lim_raw = int(ls.get("limit_threshold_ma", 800)) // 10
        buf = bytearray(18)
        for off, val in (
            (0, peak_raw),
            (2, 272),
            (4, peak_raw),
            (6, 272),
            (8, curr_ma),
            (10, peak_raw),
            (12, curr_ma),
        ):
            struct.pack_into("<H", buf, off, val)
        buf[14], buf[17] = 0x30, lim_raw & 0xFF
        return "3009", buf.hex().upper()

    def _uni_get_responding_or_not_device(self, op: str, _body: bytes) -> UniRes:
        nr = self.not_responding
        masks = []
        for k in ("weather", "flow", "mv", "pump", "stations"):
            m = 0
            for idx in nr.get(k, []):
                m |= 1 << (int(idx) - 1)
            masks.append(m)
        buf = struct.pack("<BBBHHBBH", 0, 1, 2, *masks)
        return ("2109" if op == "2009" else "2309"), buf.hex().upper()

    def _uni_get_short_status(self, _op: str, _body: bytes) -> UniRes:
        return "4309", "00000000"

    def _uni_get_discovery_results(self, _op: str, body: bytes) -> UniRes:
        page = body[0] if body else 0
        devs = self.discovery.get("devices", [])
        buf = bytearray(struct.pack("<BH", page, len(devs)))
        for d_rec in devs[:16]:
            buf.extend(
                struct.pack(
                    "<BHHB",
                    int(d_rec.get("assignment", 1)),
                    int(d_rec.get("device_index", 1)),
                    int(d_rec.get("address", 1001)),
                    int(d_rec.get("status", 0)),
                )
            )
        if len(devs) < 16:
            buf.extend(b"\x00" * 6)
        return "4F09", buf.hex().upper()

    # --- 7. Subsystem 0x05 (module diagnostics) & 8. Subsystem 0x0D (module firmware) ---

    def _uni_ac_current_test(self, _op: str, body: bytes) -> UniRes:
        if len(body) >= 2:
            self.ac_current_test["path"] = body[0]
            self.ac_current_test["source_on"] = body[1] == 1
        return "2050", "00"

    def _uni_get_segment_info(self, _op: str, _body: bytes) -> UniRes:
        si = self.segment_info
        buf = struct.pack(
            "<BBBI",
            int(si.get("diagnostic_mode", 0)),
            int(si.get("shorted_map", 0)),
            int(si.get("test_path", 0)),
            int(si.get("current", 0)),
        )
        return "2250", buf.hex().upper()

    def _uni_set_diagnostic_mode(self, _op: str, body: bytes) -> UniRes:
        if body:
            self.segment_info["diagnostic_mode"] = body[0]
        return "2450", "00"

    def _uni_get_module_list(self, _op: str, _body: bytes) -> UniRes:
        return "250B", f"00000000{self.module_info_address}"

    def _uni_get_module_info(self, _op: str, _body: bytes) -> UniRes:
        hdr, rec = bytearray(12), bytearray(42)
        hdr[11] = 1
        struct.pack_into("<I", rec, 0, 458753)
        struct.pack_into("<I", rec, 4, 321)
        struct.pack_into("<H", rec, 9, self.fw_major)
        struct.pack_into("<H", rec, 11, self.fw_minor)
        return "230B", (hdr + rec).hex().upper()
