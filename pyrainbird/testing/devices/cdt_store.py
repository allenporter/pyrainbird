"""CDTStore implementing 0D-3D CDT batch read, write, and run-length read operations."""

from __future__ import annotations

import math
import struct
from typing import Any

from .constants import CDT_SCHEMA

RangePair = tuple[int, int]


def encode_cdt_scalar(val: Any, width: int, is_float: bool) -> bytes:
    """Encode a single CDT scalar value into Little-Endian wire bytes."""
    if is_float and width == 4:
        return struct.pack("<f", float(val))
    int_val = int(val)
    if width in (1, 255):
        return bytes([int_val & 0xFF])
    if width == 2:
        return struct.pack("<H", int_val & 0xFFFF)
    if width == 4:
        return struct.pack("<I", int_val & 0xFFFFFFFF)
    return b""


def decode_cdt_scalar(buf: bytes, width: int, is_float: bool) -> tuple[Any, int]:
    """Decode a single CDT scalar value from Little-Endian wire bytes."""
    if is_float and width == 4:
        return struct.unpack("<f", buf[:4])[0], 4
    if width in (1, 255):
        return buf[0], 1
    if width == 2:
        return struct.unpack("<H", buf[:2])[0], 2
    if width == 4:
        return struct.unpack("<I", buf[:4])[0], 4
    return 0, 0


