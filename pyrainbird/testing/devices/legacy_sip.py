"""LegacyProgramDevice (ESP_ME*, ESP_TM2) and UpgradedTM2Device (ESP_TM2v2/v3, TM2R, TRU)."""

from __future__ import annotations

from ..profiles import ProtocolFamily
from .base import BaseControllerDevice
from .state import ProgramScheduleConfig, init_schedule_state


class LegacyProgramDevice(BaseControllerDevice):
    """Program-centric SIP controller emulator for ESP-ME, ESP-MEv2, and ESP-TM2."""

    def _init_device_state(self) -> None:
        super()._init_device_state()
        init_schedule_state(self)

    def _is_ble_schedule_format(self) -> bool:
        return self.profile.is_battery_based or self.profile.protocol_family in (
            ProtocolFamily.BLE_CBOS,
            ProtocolFamily.BLE_SOLEM,
        )

    def _handle_retrieve_schedule(self, page_id: int) -> str:
        """Dispatch schedule read (0x20 -> 0xA0) subpages."""
        if page_id == 0x0000:
            return self._retrieve_page_0000()
        if page_id == 0x0008:
            return self._retrieve_page_0008()
        if 0x0010 <= page_id <= 0x0013:
            return self._retrieve_program_config(page_id)
        if page_id in (0x0020, 0x0040):
            return self._retrieve_station_flags(page_id)
        if 0x0060 <= page_id <= 0x0063:
            return self._retrieve_start_times(page_id)
        if page_id in (0x0084, 0x0085) and self._supports_calendar_days_off_page():
            return self._retrieve_calendar_days_off(page_id)
        if 0x0080 <= page_id <= 0x008A:
            return self._retrieve_station_run_times(page_id)
        return "002002"

    def _supports_calendar_days_off_page(self) -> bool:
        return (
            self._is_ble_schedule_format()
            or self.profile.is_isk_controller
            or "calendar_days_off_11_15" in self._applied_state
            or "calendar_days_off_page_1" in self._applied_state
        )

    def _retrieve_page_0000(self) -> str:
        delay_hex = f"{self.inter_station_delay_seconds & 0xFFFF:04X}"
        rd_hex = f"{self.rain_delay_days & 0xFF:02X}"
        bypass_hex = "01" if self.rain_sensor_bypassed else "00"
        if self._is_ble_schedule_format():
            mv_hex = "01" if self.master_valve_enable else "00"
            settle_hex = f"{self.rain_settling_time_minutes & 0xFF:02X}"
            return f"A00000{delay_hex}{rd_hex}{bypass_hex}{mv_hex}{settle_hex}"
        return f"A00000{delay_hex}{rd_hex}{bypass_hex}"

    def _retrieve_page_0008(self) -> str:
        entries_hex = "".join(
            f"{int(e['soak_seconds']) & 0xFFFF:04X}{int(e['cycle_seconds']) & 0xFFFF:04X}"
            for e in self.station_cycle_soak
        )
        return f"A00008{entries_hex}"

    def _retrieve_program_config(self, page_id: int) -> str:
        p_num = page_id - 0x000F
        prog = self.programs.get(p_num, ProgramScheduleConfig())
        if self._is_ble_schedule_format():
            return (
                f"A0{page_id:04X}"
                f"{prog.custom_days_mask & 0xFF:02X}"
                f"{prog.cyclic_days & 0xFF:02X}"
                f"{prog.days_remaining & 0xFF:02X}"
                f"{prog.permanent_days_off & 0xFF:02X}"
                f"{prog.seasonal_adjust & 0xFFFF:04X}"
                f"{prog.water_cycle & 0xFF:02X}"
                f"{'01' if prog.auto_restart else '00'}"
            )
        return (
            f"A0{page_id:04X}"
            f"{prog.custom_days_mask & 0xFF:02X}"
            f"{prog.cyclic_days & 0xFF:02X}"
            f"{prog.days_remaining & 0xFF:02X}"
            f"{prog.permanent_days_off & 0xFF:02X}"
            f"{prog.seasonal_adjust & 0xFF:02X}"
            f"{prog.water_cycle & 0xFF:02X}"
        )

    def _retrieve_station_flags(self, page_id: int) -> str:
        flags = (
            self.station_rain_sensor_obey
            if page_id == 0x0020
            else self.station_mv_enable
        )
        flags_hex = "".join("01" if flag else "00" for flag in flags)
        return f"A0{page_id:04X}{flags_hex}"

    def _retrieve_start_times(self, page_id: int) -> str:
        p_num = page_id - 0x005F
        prog = self.programs.get(p_num, ProgramScheduleConfig())
        slot_count = (
            8 if self._is_ble_schedule_format() else self.profile.maximum_start_times
        )
        slots = list(prog.start_times_minutes[:slot_count])
        while len(slots) < slot_count:
            slots.append(0xFFFF)
        slots_hex = "".join(
            f"{(s if 0 <= s < 1440 else 0xFFFF) & 0xFFFF:04X}" for s in slots
        )
        return f"A0{page_id:04X}{slots_hex}"

    def _retrieve_calendar_days_off(self, page_id: int) -> str:
        slots = (
            self.calendar_days_off[:10]
            if page_id == 0x0084
            else self.calendar_days_off[10:15]
        )
        tuples_hex = ""
        for entry in slots:
            if not entry:
                tuples_hex += "000000"
            else:
                m = int(entry["month"]) & 0xFF
                d = int(entry["day"]) & 0xFF
                y = (int(entry["year"]) - 2000) & 0xFF
                tuples_hex += f"{m:02X}{d:02X}{y:02X}"
        return f"A0{page_id:04X}{tuples_hex}"

    def _retrieve_station_run_times(self, page_id: int) -> str:
        if page_id in self.page_run_times_sec:
            vals_hex = "".join(
                f"{v & 0xFFFF:04X}" for v in self.page_run_times_sec[page_id]
            )
            return f"A0{page_id:04X}{vals_hex}"
        pair_idx = page_id - 0x0080
        odd_stn = pair_idx * 2 + 1
        even_stn = pair_idx * 2 + 2
        prog_count = (
            4 if self._is_ble_schedule_format() else self.profile.maximum_programs
        )
        odd_runs = list(self.station_run_times.get(odd_stn, [0] * prog_count))[
            :prog_count
        ]
        even_runs = list(self.station_run_times.get(even_stn, [0] * prog_count))[
            :prog_count
        ]
        while len(odd_runs) < prog_count:
            odd_runs.append(0)
        while len(even_runs) < prog_count:
            even_runs.append(0)
        runs_hex = "".join(f"{r & 0xFFFF:04X}" for r in (odd_runs + even_runs))
        return f"A0{page_id:04X}{runs_hex}"

    def _handle_set_schedule(self, page_id: int, payload: bytes) -> str:
        """Dispatch schedule write (0x21 -> 0x01) subpages."""
        if page_id == 0x0000:
            return self._set_page_0000(payload)
        if page_id == 0x0008:
            return self._set_page_0008(payload)
        if 0x0010 <= page_id <= 0x0013:
            return self._set_program_config(page_id, payload)
        if page_id in (0x0020, 0x0040):
            return self._set_station_flags(page_id, payload)
        if 0x0060 <= page_id <= 0x0063:
            return self._set_start_times(page_id, payload)
        if page_id in (0x0084, 0x0085) and len(payload) in (30, 15):
            return self._set_calendar_days_off(page_id, payload)
        if 0x0080 <= page_id <= 0x008A:
            return self._set_station_run_times(page_id, payload)
        return "002102"

    def _set_page_0000(self, payload: bytes) -> str:
        if len(payload) < 4:
            return "002102"
        self.inter_station_delay_seconds = (payload[0] << 8) | payload[1]
        self.rain_delay_days = payload[2]
        self.rain_sensor_bypassed = payload[3] != 0
        if len(payload) >= 6:
            self.master_valve_enable = payload[4] != 0
            self.rain_settling_time_minutes = payload[5]
        return "0121"

    def _set_page_0008(self, payload: bytes) -> str:
        count = len(payload) // 4
        new_cs = []
        for i in range(count):
            soak = (payload[4 * i] << 8) | payload[4 * i + 1]
            cycle = (payload[4 * i + 2] << 8) | payload[4 * i + 3]
            new_cs.append(
                {"station": i + 1, "soak_seconds": soak, "cycle_seconds": cycle}
            )
        self.station_cycle_soak = new_cs
        return "0121"

    def _set_program_config(self, page_id: int, payload: bytes) -> str:
        p_num = page_id - 0x000F
        prog = self.programs.setdefault(p_num, ProgramScheduleConfig())
        if len(payload) >= 8:
            prog.custom_days_mask = payload[0]
            prog.cyclic_days = payload[1]
            prog.days_remaining = payload[2]
            prog.permanent_days_off = payload[3]
            prog.seasonal_adjust = (payload[4] << 8) | payload[5]
            prog.water_cycle = payload[6]
            prog.auto_restart = payload[7] != 0
        elif len(payload) >= 6:
            prog.custom_days_mask = payload[0]
            prog.cyclic_days = payload[1]
            prog.days_remaining = payload[2]
            prog.permanent_days_off = payload[3]
            prog.seasonal_adjust = payload[4]
            prog.water_cycle = payload[5]
        else:
            return "002102"
        self.water_budget[p_num - 1] = prog.seasonal_adjust
        return "0121"

    def _set_station_flags(self, page_id: int, payload: bytes) -> str:
        if page_id == 0x0020:
            self.station_rain_sensor_obey = [b != 0 for b in payload]
        else:
            self.station_mv_enable = [b != 0 for b in payload]
        return "0121"

    def _set_start_times(self, page_id: int, payload: bytes) -> str:
        p_num = page_id - 0x005F
        prog = self.programs.setdefault(p_num, ProgramScheduleConfig())
        slot_count = len(payload) // 2
        prog.start_times_minutes = [
            (payload[2 * i] << 8) | payload[2 * i + 1] for i in range(slot_count)
        ]
        return "0121"

    def _set_calendar_days_off(self, page_id: int, payload: bytes) -> str:
        base_idx = 0 if page_id == 0x0084 else 10
        slot_count = len(payload) // 3
        for i in range(slot_count):
            m, d, y = payload[3 * i], payload[3 * i + 1], payload[3 * i + 2]
            if m == 0 or d == 0:
                self.calendar_days_off[base_idx + i] = None
            else:
                self.calendar_days_off[base_idx + i] = {
                    "month": m,
                    "day": d,
                    "year": 2000 + y,
                }
        return "0121"

    def _set_station_run_times(self, page_id: int, payload: bytes) -> str:
        word_count = len(payload) // 2
        words = [(payload[2 * i] << 8) | payload[2 * i + 1] for i in range(word_count)]
        if self.profile.is_battery_based:
            self.page_run_times_sec[page_id] = words
        half = word_count // 2
        pair_idx = page_id - 0x0080
        self.station_run_times[pair_idx * 2 + 1] = words[:half]
        self.station_run_times[pair_idx * 2 + 2] = words[half:]
        return "0121"

    def _handle_current_queue(self, page: int) -> str:
        """Format 0xBB queue response across standard SIP (12B), BLE (14B), and page >= 1 (35B)."""
        is_14b_queue = (
            self.profile.is_battery_based
            or self.profile.protocol_family == ProtocolFamily.BLE_CBOS
        )
        if page == 0:
            counts_hex = (
                f"{self.manual_queue_count & 0xFFFF:04X}{self.auto_queue_count & 0xFFFF:04X}"
                if is_14b_queue
                else f"{self.manual_queue_count & 0xFF:02X}{self.auto_queue_count & 0xFF:02X}"
            )
            return (
                f"BB00{counts_hex}"
                f"{self.remaining_runtime_sec & 0xFFFF:04X}"
                f"{self.inter_station_delay_seconds & 0xFFFF:04X}"
                f"{self.active_station & 0xFF:02X}"
                f"{self.active_program & 0xFF:02X}"
                f"{self.status_flags & 0xFF:02X}"
                f"{self.mv_on_byte & 0xFF:02X}"
            )
        entries_hex = ""
        for idx in range(11):
            if idx < len(self.queued_entries):
                ent = self.queued_entries[idx]
                stn = int(ent.get("station_id", 0)) & 0x0F
                prog = int(ent.get("program_id", -1))
                prog_nibble = (prog + 1) & 0x0F if prog >= 0 else 0
                rem = int(ent.get("remaining_seconds", 0)) & 0xFFFF
                entries_hex += f"{(prog_nibble << 4) | stn:02X}{rem:04X}"
            else:
                entries_hex += "000000"
        return f"BB{page & 0xFF:02X}{entries_hex}"


class UpgradedTM2Device(LegacyProgramDevice):
    """Upgraded TM2 and TRU controller emulator (ESP_TM2v2/v3/v4, TM2R, TRU, ESP_CPTM2)."""
