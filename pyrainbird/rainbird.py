"""Library for encoding and decoding rainbird tunnelSip commands."""

import logging
from collections.abc import Callable
from typing import Any

from .const import ProgramFrequency
from .exceptions import RainbirdCodingException
from .resources import (
    DECODER,
    LENGTH,
    POSITION,
    RAINBIRD_COMMANDS,
    RAINBIRD_COMMANDS_BY_ID,
    RESERVED_FIELDS,
    TYPE,
)

_LOGGER = logging.getLogger(__name__)

# The LCR series (ESP-RZXe / ST8) encodes the schedule frequency of a zone with
# a different set of values than the program based devices, following the order
# the Rain Bird app shows them in: custom, odd, even, cyclic.
_LCR_FREQUENCY: dict[int, int] = {
    0: ProgramFrequency.CUSTOM,
    1: ProgramFrequency.ODD,
    2: ProgramFrequency.EVEN,
    3: ProgramFrequency.CYCLIC,
}

_LCR_FREQUENCY_CODE: dict[int, int] = {v: k for k, v in _LCR_FREQUENCY.items()}

# Number of start times an LCR series zone can hold, and the value used for the
# slots that are left unused.
_LCR_MAX_STARTS = 6
_LCR_UNUSED_START = 0x90

# The resolution the LCR series stores start times with.
_LCR_START_RESOLUTION = 10

# Minutes in a day. A start time slot that does not hold a valid time of day is
# reported as 0x90 (1440 minutes) by the ESP-RZXe and as 0xFF by other devices.
_MINUTES_PER_DAY = 24 * 60

# Program-based SIP controllers (ESP-ME, ESP-TM2, ESP-TM2v2/v3, TRU) encode the
# program water cycle in schedule subpage 0x10..0x13 byte 5 as:
# 0=Custom, 1=Cyclic, 2=Odd (or Odd excluding 31st), 3=Even, 4=Off, 5=Odd.
_PROGRAM_FREQUENCY: dict[int, int] = {
    0: ProgramFrequency.CUSTOM,
    1: ProgramFrequency.CYCLIC,
    2: ProgramFrequency.ODD,
    3: ProgramFrequency.EVEN,
    4: ProgramFrequency.OFF,
    5: ProgramFrequency.ODD,
}

# Universal controllers (ARC8, RC2, ESP-ME3, ESP-2WIRE, LX*) store schedules in
# an indexed Controller Data Table (CDT) accessed via SIP command 0x0C -> 0x8C
# (batch read 0x070B -> 0x080B). Each table is addressed by a 2-byte little-endian
# Data ID and 0D-3D index ranges.
_UNIVERSAL_REQUEST_HEADER = bytes.fromhex("0C200001000805000000000C000000000005000000")
_CDT_BUNCH_GET_REQUEST = b"\x07\x0b"
_CDT_BUNCH_GET_RESPONSE = b"\x08\x0b"
# Each SIP serial frame between the WiFi module and controller uses a 1-byte
# payload length (<= 255 bytes), so CDT schedule reads slice program metadata
# into groups of 5 programs and station runtimes into groups of 25 stations.
_UNIVERSAL_PROGRAM_CHUNK_SIZE = 5
_UNIVERSAL_STATION_CHUNK_SIZE = 25

_CDI_GLOBAL_SENSOR_BYPASS = 0x0D
_CDI_PROGRAM_CUSTOM_DAYS = 0x10
_CDI_PROGRAM_CYCLE_COUNT = 0x11
_CDI_PROGRAM_CYCLE_DAYS = 0x12
_CDI_PROGRAM_CYCLE_TYPE = 0x13
_CDI_RAIN_DELAY = 0x14
_CDI_RUN_TIMES = 0x15
_CDI_SEASONAL_ADJUST_BY_PROGRAM = 0x18
_CDI_START_TIMES = 0x1D

# Universal CDT table 0x13 encodes program water cycle types as:
# 0=Custom, 1=Odd, 2=Odd (excluding 31st), 3=Even, 4=Cyclic, 5=Off (disabled).
_UNIVERSAL_FREQUENCY: dict[int, int] = {
    0: ProgramFrequency.CUSTOM,
    1: ProgramFrequency.ODD,
    2: ProgramFrequency.ODD,
    3: ProgramFrequency.EVEN,
    4: ProgramFrequency.CYCLIC,
    5: ProgramFrequency.OFF,
}


def decode_template(data: str, cmd_template: dict[str, Any]) -> dict[str, int]:
    """Decode the command from the template in yaml."""
    result = {}
    for k, v in cmd_template.items():
        if (
            isinstance(v, dict)
            and (position := v.get(POSITION))
            and (length := v.get(LENGTH))
        ):
            result[k] = int(data[position : position + length], 16)
    return result


