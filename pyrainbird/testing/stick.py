"""LNK2 WiFi Stick HTTP transport and JSON-RPC 2.0 emulator."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .crypto import (
    decode_manchester_frame,
    decode_sip_wire_frame,
    decrypt_lnk2_envelope,
    decrypt_stick_payload,
    derive_aes256_key,
    encode_manchester_frame,
    encode_sip_wire_frame,
    encrypt_lnk2_envelope,
    encrypt_stick_payload,
    manchester_decode_pulses,
    manchester_encode_bytes,
    pad_zero_16,
    strip_stick_padding,
    zero_pad_16,
    zero_unpad,
)

RpcDict = dict[str, Any]
RpcHandler = Callable[[str, RpcDict, bool], Any]


def _ok(req_id: Any, result: Any = "OK") -> RpcDict:
    return {"jsonrpc": "2.0", "id": req_id, "result": result}


def _err(req_id: Any, code: int, message: str) -> RpcDict:
    return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


class _RpcError(Exception):
    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.message = message


class LNK2StickEmulator:
    """LNK2 WiFi Stick emulator handling /stick:80 HTTP, AES-256-CBC lockout, and JSON-RPC methods."""

    def __init__(self, device: Any) -> None:
        self.device = device
        self._jsonrpc_handlers: dict[str, RpcHandler] = {
            "tunnelSip": self._r_tunnel_sip,
            "setPassword": self._r_set_password,
            "getWifiParams": self._r_get_wifi_params,
            "setWifiParams": self._r_set_wifi_params,
            "getScanResults": self._r_get_scan_results,
            "getNetworkStatus": self._r_get_network_status,
            "getApMode": self._r_get_ap_mode,
            "setApMode": self._r_set_ap_mode,
            "getServerMode": self._r_get_server_mode,
            "setServerMode": self._r_set_server_mode,
            "getSettings": self._r_get_settings,
            "getProgramInfo": self._r_get_program_info,
            "setProgramInfo": self._r_set_program_info,
            "setSoilType": self._r_set_soil_type,
            "getZipCode": self._r_get_zip_code,
            "setZipCode": self._r_set_zip_code,
            "getAutoQueueList": self._r_get_queue_list,
            "getManualQueueList": self._r_get_queue_list,
            "setAutoQueueList": self._r_set_queue_list,
            "setManualQueueList": self._r_set_queue_list,
            "clearAutoQueueList": self._r_clear_queue_list,
            "clearManualQueueList": self._r_clear_queue_list,
            "setAutoQueueConsecutive": self._r_set_queue_consecutive,
            "setManualQueueConsecutive": self._r_set_queue_consecutive,
            "setQueueMultiList": self._r_set_queue_consecutive,
            "getAutoQueueInterval": self._r_get_auto_queue_interval,
            "setAutoQueueInterval": self._r_set_auto_queue_interval,
            "getAutoQueueResponse": self._r_get_queue_response,
            "getManualQueueResponse": self._r_get_queue_response,
            "getWeatherAdjustmentMask": self._r_get_weather_adjustment_mask,
            "setWeatherAdjustmentMask": self._r_set_weather_adjustment_mask,
            "getFwUpdateStatus": self._r_get_fw_update_status,
            "requestFwUpdate": self._r_request_fw_update,
            "testRpc": self._r_test_rpc,
            "appReboot": self._r_app_reboot,
            "setMacAddress": self._r_set_mac_address,
            "getFlowMonitorStatus": self._r_get_flow_monitor_status,
            "getLogStatistics": self._r_get_log_statistics,
            "PeripheralReadWrite": self._r_peripheral_read_write,
        }

    def handle_http_post(
        self,
        path: str,
        headers: dict[str, str],
        body: bytes | str | None = None,
        body_type: str | None = None,
        client_password: str | None = None,
    ) -> RpcDict:
        """Handle simulated HTTP POST to /stick or /stick:80."""
        dev = self.device
        if path not in ("/stick", "/stick:80", "/upload"):
            return {"status_code": 404, "status_text": "404 Not Found"}
        if dev.lockout_active:
            return {"status_code": 503, "status_text": "503 Service Unavailable"}

        content_type = headers.get("Content-Type") or headers.get("content-type") or ""
        if dev.encryption_required:
            if content_type == "application/json" or body_type == "PLAINTEXT_JSON":
                return {"status_code": 400, "status_text": "400 Bad Request"}
            if client_password is not None and client_password != dev.password:
                return self._record_auth_failure()
            if isinstance(body, bytes) and len(body) >= 48:
                ok, plain = decrypt_lnk2_envelope(body, dev.password or "")
                if not ok or plain is None:
                    return self._record_auth_failure()
            return {
                "status_code": 200,
                "headers": {"Content-Type": "application/octet-stream"},
                "body_type": "AES256_CBC_ENVELOPE",
            }
        return {
            "status_code": 200,
            "headers": {"Content-Type": "application/json"},
            "body_type": "PLAINTEXT_JSON",
        }

    def _record_auth_failure(self) -> RpcDict:
        dev = self.device
        dev.failed_attempts += 1
        if dev.failed_attempts >= dev.lockout_tries:
            dev.lockout_active = True
        return {"status_code": 403, "http_status": 403, "decrypt_verified": False}

    def handle_jsonrpc(
        self, request: RpcDict, *, request_encrypted: bool | None = None
    ) -> RpcDict:
        """Dispatch a JSON-RPC 2.0 request to Stick or tunnelSip handlers."""
        req_id = request.get("id", 1)
        method = request.get("method")
        if request.get("jsonrpc") != "2.0" or not isinstance(method, str):
            return _err(req_id, -32600, "Invalid Request")
        is_enc = (
            self.device.request_encrypted
            if request_encrypted is None
            else request_encrypted
        )
        handler = self._jsonrpc_handlers.get(method)
        if handler is None:
            return _err(req_id, -32601, "Method not found")
        try:
            res = handler(method, request.get("params") or {}, is_enc)
        except _RpcError as exc:
            return _err(req_id, exc.code, exc.message)
        return _ok(req_id, res)

    def _r_tunnel_sip(self, _m: str, p: RpcDict, _e: bool) -> Any:
        data_hex = str(p.get("data", "")).strip().upper()
        exp = p.get("length")
        if (
            not data_hex
            or len(data_hex) % 2 != 0
            or (exp is not None and int(exp) != len(data_hex) // 2)
        ):
            raise _RpcError(-32602, "Invalid params")
        wire = encode_sip_wire_frame(bytes.fromhex(data_hex))
        self.device.last_uart_tx_frame_hex = wire.hex().upper()
        resp = self.device.handle_sip(data_hex, transport="STICK_TUNNEL_SIP")
        return {"data": resp, "length": len(resp) // 2}

    def _r_set_password(self, _m: str, p: RpcDict, is_enc: bool) -> str:
        dev = self.device
        if dev.password and not is_enc:
            raise _RpcError(-32001, "Password protected")
        dev.password = str(p.get("password", ""))
        dev.encryption_required = bool(dev.password)
        if "lockoutTries" in p:
            dev.lockout_tries = int(p["lockoutTries"])
        if "lockoutTimeout" in p:
            dev.lockout_timeout = int(p["lockoutTimeout"])
        return "OK"

    def _r_get_wifi_params(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        return {
            "macAddress": d.mac_address,
            "localIpAddress": d.local_ip_address,
            "localNetmask": d.local_netmask,
            "localGateway": d.local_gateway,
            "rssi": d.wifi_rssi,
            "wifiSsid": d.wifi_ssid,
            "wifiPassword": d.wifi_password,
            "wifiSecurity": d.wifi_security,
            "apTimeoutNoLan": d.ap_timeout_no_lan,
            "apTimeoutIdle": d.ap_timeout_idle,
            "apSecurity": d.ap_security,
            "stickId": d.stick_id,
            "stickVersion": d.stick_version,
        }

    def _r_set_wifi_params(self, _m: str, p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        for pk, attr in (
            ("wifiSsid", "wifi_ssid"),
            ("wifiPassword", "wifi_password"),
            ("wifiSecurity", "wifi_security"),
            ("apSecurity", "ap_security"),
            ("stickVersion", "stick_version"),
        ):
            if pk in p:
                setattr(d, attr, str(p[pk]))
        if "apTimeoutNoLan" in p:
            d.ap_timeout_no_lan = int(p["apTimeoutNoLan"])
        if "apTimeoutIdle" in p:
            d.ap_timeout_idle = int(p["apTimeoutIdle"])
        return {"joinedNetwork": True}

    def _r_get_scan_results(self, _m: str, p: RpcDict, _e: bool) -> RpcDict:
        idx = int(p.get("index", 0))
        batch = self.device.visible_aps[idx : idx + 5]
        return {
            "index": idx,
            "numTotal": len(self.device.visible_aps),
            "numThis": len(batch),
            "ssids": [str(ap["ssid"]) for ap in batch],
            "rssis": [int(ap["rssi"]) for ap in batch],
        }

    def _r_get_network_status(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        return {
            "networkUp": d.network_up,
            "internetUp": d.internet_up,
            "serverCheckInRsp": d.server_check_in_rsp,
            "serverOpenSocket": d.server_open_socket,
        }

    def _r_get_ap_mode(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        return {"apMode": self.device.ap_mode}

    def _r_set_ap_mode(self, _m: str, p: RpcDict, _e: bool) -> str:
        self.device.ap_mode = bool(p.get("apMode", False))
        return "OK"

    def _r_get_server_mode(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        return {
            "serverMode": d.server_mode,
            "checkInInterval": d.check_in_interval,
            "serverUrl": d.server_url,
            "missedCheckIns": d.missed_check_ins,
            "relayTimeout": d.relay_timeout,
        }

    def _r_set_server_mode(self, _m: str, p: RpcDict, _e: bool) -> str:
        d = self.device
        d.server_mode = bool(p["serverMode"])
        if "checkInInterval" in p:
            d.check_in_interval = int(p["checkInInterval"])
        if "serverUrl" in p:
            d.server_url = str(p["serverUrl"])
        if "relayTimeout" in p:
            d.relay_timeout = int(p["relayTimeout"])
        return "OK"

    def _r_get_settings(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        n = d.num_programs
        return {
            "country": d.country,
            "code": d.zip_code,
            "globalDisable": d.global_disable,
            "numPrograms": n,
            "programOptOutMask": d.program_opt_out_mask,
            "SoilTypes": list(d.soil_types[:n]),
            "FlowRates": list(d.flow_rates[:n]),
            "FlowUnits": list(d.flow_units[:n]),
        }

    def _r_get_program_info(self, _m: str, p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        prog = int(p.get("Program", 1))
        idx = max(0, min(7, prog - 1))
        return {
            "Program": prog,
            "SoilType": d.soil_types[idx],
            "FlowRate": d.flow_rates[idx],
            "FlowUnit": d.flow_units[idx],
        }

    def _r_set_program_info(self, _m: str, p: RpcDict, _e: bool) -> str:
        d = self.device
        idx = max(0, min(7, int(p.get("Program", 1)) - 1))
        if "SoilType" in p:
            d.soil_types[idx] = int(p["SoilType"])
        if "FlowRate" in p:
            d.flow_rates[idx] = int(p["FlowRate"])
        if "FlowUnit" in p:
            d.flow_units[idx] = int(p["FlowUnit"])
        return "OK"

    def _r_set_soil_type(self, _m: str, p: RpcDict, _e: bool) -> str:
        idx = max(0, min(7, int(p.get("Program", 1)) - 1))
        self.device.soil_types[idx] = int(p.get("SoilType", 0))
        return "OK"

    def _r_get_zip_code(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        return {"country": self.device.country, "code": self.device.zip_code}

    def _r_set_zip_code(self, _m: str, p: RpcDict, _e: bool) -> str:
        self.device.country = str(p.get("country", ""))
        self.device.zip_code = str(p.get("code", ""))
        return "OK"

    def _r_get_queue_list(self, m: str, p: RpcDict, _e: bool) -> RpcDict:
        q = (
            self.device.auto_queue
            if m == "getAutoQueueList"
            else self.device.manual_rpc_queue
        )
        idx = int(p.get("index", 0))
        entry = q[idx] if 0 <= idx < len(q) else {"value": "", "autoIncByte": 0}
        return {
            "listLength": len(q),
            "index": idx,
            "autoIncByte": bool(entry.get("autoIncByte", 0)),
            "value": str(entry.get("value", "")),
        }

    def _r_set_queue_list(self, m: str, p: RpcDict, _e: bool) -> RpcDict:
        q = (
            self.device.auto_queue
            if m == "setAutoQueueList"
            else self.device.manual_rpc_queue
        )
        idx = int(p.get("index", 0))
        val = str(p.get("value", "")).upper()
        while len(q) <= idx:
            q.append({"index": len(q), "length": 0, "value": "", "autoIncByte": 0})
        q[idx] = {
            "index": idx,
            "length": int(p.get("length", len(val) // 2)),
            "value": val,
            "autoIncByte": int(p.get("autoIncByte", 0)),
        }
        return {"index": idx}

    def _r_clear_queue_list(self, m: str, _p: RpcDict, _e: bool) -> str:
        if m == "clearAutoQueueList":
            self.device.auto_queue.clear()
        else:
            self.device.manual_rpc_queue.clear()
        return "OK"

    def _r_set_queue_consecutive(self, m: str, p: RpcDict, _e: bool) -> RpcDict:
        q = (
            self.device.auto_queue
            if m == "setAutoQueueConsecutive"
            else self.device.manual_rpc_queue
        )
        if int(p.get("clearList", 0)) != 0:
            q.clear()
        start_idx = int(p.get("startIdx", 0))
        commands = list(p.get("commands", []))
        incs = list(p.get("autoIncBytes", [0] * len(commands)))
        for offset, cmd_val in enumerate(commands):
            idx = start_idx + offset
            val_str = str(cmd_val).upper()
            inc = int(incs[offset]) if offset < len(incs) else 0
            while len(q) <= idx:
                q.append({"index": len(q), "length": 0, "value": "", "autoIncByte": 0})
            q[idx] = {
                "index": idx,
                "length": len(val_str) // 2,
                "value": val_str,
                "autoIncByte": inc,
            }
        return {
            "startIndex": start_idx,
            "entriesSet": len(commands),
            "listLength": len(q),
        }

    def _r_get_auto_queue_interval(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        return {"interval": self.device.auto_queue_interval}

    def _r_set_auto_queue_interval(self, _m: str, p: RpcDict, _e: bool) -> str:
        self.device.auto_queue_interval = int(p.get("interval", 0))
        return "OK"

    def _r_get_queue_response(self, m: str, p: RpcDict, _e: bool) -> RpcDict:
        q = (
            self.device.auto_queue
            if m == "getAutoQueueResponse"
            else self.device.manual_rpc_queue
        )
        idx = int(p.get("index", 0))
        if 0 <= idx < len(q):
            cmd = str(q[idx]["value"]).upper()
            resp = self.device.handle_sip(cmd, transport="STICK_TUNNEL_SIP")
            return {"command": cmd, "response": resp}
        return {}

    def _r_get_weather_adjustment_mask(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        return {
            "globalDisable": d.global_disable,
            "numPrograms": d.num_programs,
            "programOptOutMask": d.program_opt_out_mask,
        }

    def _r_set_weather_adjustment_mask(self, _m: str, p: RpcDict, _e: bool) -> str:
        d = self.device
        d.global_disable = bool(p.get("globalDisable", False))
        d.num_programs = int(p.get("numPrograms", d.num_programs))
        d.program_opt_out_mask = str(p.get("programOptOutMask", d.program_opt_out_mask))
        return "OK"

    def _r_get_fw_update_status(self, _m: str, _p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        return {
            "updateStatus": d.update_status,
            "lnkProgress": d.lnk_progress,
            "unvProgress": d.unv_progress,
        }

    def _r_request_fw_update(self, _m: str, _p: RpcDict, _e: bool) -> str:
        return "OK"

    def _r_test_rpc(self, _m: str, p: RpcDict, _e: bool) -> RpcDict:
        length = int(p.get("length", 0))
        return {"length": length, "value": p.get("value", 0), "string": "A" * length}

    def _r_app_reboot(self, _m: str, _p: RpcDict, _e: bool) -> str:
        self.device.reboot_scheduled = True
        return "OK"

    def _r_set_mac_address(self, _m: str, p: RpcDict, _e: bool) -> str:
        self.device.mac_address = str(p.get("macAddress", self.device.mac_address))
        return "OK"

    def _r_get_flow_monitor_status(self, _m: str, p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        return {
            "StickId": p.get("StickId", d.stick_id),
            "units": p.get("units", "GPM"),
            "enabled": d.flow_monitor_enabled,
            "flowRate": d.current_flow_rate_milli / 1000.0,
        }

    def _r_get_log_statistics(self, _m: str, p: RpcDict, _e: bool) -> RpcDict:
        d = self.device
        max_stn = int(p.get("maxStations", d.profile.maximum_stations))
        return {
            "StickId": p.get("StickId", d.stick_id),
            "units": p.get("units", "GPM"),
            "maxStations": max_stn,
            "referenceDateUTC": int(p.get("referenceDateUTC", 0)),
            "stations": [],
        }

    def _r_peripheral_read_write(self, _m: str, p: RpcDict, _e: bool) -> RpcDict:
        return {
            "Command": int(p.get("Command", 0)),
            "DataLength": int(p.get("DataLength", 0)),
            "Data": str(p.get("Data", "")),
        }


__all__ = [
    "LNK2StickEmulator",
    "decode_manchester_frame",
    "decode_sip_wire_frame",
    "decrypt_lnk2_envelope",
    "decrypt_stick_payload",
    "derive_aes256_key",
    "encode_manchester_frame",
    "encode_sip_wire_frame",
    "encrypt_lnk2_envelope",
    "encrypt_stick_payload",
    "manchester_decode_pulses",
    "manchester_encode_bytes",
    "pad_zero_16",
    "strip_stick_padding",
    "zero_pad_16",
    "zero_unpad",
]
