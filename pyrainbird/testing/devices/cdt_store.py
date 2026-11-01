"""Controller Data Table (CDT) read and write engine for Universal controllers.

Universal controllers expose subsystem `0x0C` inside SIP command `0x0C` to read
and write slices of the controller's N-dimensional configuration table:

- **Batch / single-block read (`070B -> 080B`, `030B -> 040B`)**: Reads one or
  more scalar (`0D`) or indexed (`1D`–`3D`) blocks in a single round-trip.
- **Run-length read (`1B0B -> 1C0B`)**: Returns the first value in a program's
  station runtime (`1500`) or start-time (`1D00`) slice along with how far that
  identical value repeats, allowing clients to skip reading all-zero or
  all-disabled rows.
- **Batch / single-block write (`050B -> 060B`, `010B -> 020B`)**: Validates
  all blocks in the request first and commits them atomically.
"""

from __future__ import annotations

import math
import struct
from typing import Any

from .cdt_schema import (
    CDT_SCHEMA,
    get_cdt_default,
    get_cdt_dim_limits,
    is_valid_cdt_write_width,
    validate_cdt_values,
)

RangePair = tuple[int, int]
ParsedWriteBlock = tuple[str, int, list[RangePair], list[Any]]


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


def _lookup_2d_cell(stored: Any, i0: int, i1: int, default_val: Any) -> Any:
    if isinstance(stored, dict) and str(i0) in stored:
        row = stored[str(i0)]
        if isinstance(row, list) and i1 < len(row):
            return row[i1]
    elif isinstance(stored, list) and i0 < len(stored):
        row = stored[i0]
        if isinstance(row, list) and i1 < len(row):
            return row[i1]
    return default_val