def decode_schedule(data: str, cmd_template: dict[str, Any]) -> dict[str, Any]:
    """Decode a schedule command."""
    subcommand = int(data[4:6], 16)
    rest: str | bytes = data[6:]
    if subcommand == 0:
        if len(rest) == 4:
            # LCR series global info: A0 00 00 00 SS
            return {
                "controllerInfo": {
                    "rainSensor": int(rest[2:4], 16),
                }
            }
        if len(rest) < 8:
            return {}
        # Delay, Snooze, Rainsensor
        return {
            "controllerInfo": {
                "stationDelay": int(rest[0:4], 16),
                "rainDelay": int(rest[4:6], 16),
                "rainSensor": int(rest[6:8], 16),
            }
        }

    if subcommand & 16 == 16:
        if len(rest) < 10:
            return {}
        program = subcommand & ~16
        fields = [int(rest[i : i + 2], 16) for i in range(0, len(rest), 2)]
        return {
            "programInfo": {
                "program": program,
                "daysOfWeekMask": fields[0],
                "period": fields[1],
                "synchro": fields[2],
                "permanentDaysOff": fields[3],
                "reserved": fields[4],
                "frequency": _PROGRAM_FREQUENCY.get(fields[5], ProgramFrequency.OFF),
            }
        }

    if subcommand & 96 == 96:
        if len(rest) < 4:
            return {}
        program = subcommand & ~96
        # Note: 65535 is disabled
        entries = [int(rest[i : i + 4], 16) for i in range(0, len(rest), 4)]
        return {
            "programStartInfo": {
                "program": program,
                "startTime": entries,
            }
        }

    if subcommand & 128 == 128:
        if len(rest) < 4:
            return {}
        station = subcommand & ~128
        rest = bytes(data[6:], "utf-8")
        durations = [int(rest[i : i + 4], 16) for i in range(0, len(rest), 4)]
        numPrograms = int(len(durations) / 2)
        return {
            "durations": [
                {
                    "zone": station * 2,
                    "durations": durations[0:numPrograms],
                },
                {
                    "zone": station * 2 + 1,
                    "durations": durations[numPrograms : 2 * numPrograms],
                },
            ],
        }

    # LCR Series (ESP-RZXe / ST8) per-zone schedules
    if 0 < subcommand < 16 and len(data) == 28:
        duration = int(rest[0:2], 16)
        starts = []
        for i in range(6):
            val = int(rest[2 + i * 2 : 4 + i * 2], 16) * 10
            if val < _MINUTES_PER_DAY:
                starts.append(val)

        frequency = int(rest[14:16], 16)
        return {
            "zoneInfo": {
                subcommand: {
                    "zone": subcommand,
                    "duration": duration,
                    "startTime": starts,
                    "frequency": _LCR_FREQUENCY.get(frequency, frequency),
                    "daysOfWeekMask": int(rest[16:18], 16),
                    "period": int(rest[18:20], 16),
                    "synchro": int(rest[20:22], 16) & 0x7F,
                }
            }
        }

    return {"data": data}


