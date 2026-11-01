"""Universal subsystem 0x09 irrigation queue execution and 0x3B queue formatting."""

from __future__ import annotations

import struct
from typing import Any

from .constants import (
    MANUAL_RUN_SOURCE_NAMES,
    MANUAL_RUN_TO_PROGRAM_SOURCE,
    PROGRAM_SOURCE_CODES,
    STATION_STATE_CODES,
)

UniRes = tuple[str, str]


def collect_universal_program_stations(
    device: Any, prog_idx: int
) -> list[tuple[int, int]]:
    """Collect (station_1based, scaled_seconds) for prog_idx from CDT 1500 and 1800."""
    store = device.cdt_store
    pct_tbl = store.get("1800")
    pct = (
        int(pct_tbl[prog_idx])
        if isinstance(pct_tbl, list) and prog_idx < len(pct_tbl)
        else int(device.water_budget.get(prog_idx, 100))
    )
    if pct <= 0:
        return []

    rt_tbl = store.get("1500")
    prog_row = rt_tbl.get(str(prog_idx)) if isinstance(rt_tbl, dict) else None
    result: list[tuple[int, int]] = []
    for stn_idx in range(device.profile.maximum_stations):
        base_sec = 0
        if isinstance(prog_row, list) and stn_idx < len(prog_row):
            base_sec = int(prog_row[stn_idx])
        else:
            runs = device.station_run_times.get(stn_idx + 1, [])
            if 0 <= prog_idx < len(runs) and runs[prog_idx] > 0:
                base_sec = int(runs[prog_idx]) * 60
        if base_sec > 0:
            scaled_sec = max(1, round(base_sec * pct / 100.0))
            result.append((stn_idx + 1, scaled_sec))
    if not result and prog_idx == 0 and device.program_0_stations:
        for entry in device.program_0_stations:
            sec = int(entry.get("minutes", 0)) * 60
            if sec > 0:
                result.append((int(entry["station"]), sec))
    return result


def sync_core_queue_from_uni(device: Any) -> None:
    """Mirror uni_irrigation_queue onto core SIP active/queue attributes."""
    q = [r for r in device.uni_irrigation_queue if "station_number" in r]
    if not q:
        device.active_station = 0
        device.remaining_runtime_sec = 0
        device.manual_queue_count = 0
        device.auto_queue_count = 0
        device.queue.clear()
        device.queued_entries.clear()
        return

    first = q[0]
    first["state"] = "Cycling"
    device.active_station = int(first.get("station_number", 0))
    prog_num = first.get("program_number")
    device.active_program = 0xFF if prog_num is None else int(prog_num)
    device.remaining_runtime_sec = int(first.get("remaining_state_time_s", 0))

    man_cnt, auto_cnt = 0, 0
    entries: list[dict[str, int]] = []
    tail: list[dict[str, int]] = []
    for idx, rec in enumerate(q):
        src = str(rec.get("program_source", "AutoProgram"))
        if src in ("ManualStation", "RemoteStation", "ManualProgram", "RemoteProgram"):
            man_cnt += 1
        else:
            auto_cnt += 1
        stn = int(rec.get("station_number", 0))
        rem = int(rec.get("remaining_state_time_s", 0))
        p_id = -1 if rec.get("program_number") is None else int(rec["program_number"])
        entries.append(
            {"station_id": stn, "program_id": p_id, "remaining_seconds": rem}
        )
        if idx > 0:
            tail.append({"station": stn, "seconds": rem})
    device.manual_queue_count = man_cnt
    device.auto_queue_count = auto_cnt
    device.queued_entries = entries
    device.queue = tail


def sync_uni_queue_from_core(device: Any, *, source: str = "ManualStation") -> None:
    """Mirror core SIP queue state onto uni_irrigation_queue after SIP run/stop/advance."""
    if device.active_station <= 0:
        device.uni_irrigation_queue.clear()
        return
    if device.queued_entries:
        new_q: list[dict[str, Any]] = []
        for idx, ent in enumerate(device.queued_entries):
            p_raw = int(ent.get("program_id", -1))
            prog_num = (
                p_raw
                if p_raw >= 0
                else (None if device.active_program == 0xFF else device.active_program)
            )
            src_name = "ManualProgram" if prog_num is not None else source
            rem = int(ent.get("remaining_seconds", 0))
            new_q.append(
                {
                    "station_number": int(ent["station_id"]),
                    "state": "Cycling" if idx == 0 else "Pending",
                    "program_number": prog_num,
                    "program_source": src_name,
                    "remaining_state_time_s": rem,
                    "secondary_time_s": 0,
                }
            )
        device.uni_irrigation_queue = new_q
        return

    prog_num = None if device.active_program == 0xFF else int(device.active_program)
    device.uni_irrigation_queue = [
        {
            "station_number": int(device.active_station),
            "state": "Cycling",
            "program_number": prog_num,
            "program_source": "ManualProgram" if prog_num is not None else source,
            "remaining_state_time_s": int(device.remaining_runtime_sec),
            "secondary_time_s": 0,
        }
    ]


