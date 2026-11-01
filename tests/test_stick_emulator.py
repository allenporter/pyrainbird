"""Unit tests for LNK2 WiFi Stick transport, crypto, framing, and JSON-RPC 2.0."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pyrainbird.testing.crypto import (
    decode_manchester_frame,
    decrypt_stick_payload,
    derive_aes256_key,
    encode_manchester_frame,
    encrypt_stick_payload,
    manchester_decode_pulses,
    manchester_encode_bytes,
    pad_zero_16,
    strip_stick_padding,
)
from pyrainbird.testing.emulator import RainbirdDeviceEmulator
from pyrainbird.testing.stick import LNK2StickEmulator


@dataclass
class _StubProfile:
    maximum_stations: int = 8


@dataclass
class _StubDevice:
    """Minimal device stub for isolated LNK2StickEmulator testing."""

    profile: _StubProfile = field(default_factory=_StubProfile)
    password: str | None = None
    encryption_required: bool = False
    request_encrypted: bool = True
    lockout_active: bool = False
    lockout_tries: int = 5
    lockout_timeout: int = 5
    failed_attempts: int = 0
    mac_address: str = "D8:B6:73:01:02:03"
    local_ip_address: str = "192.168.1.50"
    local_netmask: str = "255.255.255.0"
    local_gateway: str = "192.168.1.1"
    wifi_rssi: int = -55
    wifi_ssid: str = "HomeNetwork"
    wifi_password: str = "secret"
    wifi_security: str = "wpa2"
    ap_timeout_no_lan: int = 1800
    ap_timeout_idle: int = 1800
    ap_security: str = "none"
    stick_id: str = "RB4455667788"
    stick_version: str = "2.9"
    visible_aps: list[dict[str, Any]] = field(
        default_factory=lambda: [{"ssid": "Guest", "rssi": -60}]
    )
    network_up: bool = True
    internet_up: bool = True
    server_check_in_rsp: bool = True
    server_open_socket: bool = True
    ap_mode: bool = False
    server_mode: bool = True
    check_in_interval: int = 60
    server_url: str = "https://api.rainbird.com"
    missed_check_ins: int = 0
    relay_timeout: int = 30
    country: str = "US"
    zip_code: str = "92121"
    global_disable: bool = False
    num_programs: int = 4
    program_opt_out_mask: str = "0000000000000000"
    soil_types: list[int] = field(default_factory=lambda: [0] * 8)
    flow_rates: list[int] = field(default_factory=lambda: [0] * 8)
    flow_units: list[int] = field(default_factory=lambda: [0] * 8)
    auto_queue: list[dict[str, Any]] = field(default_factory=list)
    manual_rpc_queue: list[dict[str, Any]] = field(default_factory=list)
    auto_queue_interval: int = 0
    update_status: int = 0
    lnk_progress: int = 0
    unv_progress: int = 0
    reboot_scheduled: bool = False
    flow_monitor_enabled: bool = True
    current_flow_rate_milli: int = 2500
    last_uart_tx_frame_hex: str = ""

    def handle_sip(self, data_hex: str, *, transport: str | None = None) -> str:
        if data_hex == "02":
            return "8200090100"
        return f"01{data_hex[:2]}"


def test_aes256_key_padding_and_envelope() -> None:
    """Verify SHA-256 key derivation, zero padding, and 48-byte header + AES-256-CBC envelope."""
    key = derive_aes256_key("admin")
    assert len(key) == 32
    assert (
        key.hex().upper()
        == "8C6976E5B5410415BDE908BD4DEE15DFB167A9C873FC4BB8A81F6F2AB448A918"
    )

    raw_79 = b'{"id":1,"jsonrpc":"2.0","method":"tunnelSip","params":{"data":"02","length":1}}'
    assert len(raw_79) == 79
    padded_80 = pad_zero_16(raw_79)
    assert len(padded_80) == 80
    assert padded_80.endswith(b"\x00")
    assert strip_stick_padding(padded_80) == raw_79

    raw_64 = b"A" * 64
    assert len(pad_zero_16(raw_64)) == 64

    iv = bytes.fromhex("000102030405060708090A0B0C0D0E0F")
    plaintext = '{"id":1,"jsonrpc":"2.0","method":"getSettings"}'
    envelope = encrypt_stick_payload(plaintext, "admin", iv=iv)
    assert len(envelope) == 96
    ok, dec = decrypt_stick_payload(envelope, "admin")
    assert ok is True
    assert dec == plaintext.encode("utf-8")

    ok_bad, _ = decrypt_stick_payload(envelope, "wrongpass")
    assert ok_bad is False


def test_manchester_and_uart_wire_framing() -> None:
    """Verify LNK2 UART byte-stuffed framing and Differential Manchester encoding/decoding."""
    payload = bytes.fromhex("02")
    frame = encode_manchester_frame(payload)
    assert frame.hex().upper() == "F51C0102031D"
    assert decode_manchester_frame(frame) == payload

    special_payload = bytes([0x1C, 0x1B, 0x1D])
    stuffed_frame = encode_manchester_frame(special_payload)
    assert b"\x1b\x01" in stuffed_frame
    assert b"\x1b\x02" in stuffed_frame
    assert b"\x1b\x03" in stuffed_frame
    assert decode_manchester_frame(stuffed_frame) == special_payload

    pulses = manchester_encode_bytes(frame)
    decoded_bytes = manchester_decode_pulses(pulses)
    assert decoded_bytes == frame


def test_http_stick_endpoints_and_lockout() -> None:
    """Verify HTTP /stick and /stick:80 status codes 200, 400, 403, 404, 503."""
    dev_plain = _StubDevice(encryption_required=False)
    stick_plain = LNK2StickEmulator(dev_plain)
    assert (
        stick_plain.handle_http_post("/stick", {"Content-Type": "application/json"})[
            "status_code"
        ]
        == 200
    )
    assert stick_plain.handle_http_post("/unknown", {})["status_code"] == 404

    dev = _StubDevice(password="admin", encryption_required=True, lockout_tries=2)
    stick = LNK2StickEmulator(dev)

    res_400 = stick.handle_http_post(
        "/stick", {"Content-Type": "application/json"}, body_type="PLAINTEXT_JSON"
    )
    assert res_400["status_code"] == 400

    valid_env = encrypt_stick_payload(
        '{"id":1,"jsonrpc":"2.0","method":"getSettings"}', "admin"
    )
    res_200 = stick.handle_http_post(
        "/stick:80",
        {"Content-Type": "application/octet-stream"},
        body=valid_env,
    )
    assert res_200["status_code"] == 200

    bad_env = encrypt_stick_payload(
        '{"id":1,"jsonrpc":"2.0","method":"getSettings"}', "wrong"
    )
    res_403_1 = stick.handle_http_post(
        "/stick", {"Content-Type": "application/octet-stream"}, body=bad_env
    )
    assert res_403_1["status_code"] == 403
    assert dev.lockout_active is False

    res_403_2 = stick.handle_http_post(
        "/stick", {"Content-Type": "application/octet-stream"}, client_password="bad"
    )
    assert res_403_2["status_code"] == 403
    assert dev.lockout_active is True

    res_503 = stick.handle_http_post(
        "/stick",
        {"Content-Type": "application/octet-stream"},
        body_type="AES256_CBC_ENVELOPE",
    )
    assert res_503["status_code"] == 503


def test_stick_jsonrpc_methods() -> None:
    """Verify Stick-native JSON-RPC 2.0 methods across WiFi, queues, settings, and diagnostics."""
    dev = _StubDevice()
    stick = LNK2StickEmulator(dev)

    # Invalid request / unknown method / invalid tunnelSip params
    assert stick.handle_jsonrpc({"id": 1})["error"]["code"] == -32600
    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "noSuch"})["error"][
            "code"
        ]
        == -32601
    )
    assert (
        stick.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tunnelSip",
                "params": {"data": "02", "length": 5},
            }
        )["error"]["code"]
        == -32602
    )

    res_sip = stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tunnelSip",
            "params": {"data": "02", "length": 1},
        }
    )
    assert res_sip["result"] == {"data": "8200090100", "length": 5}
    assert dev.last_uart_tx_frame_hex == "F51C0102031D"

    # Password and WiFi params
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "setPassword",
            "params": {"password": "pw", "lockoutTries": 3, "lockoutTimeout": 10},
        }
    )
    assert dev.password == "pw"
    assert (
        stick.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 3, "method": "setPassword", "params": {}},
            request_encrypted=False,
        )["error"]["code"]
        == -32001
    )

    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 4, "method": "getWifiParams"})[
            "result"
        ]["wifiSsid"]
        == "HomeNetwork"
    )
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "setWifiParams",
            "params": {
                "wifiSsid": "NewNet",
                "apTimeoutNoLan": 600,
                "apTimeoutIdle": 600,
            },
        }
    )
    assert dev.wifi_ssid == "NewNet"
    assert (
        stick.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "getScanResults",
                "params": {"index": 0},
            }
        )["result"]["numTotal"]
        == 1
    )
    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 7, "method": "getNetworkStatus"})[
            "result"
        ]["networkUp"]
        is True
    )
    stick.handle_jsonrpc(
        {"jsonrpc": "2.0", "id": 8, "method": "setApMode", "params": {"apMode": True}}
    )
    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 9, "method": "getApMode"})[
            "result"
        ]["apMode"]
        is True
    )
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "setServerMode",
            "params": {
                "serverMode": False,
                "checkInInterval": 120,
                "serverUrl": "https://test",
                "relayTimeout": 15,
            },
        }
    )
    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 11, "method": "getServerMode"})[
            "result"
        ]["serverMode"]
        is False
    )

    # Settings, program info, zip code, weather mask
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "setProgramInfo",
            "params": {"Program": 1, "SoilType": 2, "FlowRate": 15, "FlowUnit": 1},
        }
    )
    assert (
        stick.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 13,
                "method": "getProgramInfo",
                "params": {"Program": 1},
            }
        )["result"]["SoilType"]
        == 2
    )
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 14,
            "method": "setSoilType",
            "params": {"Program": 2, "SoilType": 3},
        }
    )
    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 15, "method": "getSettings"})[
            "result"
        ]["SoilTypes"][1]
        == 3
    )

    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 16,
            "method": "setZipCode",
            "params": {"country": "US", "code": "85718"},
        }
    )
    assert stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 17, "method": "getZipCode"})[
        "result"
    ] == {"country": "US", "code": "85718"}

    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 18,
            "method": "setWeatherAdjustmentMask",
            "params": {
                "globalDisable": True,
                "numPrograms": 4,
                "programOptOutMask": "0100",
            },
        }
    )
    assert (
        stick.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 19, "method": "getWeatherAdjustmentMask"}
        )["result"]["globalDisable"]
        is True
    )

    # Auto/manual queue lists and responses
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 20,
            "method": "setAutoQueueList",
            "params": {"index": 0, "value": "02", "autoIncByte": 0},
        }
    )
    assert (
        stick.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 21,
                "method": "getAutoQueueList",
                "params": {"index": 0},
            }
        )["result"]["value"]
        == "02"
    )
    assert (
        stick.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 22,
                "method": "getAutoQueueResponse",
                "params": {"index": 0},
            }
        )["result"]["response"]
        == "8200090100"
    )
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 23,
            "method": "setAutoQueueConsecutive",
            "params": {
                "clearList": 1,
                "startIdx": 0,
                "commands": ["02", "10"],
                "autoIncBytes": [0, 0],
            },
        }
    )
    stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 24,
            "method": "setAutoQueueInterval",
            "params": {"interval": 30},
        }
    )
    assert (
        stick.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 25, "method": "getAutoQueueInterval"}
        )["result"]["interval"]
        == 30
    )
    stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 26, "method": "clearAutoQueueList"})
    stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 27, "method": "clearManualQueueList"})

    # Firmware, reboot, MAC, flow monitor, logs, peripheral, testRpc
    assert (
        stick.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 28, "method": "getFwUpdateStatus"}
        )["result"]["updateStatus"]
        == 0
    )
    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 29, "method": "requestFwUpdate"})[
            "result"
        ]
        == "OK"
    )
    assert (
        stick.handle_jsonrpc({"jsonrpc": "2.0", "id": 30, "method": "appReboot"})[
            "result"
        ]
        == "OK"
    )
    assert (
        stick.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 31,
                "method": "setMacAddress",
                "params": {"macAddress": "AA:BB:CC:DD:EE:FF"},
            }
        )["result"]
        == "OK"
    )
    assert (
        stick.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 32, "method": "getFlowMonitorStatus", "params": {}}
        )["result"]["flowRate"]
        == 2.5
    )
    assert (
        stick.handle_jsonrpc(
            {"jsonrpc": "2.0", "id": 33, "method": "getLogStatistics", "params": {}}
        )["result"]["maxStations"]
        == 8
    )
    assert (
        stick.handle_jsonrpc(
            {
                "jsonrpc": "2.0",
                "id": 34,
                "method": "PeripheralReadWrite",
                "params": {"Command": 1, "DataLength": 2, "Data": "ABCD"},
            }
        )["result"]["Data"]
        == "ABCD"
    )
    res_test = stick.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 35,
            "method": "testRpc",
            "params": {"length": 5, "string": "AAAAA", "value": 42},
        }
    )
    assert res_test["result"] == {"length": 5, "string": "AAAAA", "value": 42}


def test_tunnel_sip_rejects_oversize_response_frame() -> None:
    """Verify tunnelSip rejects SIP responses exceeding the 255-byte wire frame limit."""
    emu = RainbirdDeviceEmulator.for_model("LX_ME2")
    # Unchunked 0x1D start-time read across all 40 programs x 10 slots produces an 839-byte 0x8C response
    unchunked_req = "0C200001000805000000000C0000000000050000001200070B011D0003000027000000000000000900"
    resp = emu.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tunnelSip",
            "params": {"data": unchunked_req, "length": len(unchunked_req) // 2},
        }
    )
    assert resp["error"] == {"code": -32603, "message": "SIP response frame overflow"}
