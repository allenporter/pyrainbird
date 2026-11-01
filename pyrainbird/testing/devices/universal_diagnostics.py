"""Universal field/2-wire (0x04) and expansion module (0x05, 0x0D) subsystems.

Commercial and 2-wire Universal controllers (`ESP-2WIRE`, `LX-ME2`, `LX-IVM*`)
expose hardware diagnostic subsystems inside SIP command `0x0C` to test station
wiring, ping 2-wire decoders/IVMs, survey line voltage/current, and inspect
installed expansion modules.
"""

from __future__ import annotations

import struct
from typing import Any

from .constants import DISCOVERY_PROGRESS_STATUS_CODES, WEATHER_SENSOR_STATUS_CODES

UniRes = tuple[str, str]


def handle_uni_set_raster_test(device: Any, body: bytes) -> UniRes:
    """Start or stop a station wiring raster test (`3509 -> 3609`)."""
    if body:
        active = body[0] == 1
        device.uni_raster_test["active"] = active
        device.uni_raster_test["progress"] = 0 if active else 100
    return "3609", "01"


def handle_uni_get_raster_test_status(device: Any) -> UniRes:
    """Format station wiring raster test status and open/short bitmaps (`3709 -> 3809`)."""
    is_act = 1 if device.uni_raster_test.get("active", False) else 0
    prog = int(device.uni_raster_test.get("progress", 100)) & 0xFF
    stn_bytes, short_bytes = bytearray(3), bytearray(3)
    for s in device.uni_raster_test.get("open_stations", []):
        s_idx = int(s) - 1
        if 0 <= s_idx < 24:
            stn_bytes[s_idx // 8] |= 1 << (s_idx % 8)
    for s in device.uni_raster_test.get("shorted_stations", []):
        s_idx = int(s) - 1
        if 0 <= s_idx < 24:
            short_bytes[s_idx // 8] |= 1 << (s_idx % 8)
    body = (
        f"{is_act:02X}{prog:02X}00000000000000"
        f"0000{short_bytes.hex().upper()}{stn_bytes.hex().upper()}0000"
    )
    return "3809", body


def handle_uni_ping_device_setup(device: Any, body: bytes) -> UniRes:
    """Configure target 2-wire device for ping polling (`3109 -> 3209`)."""
    if len(body) >= 3:
        device.ping_polling_target = {
            "device_number": struct.unpack("<H", body[0:2])[0],
            "device_type": body[2],
        }
    return "3209", "00"


def handle_uni_ping_device(device: Any, op: str) -> UniRes:
    """Return 2-wire device ping result and line voltage (`1D09 -> 1E09`, `3309 -> 3409`)."""
    lp = device.last_ping
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


def handle_uni_get_weather_sensor_status(device: Any) -> UniRes:
    """Format weather sensor monitoring/tripped states (`3B09 -> 3C09`)."""
    codes = [
        WEATHER_SENSOR_STATUS_CODES.get(s, 1) for s in device.weather_sensor_status
    ]
    return "3C09", bytes([len(codes), *codes]).hex().upper()


def handle_uni_get_discovery_progress(device: Any) -> UniRes:
    """Format 2-wire device discovery progress (`4C09 -> 4D09`)."""
    st_str = str(device.discovery.get("status", "DISCOVERY_COMPLETED"))
    st_code = DISCOVERY_PROGRESS_STATUS_CODES.get(st_str, 2)
    pct = int(device.discovery.get("percent_complete", 100)) & 0xFF
    return "4D09", f"{st_code:02X}{pct:02X}"


def handle_uni_get_two_wire_line_survey(device: Any) -> UniRes:
    """Format 2-wire voltage and current line survey frame (`2F09 -> 3009`)."""
    ls = device.line_survey
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


def handle_uni_get_responding_devices(device: Any, op: str) -> UniRes:
    """Format responding / non-responding field device bitmasks (`2009` / `2209`)."""
    nr = device.not_responding
    masks = []
    for k in ("weather", "flow", "mv", "pump", "stations"):
        m = 0
        for idx in nr.get(k, []):
            m |= 1 << (int(idx) - 1)
        masks.append(m)
    buf = struct.pack("<BBBHHBBH", 0, 1, 2, *masks)
    return ("2109" if op == "2009" else "2309"), buf.hex().upper()


def handle_uni_get_discovery_results(device: Any, body: bytes) -> UniRes:
    """Format paginated 2-wire device discovery records (`4E09 -> 4F09`)."""
    page = body[0] if body else 0
    devs = device.discovery.get("devices", [])
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


def handle_uni_ac_current_test(device: Any, body: bytes) -> UniRes:
    """Configure module AC current diagnostic path (`1F50 -> 2050`)."""
    if len(body) >= 2:
        device.ac_current_test["path"] = body[0]
        device.ac_current_test["source_on"] = body[1] == 1
    return "2050", "00"


def handle_uni_get_segment_info(device: Any) -> UniRes:
    """Format 2-wire segment diagnostic status (`2150 -> 2250`)."""
    si = device.segment_info
    buf = struct.pack(
        "<BBBI",
        int(si.get("diagnostic_mode", 0)),
        int(si.get("shorted_map", 0)),
        int(si.get("test_path", 0)),
        int(si.get("current", 0)),
    )
    return "2250", buf.hex().upper()


def handle_uni_set_diagnostic_mode(device: Any, body: bytes) -> UniRes:
    """Set 2-wire segment diagnostic mode (`2350 -> 2450`)."""
    if body:
        device.segment_info["diagnostic_mode"] = body[0]
    return "2450", "00"


def handle_uni_get_module_list(device: Any) -> UniRes:
    """Return installed expansion module address list (`240B -> 250B`)."""
    return "250B", f"00000000{device.module_info_address}"


def handle_uni_get_module_info(device: Any) -> UniRes:
    """Format expansion module hardware and firmware metadata (`220B -> 230B`)."""
    hdr, rec = bytearray(12), bytearray(42)
    hdr[11] = 1
    struct.pack_into("<I", rec, 0, 458753)
    struct.pack_into("<I", rec, 4, 321)
    struct.pack_into("<H", rec, 9, device.fw_major)
    struct.pack_into("<H", rec, 11, device.fw_minor)
    return "230B", (hdr + rec).hex().upper()