def handle_uni_run_program(device: Any, body: bytes) -> UniRes:
    """Execute Universal 0A20 manual program run using CDT 1500 and 1800."""
    if len(body) < 2:
        return "0100", "01"
    src_byte, prog_idx = body[0], body[1]
    if prog_idx >= device.profile.maximum_programs:
        return "0100", "04"
    src_name = MANUAL_RUN_TO_PROGRAM_SOURCE.get(src_byte, "RemoteProgram")
    raw_src = MANUAL_RUN_SOURCE_NAMES.get(src_byte, "FROM_REMOTE")
    runnable = collect_universal_program_stations(device, prog_idx)
    if runnable:
        device.uni_irrigation_queue = [
            {
                "station_number": stn,
                "state": "Cycling" if idx == 0 else "Pending",
                "program_number": prog_idx,
                "program_source": src_name,
                "remaining_state_time_s": sec,
                "secondary_time_s": 0,
            }
            for idx, (stn, sec) in enumerate(runnable)
        ]
    else:
        device.uni_irrigation_queue = [{"program": prog_idx, "source": raw_src}]
    sync_core_queue_from_uni(device)
    return "0B20", "00"


def handle_uni_run_station(device: Any, body: bytes) -> UniRes:
    """Execute Universal 0220 manual station run and enqueue station state."""
    if not body:
        return "0320", "00"
    if len(body) >= 7:
        stn_idx = struct.unpack("<H", body[1:3])[0]
        dur_sec = struct.unpack("<I", body[3:7])[0]
    elif len(body) == 6:
        stn_idx = struct.unpack("<H", body[0:2])[0]
        dur_sec = struct.unpack("<I", body[2:6])[0]
    elif len(body) >= 4:
        stn_idx = struct.unpack("<H", body[0:2])[0]
        dur_sec = struct.unpack("<H", body[2:4])[0]
    else:
        return "0100", "01"
    max_sec = device.profile.maximum_manual_run_seconds
    if stn_idx >= device.profile.maximum_stations or (
        max_sec > 0 and dur_sec > max_sec
    ):
        return "0100", "04"
    state = "Cycling" if not device.uni_irrigation_queue else "Pending"
    device.uni_irrigation_queue.append(
        {
            "station_number": stn_idx + 1,
            "state": state,
            "program_number": None,
            "program_source": "ManualStation",
            "remaining_state_time_s": dur_sec,
            "secondary_time_s": 0,
        }
    )
    sync_core_queue_from_uni(device)
    return "0320", "00"


def handle_uni_stop_station(device: Any, body: bytes) -> UniRes:
    """Execute Universal 0420 single-station stop."""
    if len(body) >= 2:
        target_stn = struct.unpack("<H", body[0:2])[0] + 1
        device.uni_irrigation_queue = [
            r
            for r in device.uni_irrigation_queue
            if int(r.get("station_number", 0)) != target_stn
        ]
    elif device.uni_irrigation_queue:
        device.uni_irrigation_queue.pop(0)
    sync_core_queue_from_uni(device)
    return "0520", "00"


def handle_uni_stop_all(device: Any, op: str) -> UniRes:
    """Execute Universal 0620 / 0820 stop program / stop all irrigation."""
    device.uni_irrigation_queue.clear()
    sync_core_queue_from_uni(device)
    return ("0720" if op == "0620" else "0920"), "00"


def handle_uni_advance_station(device: Any) -> UniRes:
    """Execute Universal 0C20 advance station."""
    if device.uni_irrigation_queue:
        device.uni_irrigation_queue.pop(0)
    sync_core_queue_from_uni(device)
    return "0D20", "00"