def encode_zone_schedule(
    duration: int,
    starts: list[int],
    frequency: int = ProgramFrequency.CUSTOM,
    days_of_week_mask: int = 0,
    period: int = 0,
    synchro: int = 0,
) -> str:
    """Encode the schedule body of a zone of an LCR series device.

    This is the counterpart of the zone information returned by
    `decode_schedule` and is passed to a `SetScheduleRequest`. Durations and
    start times are in minutes; start times are stored with a resolution of
    ten minutes.
    """
    if not 1 <= duration <= 255:
        raise RainbirdCodingException(
            f"Duration must be between 1 and 255 minutes: {duration}"
        )
    if len(starts) > _LCR_MAX_STARTS:
        raise RainbirdCodingException(
            f"A zone holds at most {_LCR_MAX_STARTS} start times: {starts}"
        )
    slots = []
    for start in starts:
        if not 0 <= start < _MINUTES_PER_DAY or start % _LCR_START_RESOLUTION:
            raise RainbirdCodingException(
                f"Start time must be a time of day on a "
                f"{_LCR_START_RESOLUTION} minute boundary: {start}"
            )
        slots.append(start // _LCR_START_RESOLUTION)
    if (frequency_code := _LCR_FREQUENCY_CODE.get(frequency)) is None:
        raise RainbirdCodingException(f"Unsupported frequency: {frequency}")
    slots.extend([_LCR_UNUSED_START] * (_LCR_MAX_STARTS - len(slots)))
    body = bytes(
        [duration, *slots, frequency_code, days_of_week_mask & 0x7F, period, synchro]
    )
    return body.hex().upper()


def decode_queue(data: str, cmd_template: dict[str, Any]) -> dict[str, Any]:
    """Decode a queue command."""
    page = int(data[2:4], 16)
    rest = data[4:]
    if page == 0:
        # Currently running program
        if len(data) == 24:  # TM2 etc
            runtime = int(data[8:12], 16)
            program = int(data[18:20], 16)
            if program > 4:  # Max programs differs by device
                program = 0
            return {
                "program": {
                    "seconds": runtime,
                    "program": program,
                    "zone": int(data[16:18], 16),
                    "active": (runtime > 0),
                }
            }
        if len(data) == 14:  # me3
            return {
                "program": {
                    "program": int(rest[0:2], 16),
                    "running": bool(int(rest[2:4], 16)),
                    "zonesRemaining": int(rest[4:6], 16),
                }
            }
        return {"data": data}

    if page == 1:
        queue = []
        if len(data) == 70:  # TM2
            for i in range(11):
                base = i * 6
                zone = int(data[base + 4 : base + 6], 16) & 31
                runtime = int(data[base + 6 : base + 10], 16)
                if zone:
                    queue.append({"zone": zone, "seconds": runtime})
        else:  # ME3
            for i in range(8):
                base = i * 8
                program = int(data[base + 4 : base + 6], 16)
                zone = int(data[base + 6 : base + 8], 16)
                runtime = int(data[base + 8 : base + 12], 16)
                if runtime > 0:
                    runtime = ((runtime & 0xFF00) >> 8) | ((runtime & 0xFF) << 8)
                if zone:
                    queue.append({"program": program, "zone": zone, "seconds": runtime})
        return {"zones": queue}

    if len(data) == 100:
        queue = []
        for i in range(8):
            base = i * 12
            program = int(data[base + 4 : base + 6], 16)
            zone = int(data[base + 6 : base + 8], 16)
            runtime = int(data[base + 8 : base + 12], 16)
            if runtime > 0:
                runtime = ((runtime & 0xFF00) >> 8) | ((runtime & 0xFF) << 8)
            if zone:
                queue.append({"program": program, "zone": zone, "seconds": runtime})
        return {"zones": queue}

    return {"data": data}


def encode_universal_bunch_get_request(
    blocks: list[tuple[int, list[tuple[int, int]]]],
) -> str:
    """Encode a Universal (0x0C) CDT bunch get request."""
    block_bytes = bytearray()
    for table_id, ranges in blocks:
        block_bytes.extend(table_id.to_bytes(2, "little"))
        block_bytes.append(len(ranges))
        for start, end in ranges:
            block_bytes.extend(start.to_bytes(2, "little"))
            block_bytes.extend(end.to_bytes(2, "little"))
    inner = _CDT_BUNCH_GET_REQUEST + bytes([len(blocks)]) + bytes(block_bytes)
    frame = _UNIVERSAL_REQUEST_HEADER + len(inner).to_bytes(2, "little") + inner
    return frame.hex().upper()


def encode_universal_schedule_commands(
    max_programs: int, max_run_times: int, max_stations: int
) -> list[str]:
    """Build the Universal (0x0C) schedule retrieval commands for a controller."""
    if max_programs <= 0:
        return []
    s_end = max(max_run_times - 1, 0)
    commands: list[str] = []
    for p_start in range(0, max_programs, _UNIVERSAL_PROGRAM_CHUNK_SIZE):
        p_end = min(p_start + _UNIVERSAL_PROGRAM_CHUNK_SIZE - 1, max_programs - 1)
        header_blocks: list[tuple[int, list[tuple[int, int]]]] = []
        if p_start == 0:
            header_blocks.extend(
                [
                    (_CDI_RAIN_DELAY, []),
                    (_CDI_GLOBAL_SENSOR_BYPASS, []),
                ]
            )
        header_blocks.extend(
            [
                (_CDI_SEASONAL_ADJUST_BY_PROGRAM, [(p_start, p_end)]),
                (_CDI_PROGRAM_CYCLE_TYPE, [(p_start, p_end)]),
            ]
        )
        commands.extend(
            [
                encode_universal_bunch_get_request(header_blocks),
                encode_universal_bunch_get_request(
                    [
                        (_CDI_PROGRAM_CYCLE_DAYS, [(p_start, p_end)]),
                        (_CDI_PROGRAM_CYCLE_COUNT, [(p_start, p_end)]),
                        (_CDI_PROGRAM_CUSTOM_DAYS, [(p_start, p_end), (0, 6)]),
                    ]
                ),
                encode_universal_bunch_get_request(
                    [
                        (_CDI_START_TIMES, [(p_start, p_end), (0, 0), (0, s_end)]),
                    ]
                ),
            ]
        )
    for program in range(max_programs):
        for station_start in range(0, max_stations, _UNIVERSAL_STATION_CHUNK_SIZE):
            station_end = min(
                station_start + _UNIVERSAL_STATION_CHUNK_SIZE - 1, max_stations - 1
            )
            commands.append(
                encode_universal_bunch_get_request(
                    [
                        (
                            _CDI_RUN_TIMES,
                            [(program, program), (station_start, station_end)],
                        )
                    ]
                )
            )
    return commands


def decode_universal(data: str, cmd_template: dict[str, Any]) -> dict[str, Any]:
    """Decode a Universal (0x8C) CDT transport response."""
    try:
        raw = bytes.fromhex(data)
    except ValueError:
        return {"data": data}
    if len(raw) < 26:
        return {"data": data}
    payload_len = int.from_bytes(raw[21:23], "little")
    if len(raw) < 23 + payload_len:
        return {"data": data}
    payload = raw[23 : 23 + payload_len]
    if payload[:2] != _CDT_BUNCH_GET_RESPONSE:
        return {"data": data}

    num_blocks = payload[2]
    offset = 3
    controller_info: dict[str, int] = {}
    program_info_by_id: dict[int, dict[str, Any]] = {}
    program_start_info: list[dict[str, Any]] = []
    program_durations: list[dict[str, Any]] = []

    for _ in range(num_blocks):
        if offset + 3 > len(payload):
            return {"data": data}
        table_id = int.from_bytes(payload[offset : offset + 2], "little")
        rank = payload[offset + 2]
        offset += 3
        ranges: list[tuple[int, int]] = []
        count = 1
        for _ in range(rank):
            if offset + 4 > len(payload):
                return {"data": data}
            start = int.from_bytes(payload[offset : offset + 2], "little")
            end = int.from_bytes(payload[offset + 2 : offset + 4], "little")
            offset += 4
            if end < start:
                return {"data": data}
            ranges.append((start, end))
            count *= end - start + 1
        if offset >= len(payload):
            return {"data": data}
        elem_size = payload[offset]
        offset += 1
        if elem_size <= 0 or offset + count * elem_size > len(payload):
            return {"data": data}
        values = [
            int.from_bytes(
                payload[offset + i * elem_size : offset + (i + 1) * elem_size],
                "little",
            )
            for i in range(count)
        ]
        offset += count * elem_size

        if table_id == _CDI_RAIN_DELAY and values:
            controller_info["rainDelay"] = values[0]
        elif table_id == _CDI_GLOBAL_SENSOR_BYPASS and values:
            controller_info["rainSensor"] = values[0]
        elif table_id == _CDI_SEASONAL_ADJUST_BY_PROGRAM and rank == 1:
            p_start, _ = ranges[0]
            for i, val in enumerate(values):
                prog = program_info_by_id.setdefault(
                    p_start + i, {"program": p_start + i}
                )
                prog["seasonalAdjust"] = val
        elif table_id == _CDI_PROGRAM_CYCLE_TYPE and rank == 1:
            p_start, _ = ranges[0]
            for i, val in enumerate(values):
                prog = program_info_by_id.setdefault(
                    p_start + i, {"program": p_start + i}
                )
                prog["frequency"] = _UNIVERSAL_FREQUENCY.get(val, ProgramFrequency.OFF)
        elif table_id == _CDI_PROGRAM_CYCLE_DAYS and rank == 1:
            p_start, _ = ranges[0]
            for i, val in enumerate(values):
                prog = program_info_by_id.setdefault(
                    p_start + i, {"program": p_start + i}
                )
                prog["period"] = val
        elif table_id == _CDI_PROGRAM_CYCLE_COUNT and rank == 1:
            p_start, _ = ranges[0]
            for i, val in enumerate(values):
                prog = program_info_by_id.setdefault(
                    p_start + i, {"program": p_start + i}
                )
                prog["synchro"] = val
        elif table_id == _CDI_PROGRAM_CUSTOM_DAYS and rank == 2:
            (p_start, p_end), (d_start, d_end) = ranges
            num_days = d_end - d_start + 1
            for p_idx, p in enumerate(range(p_start, p_end + 1)):
                mask = 0
                for d_idx, d in enumerate(range(d_start, d_end + 1)):
                    if values[p_idx * num_days + d_idx]:
                        mask |= 1 << d
                prog = program_info_by_id.setdefault(p, {"program": p})
                prog["daysOfWeekMask"] = mask
        elif table_id == _CDI_START_TIMES and rank == 3:
            (p_start, p_end), (m_start, m_end), (s_start, s_end) = ranges
            num_m = m_end - m_start + 1
            num_s = s_end - s_start + 1
            stride = num_m * num_s
            for p_idx, p in enumerate(range(p_start, p_end + 1)):
                starts = values[p_idx * stride : p_idx * stride + num_s]
                program_start_info.append({"program": p, "startTime": starts})
        elif table_id == _CDI_RUN_TIMES and rank == 2:
            (p_start, p_end), (z_start, z_end) = ranges
            num_z = z_end - z_start + 1
            for p_idx, p in enumerate(range(p_start, p_end + 1)):
                durations = []
                for z_idx, z in enumerate(range(z_start, z_end + 1)):
                    seconds = values[p_idx * num_z + z_idx]
                    duration = seconds // 60
                    if duration > 0:
                        durations.append({"zone": z + 1, "duration": duration})
                program_durations.append({"program": p, "durations": durations})

    result: dict[str, Any] = {}
    if controller_info:
        result["controllerInfo"] = controller_info
    if program_info_by_id:
        result["programInfo"] = [
            program_info_by_id[p] for p in sorted(program_info_by_id)
        ]
    if program_start_info:
        result["programStartInfo"] = program_start_info
    if program_durations:
        result["programDurations"] = program_durations
    if not result:
        return {"data": data}
    return result


DEFAULT_DECODER = "decode_template"

DECODERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "decode_template": decode_template,
    "decode_schedule": decode_schedule,
    "decode_queue": decode_queue,
    "decode_universal": decode_universal,
}