class CDTStore:
    """Universal Controller Data Table (CDT) multi-dimensional block processor."""

    def __init__(self, device: Any) -> None:
        self.device = device

    def _are_ranges_valid(self, data_id: str, ranges: list[RangePair]) -> bool:
        limits = get_cdt_dim_limits(self.device.profile, data_id)
        if len(limits) != len(ranges):
            return False
        return all(
            0 <= s_idx <= e_idx < dim_limit and e_idx < 0x00FF
            for (s_idx, e_idx), dim_limit in zip(ranges, limits, strict=True)
        )

    def handle_bunch_get(self, req_body: bytes) -> str:
        """Process CDT batch read (070B -> 080B) blocks."""
        if not req_body:
            return "00"
        block_count = req_body[0]
        offset = 1
        out = bytearray([block_count])

        for _ in range(block_count):
            if offset + 3 > len(req_body):
                return "00"
            data_id_bytes = req_body[offset : offset + 2]
            data_id = data_id_bytes.hex().upper()
            rank = req_body[offset + 2]
            offset += 3
            if offset + 4 * rank > len(req_body):
                out.extend(data_id_bytes + bytes([rank, 0x00]))
                break
            ranges, range_bytes, offset = self._unpack_ranges(req_body, offset, rank)
            schema = CDT_SCHEMA.get(data_id)
            if (
                schema is None
                or rank != schema[0]
                or not self._are_ranges_valid(data_id, ranges)
            ):
                out.extend(data_id_bytes + bytes([rank]) + range_bytes + bytes([0x00]))
                continue
            _, val_width, is_float, _ = schema
            def_val = get_cdt_default(self.device.profile, data_id)
            out.extend(data_id_bytes + bytes([rank]) + range_bytes)
            out.append(val_width & 0xFF)
            out.extend(
                self._read_block_payload(
                    data_id, rank, ranges, val_width, is_float, def_val
                )
            )
        return out.hex().upper()

    @staticmethod
    def _unpack_ranges(
        req_body: bytes, offset: int, rank: int
    ) -> tuple[list[RangePair], bytearray, int]:
        ranges: list[RangePair] = []
        range_bytes = bytearray()
        for _ in range(rank):
            s_idx, e_idx = struct.unpack("<HH", req_body[offset : offset + 4])
            ranges.append((s_idx, e_idx))
            range_bytes.extend(req_body[offset : offset + 4])
            offset += 4
        return ranges, range_bytes, offset

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
            if stored is None and data_id == "1400":
                val = self.device.rain_delay_days
            else:
                val = default_val if stored is None else stored
            return encode_cdt_scalar(val, val_width, is_float)
        if rank == 1:
            fallback_map = self.device.water_budget if data_id == "1800" else None
            return self._read_rank1(
                stored, ranges[0], val_width, is_float, default_val, fallback_map
            )
        if rank == 2:
            if data_id in ("1900", "8600") and (
                data_id == "8600" or ranges[0][0] < ranges[0][1]
            ):
                return self._read_rank2_col_bits(
                    stored, ranges[0], ranges[1], default_val
                )
            return self._read_rank2(
                stored, ranges[0], ranges[1], val_width, is_float, default_val
            )
        return self._read_rank3(
            stored, ranges[0], ranges[2], val_width, is_float, default_val
        )

    @staticmethod
    def _read_rank1(
        stored: Any,
        r0: RangePair,
        val_width: int,
        is_float: bool,
        default_val: Any,
        fallback_map: dict[int, int] | None = None,
    ) -> bytes:
        s_idx, e_idx = r0
        vals = []
        for idx in range(s_idx, e_idx + 1):
            if isinstance(stored, list) and idx < len(stored):
                vals.append(stored[idx])
            elif isinstance(stored, dict) and str(idx) in stored:
                vals.append(stored[str(idx)])
            elif fallback_map is not None and idx in fallback_map:
                vals.append(fallback_map[idx])
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
            row_vals = [
                _lookup_2d_cell(stored, i0, i1, default_val) for i1 in range(s1, e1 + 1)
            ]
            out.extend(_pack_cdt_values(row_vals, val_width, is_float))
        return bytes(out)

    @staticmethod
    def _read_rank2_col_bits(
        stored: Any, r0: RangePair, r1: RangePair, default_val: Any
    ) -> bytes:
        (s0, e0), (s1, e1) = r0, r1
        out = bytearray()
        for i1 in range(s1, e1 + 1):
            col_flags = [
                int(_lookup_2d_cell(stored, i0, i1, default_val)) != 0
                for i0 in range(s0, e0 + 1)
            ]
            out.extend(_pack_cdt_values(col_flags, 255, False))
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
                val = _lookup_2d_cell(stored, i0, i2, default_val)
                out.extend(encode_cdt_scalar(val, val_width, is_float))
        return bytes(out)

    def handle_bunch_set(self, req_body: bytes) -> str:
        """Validate and atomically apply CDT batch write (050B -> 060B) blocks."""
        if not req_body or req_body[0] == 0:
            return "01"
        block_count = req_body[0]
        offset = 1
        parsed: list[ParsedWriteBlock] = []

        for _ in range(block_count):
            err, block, offset = self._parse_and_validate_write_block(req_body, offset)
            if err is not None or block is None:
                return err or "01"
            parsed.append(block)

        if offset != len(req_body):
            return "01"
        for data_id, rank, ranges, values in parsed:
            self._commit_write_block(data_id, rank, ranges, values)
        return "00"

    def _parse_and_validate_write_block(
        self, req_body: bytes, offset: int
    ) -> tuple[str | None, ParsedWriteBlock | None, int]:
        if offset + 3 > len(req_body):
            return "01", None, offset
        data_id = req_body[offset : offset + 2].hex().upper()
        rank = req_body[offset + 2]
        offset += 3
        schema = CDT_SCHEMA.get(data_id)
        if schema is None:
            return "03", None, offset
        if rank != schema[0]:
            return "02", None, offset
        if offset + 4 * rank + 1 > len(req_body):
            return "01", None, offset
        ranges, _, offset = self._unpack_ranges(req_body, offset, rank)
        req_width = req_body[offset]
        offset += 1
        if not self._are_ranges_valid(data_id, ranges):
            return "04", None, offset
        if not is_valid_cdt_write_width(data_id, schema[1], req_width):
            return "05", None, offset
        values, next_offset = self._decode_write_values(
            req_body, offset, data_id, ranges, req_width, schema[2]
        )
        if values is None:
            return "01", None, offset
        if not validate_cdt_values(self.device.profile, data_id, values):
            return "01", None, offset
        return None, (data_id, rank, ranges, values), next_offset

    @staticmethod
    def _decode_write_values(
        req_body: bytes,
        offset: int,
        data_id: str,
        ranges: list[RangePair],
        req_width: int,
        is_float: bool,
    ) -> tuple[list[Any] | None, int]:
        counts = [e - s + 1 for s, e in ranges]
        total_elems = math.prod(counts) if counts else 1
        if req_width == 255:
            if len(counts) == 2 and data_id in ("1900", "8600"):
                b_per_col = math.ceil(counts[0] / 8)
                needed = b_per_col * counts[1]
                if offset + needed > len(req_body):
                    return None, offset
                grid = [[0] * counts[1] for _ in range(counts[0])]
                for c1 in range(counts[1]):
                    chunk = req_body[
                        offset + c1 * b_per_col : offset + (c1 + 1) * b_per_col
                    ]
                    for c0 in range(counts[0]):
                        grid[c0][c1] = (chunk[c0 // 8] >> (c0 % 8)) & 1
                return [v for row in grid for v in row], offset + needed
            row_len = counts[-1] if counts else 1
            outer = total_elems // row_len
            b_per_row = math.ceil(row_len / 8)
            needed = outer * b_per_row
            if offset + needed > len(req_body):
                return None, offset
            vals: list[Any] = []
            for r_idx in range(outer):
                chunk = req_body[
                    offset + r_idx * b_per_row : offset + (r_idx + 1) * b_per_row
                ]
                vals.extend((chunk[i // 8] >> (i % 8)) & 1 for i in range(row_len))
            return vals, offset + needed
        needed = total_elems * req_width
        if offset + needed > len(req_body):
            return None, offset
        vals = []
        for _ in range(total_elems):
            val, used = decode_cdt_scalar(req_body[offset:], req_width, is_float)
            offset += used
            vals.append(val)
        return vals, offset

    def _commit_write_block(
        self, data_id: str, rank: int, ranges: list[RangePair], values: list[Any]
    ) -> None:
        def_val = get_cdt_default(self.device.profile, data_id)
        if rank == 0:
            self.device.cdt_store[data_id] = values[0]
            if data_id == "1400":
                self.device.rain_delay_days = int(values[0])
            return
        if rank == 1:
            s0, e0 = ranges[0]
            arr = list(self.device.cdt_store.get(data_id, [def_val] * (e0 + 1)))
            while len(arr) <= e0:
                arr.append(def_val)
            for offset_i, idx in enumerate(range(s0, e0 + 1)):
                arr[idx] = values[offset_i]
                if data_id == "1800":
                    pct = int(values[offset_i])
                    self.device.water_budget[idx] = pct
                    if idx == 0:
                        self.device.seasonal_adjust = pct
            self.device.cdt_store[data_id] = arr
            return
        (s0, e0), (s_inner, e_inner) = ranges[0], ranges[-1]
        store_dict = self.device.cdt_store.setdefault(data_id, {})
        v_pos = 0
        for i0 in range(s0, e0 + 1):
            row = list(store_dict.get(str(i0), [def_val] * (e_inner + 1)))
            while len(row) <= e_inner:
                row.append(def_val)
            for idx_in in range(s_inner, e_inner + 1):
                row[idx_in] = values[v_pos]
                v_pos += 1
            store_dict[str(i0)] = row

    def handle_bunch_get_same(self, req_body: bytes) -> str:
        """Process CDT run-length read (1B0B -> 1C0B) blocks."""
        if not req_body:
            return "00"
        block_count = req_body[0]
        offset = 1
        out = bytearray([block_count])

        for _ in range(block_count):
            if offset + 3 > len(req_body):
                return "00"
            data_id_bytes = req_body[offset : offset + 2]
            data_id = data_id_bytes.hex().upper()
            rank = req_body[offset + 2]
            offset += 3
            if offset + 4 * rank > len(req_body):
                out.extend(data_id_bytes + bytes([rank, 0x00]))
                break
            ranges, range_bytes, offset = self._unpack_ranges(req_body, offset, rank)
            if not self._are_ranges_valid(data_id, ranges):
                out.extend(data_id_bytes + bytes([rank]) + range_bytes + bytes([0x00]))
                continue
            if data_id == "1500" and rank == 2 and ranges[0][0] == ranges[0][1]:
                out.extend(self._get_same_1500(data_id_bytes, range_bytes, ranges))
            elif data_id == "1D00" and rank == 3 and ranges[0][0] == ranges[0][1]:
                out.extend(self._get_same_1d00(data_id_bytes, range_bytes, ranges))
            else:
                out.extend(data_id_bytes + bytes([rank]) + range_bytes + bytes([0x00]))
        return out.hex().upper()

    def _get_same_1500(
        self, data_id_bytes: bytes, range_bytes: bytearray, ranges: list[RangePair]
    ) -> bytes:
        prog_idx = ranges[0][0]
        s_stn, e_stn = ranges[1]
        raw_row = self.device.cdt_1500.get(
            str(prog_idx),
            self.device.cdt_store.get("1500", {}).get(str(prog_idx), []),
        )
        slice_vals = [
            int(raw_row[stn]) if stn < len(raw_row) else 0
            for stn in range(s_stn, e_stn + 1)
        ]
        first_val = slice_vals[0]
        same_until_stn = s_stn
        for offset_i, val in enumerate(slice_vals):
            if val == first_val:
                same_until_stn = s_stn + offset_i
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
        prog_idx = ranges[0][0]
        s_slot, e_slot = ranges[2]
        raw_row = self.device.cdt_1d00.get(
            str(prog_idx),
            self.device.cdt_store.get("1D00", {}).get(str(prog_idx), []),
        )
        slice_vals = [
            int(raw_row[slot]) if slot < len(raw_row) else 1440
            for slot in range(s_slot, e_slot + 1)
        ]
        first_val = slice_vals[0]
        same_until_slot = s_slot
        for offset_i, val in enumerate(slice_vals):
            if val == first_val:
                same_until_slot = s_slot + offset_i
            else:
                break
        return (
            bytes(data_id_bytes)
            + bytes([3])
            + bytes(range_bytes)
            + bytes([2])
            + struct.pack("<HHHH", first_val, prog_idx, 0, same_until_slot)
        )
