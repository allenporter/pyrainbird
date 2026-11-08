"""LCRZoneDevice (ESP_RZXe*) and ST8ZoneDevice (ST8X_WF*) zone-centric controllers."""

from __future__ import annotations

from .base import BaseControllerDevice
from .state import LCRZoneSchedule, init_schedule_state


class LCRZoneDevice(BaseControllerDevice):
    """Zone-centric LCR controller emulator for ESP-RZXe and ESP-RZXe2."""

    lcr_zones: dict[int, LCRZoneSchedule]
    zone_seasonal_adjust: list[int]

    def _init_device_state(self) -> None:
        super()._init_device_state()
        init_schedule_state(self)

    def _collect_program_runnable_stations(self, prog: int) -> list[tuple[int, int]]:
        runnable: list[tuple[int, int]] = []
        for z_id, z in sorted(self.lcr_zones.items()):
            if z.run_time_minutes > 0 and prog in (0, z_id):
                z_pct = (
                    self.zone_seasonal_adjust[z_id - 1]
                    if z_id - 1 < len(self.zone_seasonal_adjust)
                    else 100
                )
                runnable.append(
                    (z_id, max(1, round(z.run_time_minutes * 60 * z_pct / 100.0)))
                )
        return runnable

    def _format_page0_sensor_byte(self) -> int:
        return 0x80 if self.rain_sensor_bypassed else 0x00

    def _parse_page0_sensor_byte(self, raw_byte: int) -> bool:
        return (raw_byte & 0x80) != 0

    def _handle_retrieve_schedule(self, page_id: int) -> str:
        """Retrieve LCR global page 0x0000 or zone schedule pages 0x0001..0x0008."""
        if page_id == 0x0000:
            return f"A00000{self._format_page0_sensor_byte():02X}"
        if 1 <= page_id <= 8:
            z = self.lcr_zones.get(page_id, LCRZoneSchedule())
            starts_hex = "".join(
                f"{(st // 10) & 0xFF:02X}" for st in z.start_times_minutes[:6]
            )
            sd = (0x80 if z.sensor_enabled else 0x00) | (z.days_remaining & 0x7F)
            return (
                f"A0{page_id:04X}{z.run_time_minutes & 0xFF:02X}"
                f"{starts_hex}{z.frequency_type & 0xFF:02X}"
                f"{z.custom_days_mask & 0xFF:02X}{z.cyclic_days & 0xFF:02X}{sd:02X}"
            )
        return "002002"

    def _handle_set_schedule(self, page_id: int, payload: bytes) -> str:
        """Set LCR global page 0x0000 or 11-byte zone schedule pages 0x0001..0x0008."""
        if page_id == 0x0000:
            if len(payload) < 1:
                return "002102"
            self.rain_sensor_bypassed = self._parse_page0_sensor_byte(payload[0])
            return "0121"
        if 1 <= page_id <= 8:
            if len(payload) < 11:
                return "002102"
            z = self.lcr_zones.setdefault(page_id, LCRZoneSchedule())
            z.run_time_minutes = payload[0]
            z.start_times_minutes = [payload[i] * 10 for i in range(1, 7)]
            z.frequency_type = payload[7]
            z.custom_days_mask = payload[8] if payload[8] != 0 else 0x7F
            z.cyclic_days = payload[9]
            z.sensor_enabled = (payload[10] & 0x80) != 0
            z.days_remaining = payload[10] & 0x7F
            return "0121"
        return "002102"

    def _op_zone_or_monthly_adjust(self, d: str, bl: int, _t: str | None) -> str:
        """Return 8-zone seasonal adjust vector (0x32 -> 0xB2)."""
        if bl != 2:
            return self._nak(d, 2)
        param = int(d[2:4], 16)
        zones_hex = "".join(
            f"{val & 0xFFFF:04X}" for val in self.zone_seasonal_adjust[:8]
        )
        return f"B2{param:02X}{zones_hex}"

    def _op_set_zone_or_monthly_adjust(self, d: str, bl: int, _t: str | None) -> str:
        """Set 8-zone seasonal adjust vector (0x33 -> 0x0133)."""
        if bl < 4:
            return self._nak(d, 2)
        count = (bl - 2) // 2
        vals = [int(d[4 + i * 4 : 8 + i * 4], 16) for i in range(count)]
        for i, val in enumerate(vals):
            if i < len(self.zone_seasonal_adjust):
                self.zone_seasonal_adjust[i] = val
        if vals:
            self.seasonal_adjust = vals[0]
        return self._ack(d)

    def _pending_queue_entries(self) -> list[dict[str, int]]:
        if self.active_station <= 0:
            return []
        if self.queued_entries:
            return list(self.queued_entries[1:])
        return [
            {
                "station_id": int(item["station"]),
                "remaining_seconds": int(item.get("seconds", 0)),
                "irrigation_type": int(item.get("irrigation_type", 2)),
            }
            for item in self.queue
            if isinstance(item, dict)
        ]

    def _handle_current_queue(self, page: int) -> str:
        """Format LCR/ST8 10-byte queue page 0 response and 4-byte pending entry pages (0x3B -> 0xBB)."""
        pending = self._pending_queue_entries()
        if page == 0:
            active_flag = 1 if self.active_station > 0 else 0
            queued = len(pending) if active_flag else 0
            if not active_flag:
                irrig_type = 0
            elif self.queued_entries and "irrigation_type" in self.queued_entries[0]:
                irrig_type = int(self.queued_entries[0]["irrigation_type"]) & 0xFF
            elif self.manual_queue_count > 0 or self.active_program == 0xFF:
                irrig_type = 2
            else:
                irrig_type = 1
            return (
                f"BB00{queued & 0xFF:02X}{active_flag:02X}0000"
                f"{self.active_station & 0xFF:02X}{irrig_type:02X}"
                f"{self.remaining_runtime_sec & 0xFFFF:04X}"
            )
        entries_hex = ""
        count = max(2, len(pending))
        for idx in range(count):
            if idx < len(pending):
                ent = pending[idx]
                irrig_type = int(ent.get("irrigation_type", 1)) & 0xFF
                stn = int(ent.get("station_id", 0)) & 0xFF
                rem = int(ent.get("remaining_seconds", 0)) & 0xFFFF
                entries_hex += f"{irrig_type:02X}{stn:02X}{rem:04X}"
            else:
                entries_hex += "00000000"
        return f"BB{page & 0xFF:02X}{entries_hex}"


class ST8ZoneDevice(LCRZoneDevice):
    """ST8x-WiFi / ST8x-WiFi2 zone-centric controller sharing LCR schedule, sensor, and queue behavior."""