def _pack_cdt_values(vals: list[Any], val_width: int, is_float: bool) -> bytes:
    if val_width == 255:
        packed = bytearray(math.ceil(len(vals) / 8))
        for i, flag in enumerate(vals):
            if bool(flag):
                packed[i // 8] |= 1 << (i % 8)
        return bytes(packed)
    out = bytearray()
    for v in vals:
        out.extend(encode_cdt_scalar(v, val_width, is_float))
    return bytes(out)


class CDTStore:
    """Universal Controller Data Table (CDT) multi-dimensional block processor."""

    def __init__(self, device: Any) -> None:
        self.device = device

    def handle_bunch_get(self, req_body: bytes) -> str:
        """Process CDT batch read (070B -> 080B) blocks."""
        if not req_body:
            return "00"
        block_count = req_body[0]
        offset = 1
        out = bytearray([block_count])

        for _ in range(block_count):
            if offset + 3 > len(req_body):
                break
            data_id_bytes = req_body[offset : offset + 2]
            data_id = data_id_bytes.hex().upper()
            rank = req_body[offset + 2]
            offset += 3

            ranges: list[RangePair] = []
            range_bytes = bytearray()
            for _ in range(rank):
                s_idx, e_idx = struct.unpack("<HH", req_body[offset : offset + 4])
                ranges.append((s_idx, e_idx))
                range_bytes.extend(req_body[offset : offset + 4])
                offset += 4

            schema = CDT_SCHEMA.get(data_id)
            if (
                schema is None
                or rank != schema[0]
                or any(e_idx >= 0x00FF or e_idx < s_idx for s_idx, e_idx in ranges)
            ):
                out.extend(data_id_bytes)
                out.append(rank)
                out.extend(range_bytes)
                out.append(0x00)
                continue

            _, val_width, is_float, default_val = schema
            out.extend(data_id_bytes)
            out.append(rank)
            out.extend(range_bytes)
            out.append(val_width & 0xFF)
            out.extend(
                self._read_block_payload(
                    data_id, rank, ranges, val_width, is_float, default_val
                )
            )

        return out.hex().upper()

    def _read_block_payload(
        self,
        data_id: str,
        rank: int,
        ranges: list[RangePair],
        val_width: int,
        is_float: bool,
        default_val: Any,
    ) -> bytes:
        stored = self.device.cdt_store.get(data_id)
        if rank == 0:
            val = default_val if stored is None else stored
            return encode_cdt_scalar(val, val_width, is_float)
        if rank == 1:
            return self._read_rank1(stored, ranges[0], val_width, is_float, default_val)
        if rank == 2:
            return self._read_rank2(
                stored, ranges[0], ranges[1], val_width, is_float, default_val
            )
        return self._read_rank3(
            stored, ranges[0], ranges[2], val_width, is_float, default_val
        )

    def sync_from_device(self) -> None:
        """Synchronize canonical device state into cdt_store after legacy SIP writes."""
        dev = self.device
        n_prog = max(1, dev.profile.maximum_programs)
        dev.cdt_store.update(
            {
                "1400": dev.rain_delay_days,
                "0D00": 1 if dev.rain_sensor_bypassed else 0,
                "0C00": [dev.inter_station_delay_seconds] * n_prog,
                "1600": [dev.monthly_water_budget.get(m, 100) for m in range(12)],
                "1800": [dev.water_budget.get(p, 100) for p in range(n_prog)],
            }
        )
        for p_num, prog in dev.programs.items():
            if any(0 <= s < 1440 for s in prog.start_times_minutes):
                dev.cdt_store.setdefault("1D00", {})[str(p_num - 1)] = [
                    s if 0 <= s < 1440 else 1440 for s in prog.start_times_minutes
                ]

    @staticmethod
    def _read_rank1(
        stored: Any, r0: RangePair, val_width: int, is_float: bool, default_val: Any
    ) -> bytes:
        s_idx, e_idx = r0
        vals = []
        for idx in range(s_idx, e_idx + 1):
            if isinstance(stored, list) and idx < len(stored):
                vals.append(stored[idx])
            elif isinstance(stored, dict) and str(idx) in stored:
                vals.append(stored[str(idx)])
            else:
                vals.append(default_val)
        return _pack_cdt_values(vals, val_width, is_float)

    @staticmethod
    def _read_rank2(
        stored: Any,
        r0: RangePair,
        r1: RangePair,
        val_width: int,
        is_float: bool,
        default_val: Any,
    ) -> bytes:
        (s0, e0), (s1, e1) = r0, r1
        out = bytearray()
        for i0 in range(s0, e0 + 1):
            row_vals = []
            for i1 in range(s1, e1 + 1):
                v = default_val
                if isinstance(stored, dict) and str(i0) in stored:
                    r = stored[str(i0)]
                    if isinstance(r, list) and i1 < len(r):
                        v = r[i1]
                elif isinstance(stored, list) and i0 < len(stored):
                    r = stored[i0]
                    if isinstance(r, list) and i1 < len(r):
                        v = r[i1]
                row_vals.append(v)
            out.extend(_pack_cdt_values(row_vals, val_width, is_float))
        return bytes(out)

    @staticmethod
    def _read_rank3(
        stored: Any,
        r0: RangePair,
        r2: RangePair,
        val_width: int,
        is_float: bool,
        default_val: Any,
    ) -> bytes:
        (s0, e0), (s2, e2) = r0, r2
        out = bytearray()
        for i0 in range(s0, e0 + 1):
            for i2 in range(s2, e2 + 1):
                v = default_val
                if isinstance(stored, dict) and str(i0) in stored:
                    r = stored[str(i0)]
                    if isinstance(r, list) and i2 < len(r):
                        v = r[i2]
                out.extend(encode_cdt_scalar(v, val_width, is_float))
        return bytes(out)

    def handle_bunch_set(self, req_body: bytes) -> str:
        """Process CDT batch write (050B -> 060B) blocks."""
        if not req_body:
            return "01"
        block_count = req_body[0]
        offset = 1

        for _ in range(block_count):
            if offset + 3 > len(req_body):
                return "01"
            data_id = req_body[offset : offset + 2].hex().upper()
            rank = req_body[offset + 2]
            offset += 3

            ranges: list[RangePair] = []
            for _ in range(rank):
                s_idx, e_idx = struct.unpack("<HH", req_body[offset : offset + 4])
                ranges.append((s_idx, e_idx))
                offset += 4

            val_width = req_body[offset]
            offset += 1
            schema = CDT_SCHEMA.get(data_id)
            if schema is None:
                return "03"
            offset = self._write_block_payload(
                req_body, offset, data_id, rank, ranges, val_width, schema[2]
            )
            self._sync_from_cdt(data_id)

        return "00"

    def _sync_from_cdt(self, data_id: str) -> None:
        stored = self.device.cdt_store.get(data_id)
        if stored is None:
            return
        if data_id == "1400":
            self.device.rain_delay_days = int(stored)
        elif data_id == "0D00":
            self.device.rain_sensor_bypassed = int(stored) != 0
        elif data_id == "0C00" and isinstance(stored, list) and stored:
            self.device.inter_station_delay_seconds = int(stored[0])
        elif data_id == "1600" and isinstance(stored, list):
            for idx, val in enumerate(stored):
                self.device.monthly_water_budget[idx] = int(val)
        elif data_id == "1800" and isinstance(stored, list):
            for idx, val in enumerate(stored):
                self.device.water_budget[idx] = int(val)
                if idx == 0:
                    self.device.seasonal_adjust = int(val)
                if (idx + 1) in self.device.programs:
                    self.device.programs[idx + 1].seasonal_adjust = int(val)
        elif data_id == "1500" and isinstance(stored, dict):
            for p_str, row in stored.items():
                p_idx = int(p_str)
                for s_idx, sec in enumerate(row):
                    stn = s_idx + 1
                    runs = self.device.station_run_times.setdefault(
                        stn, [0] * max(p_idx + 1, self.device.profile.maximum_programs)
                    )
                    while len(runs) <= p_idx:
                        runs.append(0)
                    runs[p_idx] = (
                        int(sec)
                        if self.device.profile.is_battery_based
                        else int(sec) // 60
                    )
        elif data_id == "1D00" and isinstance(stored, dict):
            for p_str, row in stored.items():
                p_num = int(p_str) + 1
                if p_num in self.device.programs:
                    self.device.programs[p_num].start_times_minutes = [
                        int(v) if 0 <= int(v) < 1440 else 0xFFFF for v in row
                    ]

    def _write_block_payload(
        self,
        req_body: bytes,
        offset: int,
        data_id: str,
        rank: int,
        ranges: list[RangePair],
        val_width: int,
        is_float: bool,
    ) -> int:
        if rank == 0:
            val, used = decode_cdt_scalar(req_body[offset:], val_width, is_float)
            self.device.cdt_store[data_id] = val
            return offset + used
        if rank == 1:
            return self._write_rank1(
                req_body, offset, data_id, ranges[0], val_width, is_float
            )
        if rank == 2:
            return self._write_rank2(
                req_body, offset, data_id, ranges[0], ranges[1], val_width, is_float
            )
        return self._write_rank3(
            req_body, offset, data_id, ranges[0], ranges[2], val_width, is_float
        )

    def _write_rank1(
        self,
        req_body: bytes,
        offset: int,
        data_id: str,
        r0: RangePair,
        val_width: int,
        is_float: bool,
    ) -> int:
        s_idx, e_idx = r0
        count = e_idx - s_idx + 1
        arr = list(self.device.cdt_store.get(data_id, [0] * (e_idx + 1)))
        while len(arr) <= e_idx:
            arr.append(0)
        if val_width == 255:
            num_bytes = math.ceil(count / 8)
            packed = req_body[offset : offset + num_bytes]
            for i in range(count):
                arr[s_idx + i] = (packed[i // 8] >> (i % 8)) & 1
            self.device.cdt_store[data_id] = arr
            return offset + num_bytes
        for idx in range(s_idx, e_idx + 1):
            val, used = decode_cdt_scalar(req_body[offset:], val_width, is_float)
            offset += used
            arr[idx] = val
        self.device.cdt_store[data_id] = arr
        return offset

    def _write_rank2(
        self,
        req_body: bytes,
        offset: int,
        data_id: str,
        r0: RangePair,
        r1: RangePair,
        val_width: int,
        is_float: bool,
    ) -> int:
        (s0, e0), (s1, e1) = r0, r1
        c1 = e1 - s1 + 1
        store_dict = self.device.cdt_store.setdefault(data_id, {})
        for i0 in range(s0, e0 + 1):
            row = list(store_dict.get(str(i0), [0] * (e1 + 1)))
            while len(row) <= e1:
                row.append(0)
            if val_width == 255:
                num_bytes = math.ceil(c1 / 8)
                packed = req_body[offset : offset + num_bytes]
                offset += num_bytes
                for i in range(c1):
                    row[s1 + i] = (packed[i // 8] >> (i % 8)) & 1
            else:
                for i1 in range(s1, e1 + 1):
                    val, used = decode_cdt_scalar(
                        req_body[offset:], val_width, is_float
                    )
                    offset += used
                    row[i1] = val
            store_dict[str(i0)] = row
        return offset

    def _write_rank3(
        self,
        req_body: bytes,
        offset: int,
        data_id: str,
        r0: RangePair,
        r2: RangePair,
        val_width: int,
        is_float: bool,
    ) -> int:
        (s0, e0), (s2, e2) = r0, r2
        store_dict = self.device.cdt_store.setdefault(data_id, {})
        for i0 in range(s0, e0 + 1):
            row = list(store_dict.get(str(i0), [1440] * (e2 + 1)))
            while len(row) <= e2:
                row.append(1440)
            for i2 in range(s2, e2 + 1):
                val, used = decode_cdt_scalar(req_body[offset:], val_width, is_float)
                offset += used
                row[i2] = val
            store_dict[str(i0)] = row
        return offset

    def handle_bunch_get_same(self, req_body: bytes) -> str:
        """Process CDT run-length read (1B0B -> 1C0B) blocks."""
        if not req_body:
            return "00"
        block_count = req_body[0]
        offset = 1
        out = bytearray([block_count])

        for _ in range(block_count):
            data_id_bytes = req_body[offset : offset + 2]
            data_id = data_id_bytes.hex().upper()
            rank = req_body[offset + 2]
            offset += 3

            ranges: list[RangePair] = []
            range_bytes = bytearray()
            for _ in range(rank):
                s_idx, e_idx = struct.unpack("<HH", req_body[offset : offset + 4])
                ranges.append((s_idx, e_idx))
                range_bytes.extend(req_body[offset : offset + 4])
                offset += 4

            if data_id == "1500" and rank == 2:
                out.extend(self._get_same_1500(data_id_bytes, range_bytes, ranges))
            elif data_id == "1D00" and rank == 3:
                out.extend(self._get_same_1d00(data_id_bytes, range_bytes, ranges))

        return out.hex().upper()

    def _get_same_1500(
        self, data_id_bytes: bytes, range_bytes: bytearray, ranges: list[RangePair]
    ) -> bytes:
        prog_idx, end_stn = ranges[0][0], ranges[1][1]
        runs = self.device.cdt_1500.get(
            str(prog_idx),
            self.device.cdt_store.get("1500", {}).get(
                str(prog_idx), [0] * (end_stn + 1)
            ),
        )
        first_val = int(runs[0]) if runs else 0
        same_until_stn = 0
        for idx, val in enumerate(runs):
            if int(val) == first_val:
                same_until_stn = idx
            else:
                break
        return (
            bytes(data_id_bytes)
            + bytes([2])
            + bytes(range_bytes)
            + bytes([4])
            + struct.pack("<IHH", first_val, prog_idx, same_until_stn)
        )

    def _get_same_1d00(
        self, data_id_bytes: bytes, range_bytes: bytearray, ranges: list[RangePair]
    ) -> bytes:
        prog_idx, end_slot = ranges[0][0], ranges[2][1]
        starts = self.device.cdt_1d00.get(
            str(prog_idx),
            self.device.cdt_store.get("1D00", {}).get(
                str(prog_idx), [1440] * (end_slot + 1)
            ),
        )
        first_val = int(starts[0]) if starts else 1440
        same_until_slot = 0
        for idx, val in enumerate(starts):
            if int(val) == first_val:
                same_until_slot = idx
            else:
                break
        return (
            bytes(data_id_bytes)
            + bytes([3])
            + bytes(range_bytes)
            + bytes([2])
            + struct.pack("<HHHH", first_val, prog_idx, 0, same_until_slot)
        )
