"""BLEBatteryDevice (ESP_BAT_BT*, ESP_BAT_PRO*) and SolemTBOSDevice (TBOS_BT*)."""

from __future__ import annotations

import struct

from .base import SipHandler
from .constants import (
    BLE_CBOS_OTA_NOTIFY_UUID,
    BLE_CBOS_OTA_WRITE_UUID,
    BLE_CBOS_SIP_NOTIFY_UUID,
    BLE_CBOS_SIP_WRITE_UUID,
    TBOS_BT_LT_NOTIFY_UUID,
    TBOS_BT_LT_WRITE_UUID,
    TBOS_BT_NOTIFY_UUID,
    TBOS_BT_WRITE_UUID,
)
from .legacy_sip import UpgradedTM2Device
from .state import init_ble_state


class FlowAndExtendedSIPMixin(UpgradedTM2Device):
    """Mixin implementing extended SIP opcodes 0x55-0x65 (battery status, BLE OTA, and flow learn/monitor)."""

    def _init_device_state(self) -> None:
        super()._init_device_state()
        init_ble_state(self)

    def _is_command_supported_by_default(self, cmd: str) -> bool:
        if cmd in ("55", "59", "5C", "5D", "5E", "5F"):
            return self.profile.is_battery_based or self.profile.controller_type in (
                "TBOS_BT",
                "TBOS_BT_LT",
            )
        return super()._is_command_supported_by_default(cmd)

    def _build_sip_handlers(self) -> dict[str, SipHandler]:
        handlers = super()._build_sip_handlers()
        handlers.update(
            {
                "55": self._op_security_status,
                "57": self._op_factory_defaults,
                "58": self._op_raster_test,
                "59": self._op_set_controller_pin,
                "5C": self._op_battery_and_comm_status,
                "5D": self._op_ota_start,
                "5E": self._op_ota_end,
                "5F": self._op_ota_cancel,
                "60": self._op_start_flow_learn,
                "61": self._op_cancel_or_transition_61,
                "62": self._op_get_flow_learn_state,
                "63": self._op_get_flow_monitor_state,
                "64": self._op_set_flow_monitor_state,
                "65": self._op_get_flow_monitor_rate,
            }
        )
        return handlers

    def _op_security_status(self, d: str, bl: int, _t: str | None) -> str:
        """Handle security PIN status query (0x55 -> 0x56)."""
        if bl != 1:
            return self._nak(d, 2)
        if not self.profile.is_battery_based and self.profile.controller_type not in (
            "TBOS_BT",
            "TBOS_BT_LT",
        ):
            return self._nak(d, 1)
        p_set = "01" if self.is_pin_set else "00"
        p_ok = "01" if self.is_pin_corrected else "00"
        return f"56{p_set}{p_ok}"

    def _op_factory_defaults(self, d: str, bl: int, _t: str | None) -> str:
        """Handle factory reset request (0x57 -> 0x0157)."""
        if bl != 1:
            return self._nak(d, 2)
        self.rain_delay_days = 0
        self.seasonal_adjust = 100
        for p in self.programs.values():
            p.seasonal_adjust = 100
        return self._ack(d)

    def _op_raster_test(self, d: str, bl: int, _t: str | None) -> str:
        """Handle station wiring test trigger (0x58 -> 0x0158)."""
        if bl != 1:
            return self._nak(d, 2)
        self.raster_test_run = True
        return self._ack(d)

    def _op_set_controller_pin(self, d: str, bl: int, _t: str | None) -> str:
        """Handle controller PIN update (0x59 -> 0x0159)."""
        if bl not in (6, 7):
            return self._nak(d, 2)
        pin_hex = d[-8:]
        if pin_hex == "FFFFFFFF":
            self.pin_code = ""
            self.is_pin_set = False
        else:
            self.pin_code = f"{int(pin_hex, 16):06d}"
            self.is_pin_set = True
            self.is_pin_corrected = True
        return self._ack(d)

    def _op_battery_and_comm_status(self, data: str, bl: int, _tr: str | None) -> str:
        """Handle battery and radio status (0x5C -> 0xDC, 8-byte LE mV + source + BLE/LoRa SNR/RSSI)."""
        if bl != 1:
            return self._nak(data, 2)
        mv_le = struct.pack("<H", self.battery_voltage_mv & 0xFFFF).hex().upper()
        src = self.battery_source_type.zfill(2)[:2].upper()
        return (
            f"DC{mv_le}{src}{self.ble_snr & 0xFF:02X}{self.ble_rssi & 0xFF:02X}"
            f"{self.lora_snr & 0xFF:02X}{self.lora_rssi & 0xFF:02X}"
        )

    def _op_ota_start(self, data: str, _bl: int, _tr: str | None) -> str:
        """Handle OTA transfer start (0x5D -> 0x015D)."""
        self.ota_active = True
        return self._ack(data)

    def _op_ota_end(self, data: str, _bl: int, _tr: str | None) -> str:
        """Handle OTA transfer end (0x5E -> 0x015E)."""
        self.ota_active = False
        return self._ack(data)

    def _op_ota_cancel(self, data: str, _bl: int, _tr: str | None) -> str:
        """Handle OTA transfer cancel/fallback (0x5F -> 0x015F)."""
        self.ota_active = False
        return self._ack(data)

    def _op_start_flow_learn(self, data: str, bl: int, _tr: str | None) -> str:
        """Handle station flow learn start (0x60 -> 0x0160)."""
        self.flow_learn_active = True
        self.flow_learn_state = 1
        if bl >= 5:
            self.learning_stations_mask = data[2:10]
        return self._ack(data)

    def _op_cancel_or_transition_61(self, data: str, bl: int, tr: str | None) -> str:
        """Disambiguate 0x61 BLE transition flag (62PP) vs WiFi stick flow learn cancel (0161)."""
        if bl != 1:
            return self._nak(data, 2)
        if (
            tr == "STICK_TUNNEL_SIP" or "flow_learn_active" in self._applied_state
        ) and tr != "BLE":
            self.flow_learn_active = False
            self.flow_learn_state = 0
            return self._ack(data)
        return f"62{'01' if self.transition_is_processing else '00'}"

    def _op_get_flow_learn_state(self, data: str, bl: int, _tr: str | None) -> str:
        """Handle station flow learn state query (0x62 -> 0xE2)."""
        return (
            f"E2{self.flow_learn_state & 0xFF:02X}" if bl == 1 else self._nak(data, 2)
        )

    def _op_get_flow_monitor_state(self, data: str, bl: int, _tr: str | None) -> str:
        """Handle flow monitor state query (0x63 -> 0xE3)."""
        if bl != 1:
            return self._nak(data, 2)
        return f"E3{'01' if self.flow_monitor_enabled else '00'}00"

    def _op_set_flow_monitor_state(self, data: str, bl: int, _tr: str | None) -> str:
        """Handle flow monitor state update (0x64 -> 0x0164)."""
        if bl not in (2, 3):
            return self._nak(data, 2)
        self.flow_monitor_enabled = int(data[2:4], 16) == 1
        return self._ack(data)

    def _op_get_flow_monitor_rate(self, data: str, bl: int, _tr: str | None) -> str:
        """Handle flow monitor rate query (0x65 -> 0xE5)."""
        if bl != 2:
            return self._nak(data, 2)
        idx = int(data[2:4], 16)
        rate_le = struct.pack("<H", self.current_flow_rate_milli & 0xFFFF).hex().upper()
        return f"E5{idx:02X}{rate_le}"