def decode(data: str) -> dict[str, Any]:
    """Decode a rainbird tunnelSip command response."""
    command_code = data[:2]
    if not (cmd_template := RAINBIRD_COMMANDS_BY_ID.get(command_code)):
        _LOGGER.warning(
            "Unrecognized server response code '%s' from '%s'", command_code, data
        )
        return {"data": data}
    decoder = DECODERS[cmd_template.get(DECODER, DEFAULT_DECODER)]
    return {TYPE: cmd_template[TYPE], **decoder(data, cmd_template)}


def encode(command: str, *args) -> str:
    """Encode a rainbird tunnelSip command request."""
    if not (command_set := RAINBIRD_COMMANDS.get(command)):
        raise RainbirdCodingException(
            f"Command {command} not available. Supported: {RAINBIRD_COMMANDS.keys()}"
        )
    return encode_command(command_set, *args)


def encode_command(command_set: dict[str, Any], *args) -> str:
    """Encode a rainbird tunnelSip command request."""
    cmd_code = command_set["command"]
    if cmd_code == "0C":
        if len(args) != 1 or not isinstance(args[0], str):
            raise RainbirdCodingException(
                f"UniversalMessageRequest expects 1 hex string argument: {args}"
            )
        payload = args[0].upper()
        if payload.startswith("0C"):
            return payload
        inner = bytes.fromhex(payload)
        frame = _UNIVERSAL_REQUEST_HEADER + len(inner).to_bytes(2, "little") + inner
        return frame.hex().upper()
    if not (length := command_set.get(LENGTH)):
        raise RainbirdCodingException(
            f"Unable to encode command missing length: {command_set}"
        )
    if len(args) > length:
        raise RainbirdCodingException(
            f"Too many parameters. {length} expected: {command_set}"
        )

    if length == 1 or "parameter" in command_set or "parameterOne" in command_set:
        # TODO: Replace old style encoding with new encoding below
        params = (cmd_code,) + tuple(int(x) for x in args)
        arg_placeholders = (
            (f"%0{(length - len(args)) * 2}X") if len(args) > 0 else ""
        ) + ("%02X" * (len(args) - 1))
        return (f"%s{arg_placeholders}") % (params)

    data = cmd_code + ("00" * (length - 1))
    args_list = list(args)
    for k, command_arg in command_set.items():
        if k in RESERVED_FIELDS:
            continue
        command_arg_length = command_arg[LENGTH]
        arg = args_list.pop(0)
        if isinstance(arg, str):
            arg = int(arg, 16)
        param_template = f"%0{command_arg_length}X"
        start_ = command_arg[POSITION]
        end_ = start_ + command_arg_length
        param = param_template % arg
        data = f"{data[:start_]}{param}{data[end_:]}"
    return data