def format_uni_irrigation_queue_6720(device: Any, body: bytes) -> UniRes:
    """Format Universal 6720 queue response with 0-based station index and 13B records."""
    page = body[0] if body else 0
    stn_q = [r for r in device.uni_irrigation_queue if "station_number" in r]
    batch = stn_q[page * 16 : (page + 1) * 16]
    records = bytearray([0x00, page & 0xFF, len(batch) & 0xFF])
    for rec in batch:
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
        sec_t = int(rec.get("secondary_time_s", 0))
        records.extend(
            struct.pack("<HBBBII", stn_idx, st_code, prog_byte, src_code, rem_t, sec_t)
        )
    return "6720", records.hex().upper()


def format_universal_sip_queue_bb(device: Any, page: int) -> str:
    """Format Universal SIP 0x3B -> 0xBB queue summary (7B page 0, 34B page 1, 50B page >= 2)."""
    q = [r for r in device.uni_irrigation_queue if "station_number" in r]
    cycling = [r for r in q if str(r.get("state", "Cycling")) == "Cycling"]
    pending = [r for r in q if str(r.get("state", "")) != "Cycling"]
    if page == 0:
        stns_running = len(cycling) or (1 if device.active_station > 0 else 0)
        irr_type = 0
        if stns_running > 0:
            irr_type = 2 if device.manual_queue_count > 0 else 1
        return (
            f"BB00{irr_type & 0xFF:02X}{stns_running & 0xFF:02X}"
            f"{device.manual_queue_count & 0xFF:02X}"
            f"{device.auto_queue_count & 0xFF:02X}"
            f"{device.status_flags & 0xFF:02X}"
        )
    if page == 1:
        active_src = cycling if cycling else (q[:1] if q else [])
        buf = bytearray([0xBB, 0x01])
        for slot in range(8):
            if slot < len(active_src):
                rec = active_src[slot]
                p_num = rec.get("program_number")
                p_1b = 0 if p_num is None else (int(p_num) + 1) & 0xFF
                stn = int(rec.get("station_number", 0)) & 0xFF
                rem = int(rec.get("remaining_state_time_s", 0)) & 0xFFFF
                buf.extend(struct.pack("<BBH", p_1b, stn, rem))
            else:
                buf.extend(b"\x00\x00\x00\x00")
        return buf.hex().upper()
    start = (page - 2) * 8
    buf = bytearray([0xBB, page & 0xFF])
    for slot in range(8):
        idx = start + slot
        if idx < len(pending):
            rec = pending[idx]
            p_num = rec.get("program_number")
            p_1b = 0 if p_num is None else (int(p_num) + 1) & 0xFF
            stn = int(rec.get("station_number", 0)) & 0xFF
            rem = int(rec.get("remaining_state_time_s", 0)) & 0xFFFF
            buf.extend(struct.pack("<BBHH", p_1b, stn, rem, 0))
        else:
            buf.extend(b"\x00" * 6)
    return buf.hex().upper()


def handle_uni_get_mv_open_duration(device: Any) -> UniRes:
    """Format Universal 4C20 -> 4D20 MV manual open duration response."""
    if (
        not device.profile.master_valves_settings
        and device.mv_manual_open_duration_minutes == 0
    ):
        return "0100", "03"
    dur_le = (
        struct.pack("<H", device.mv_manual_open_duration_minutes & 0xFFFF).hex().upper()
    )
    return "4D20", dur_le


def handle_uni_get_flow_totalizers(device: Any) -> UniRes:
    """Format Universal 4E20 -> 4F20 flow totalizers response."""
    ft = device.flow_totalizer
    body = struct.pack(
        "<IIII",
        int(ft.get("current_month", 0)),
        int(ft.get("previous_month", 0)),
        int(ft.get("last_30_days", 0)),
        int(ft.get("previous_30_days", 0)),
    )
    return "4F20", body.hex().upper()


def handle_uni_clear_flow_totalizers(device: Any) -> UniRes:
    """Execute Universal 5020 -> 5120 flow totalizer reset."""
    device.flow_totalizer = {
        "current_month": 0,
        "previous_month": 0,
        "last_30_days": 0,
        "previous_30_days": 0,
    }
    return "5120", "00"


def handle_uni_get_current_flow_rates(device: Any) -> UniRes:
    """Format Universal 6420 -> 6520 live flow rate array."""
    buf = bytearray(struct.pack("<I", len(device.current_flow_rates_gpm)))
    for rate in device.current_flow_rates_gpm:
        buf.extend(struct.pack("<f", float(rate)))
    return "6520", buf.hex().upper()