class BLEBatteryDevice(FlowAndExtendedSIPMixin):
    """BLE CBOS battery-powered controller emulator for ESP-BAT-BT* and ESP-BAT-PRO*."""

    def handle_gatt_write(
        self, gatt_write_uuid: str, payload_hex: str
    ) -> tuple[str, str]:
        """Handle BLE GATT characteristic writes across CBOS SIP (fe46) and CBOS OTA (fe44)."""
        uuid_norm = gatt_write_uuid.strip().lower()
        data = payload_hex.strip().upper()

        if uuid_norm == BLE_CBOS_SIP_WRITE_UUID.lower():
            resp_hex = self.handle_sip(data, transport="BLE")
            return BLE_CBOS_SIP_NOTIFY_UUID, resp_hex

        if uuid_norm == BLE_CBOS_OTA_WRITE_UUID.lower():
            raw = bytes.fromhex(data)
            frag_idx = struct.unpack("<H", raw[0:2])[0] if len(raw) >= 2 else 1
            self.ota_last_fragment = frag_idx
            resp = struct.pack("<HHB", frag_idx, self.ota_total_fragments, 0x01)
            return BLE_CBOS_OTA_NOTIFY_UUID, resp.hex().upper()

        if uuid_norm in (
            TBOS_BT_WRITE_UUID.lower(),
            TBOS_BT_LT_WRITE_UUID.lower(),
        ):
            notify_uuid = (
                TBOS_BT_NOTIFY_UUID
                if uuid_norm == TBOS_BT_WRITE_UUID.lower()
                else TBOS_BT_LT_NOTIFY_UUID
            )
            return notify_uuid, self.handle_solem_frame(data)

        raise ValueError(f"Unsupported GATT write UUID: {gatt_write_uuid}")

    def handle_ble_write(self, write_char: str, payload_hex: str) -> dict[str, str]:
        """Handle BLE GATT write and return {'notify_char': ..., 'payload_hex': ...}."""
        notify_char, resp_hex = self.handle_gatt_write(write_char, payload_hex)
        return {"notify_char": notify_char, "payload_hex": resp_hex}

    def handle_solem_frame(self, payload_hex: str) -> str:
        """Handle Solem [CODE, LENGTH, IT, DATA] BLE frame."""
        raw = bytes.fromhex(payload_hex.strip())
        if len(raw) < 3:
            return "000100F0"
        req_code, length, it = raw[0], raw[1], raw[2]
        data = raw[3 : 3 + length]
        resp_code = (req_code + 1) & 0xFF

        if req_code == 0x19 and len(raw) >= 5:
            expected_sum = sum(raw[:-2]) & 0xFFFF
            wire_sum = struct.unpack("<H", raw[-2:])[0]
            code_hex = data[:-2].hex().upper()
            checksum_ok = expected_sum == wire_sum or (
                wire_sum != 0 and bool(self.solem_install_code)
            )
            if not checksum_ok:
                return f"{resp_code:02X}0100F0"
            if not self.solem_install_code or code_hex == self.solem_install_code:
                self.solem_authenticated = True
                return f"{resp_code:02X}010001"
            return f"{resp_code:02X}0100F0"

        return f"{resp_code:02X}01{it:02X}01"


class SolemTBOSDevice(BLEBatteryDevice):
    """Solem TBOS-BT / TBOS-BT-LT controller emulator supporting F4780001/863A0001 Solem frames."""
