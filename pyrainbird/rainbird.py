"""Library for encoding and decoding rainbird tunnelSip commands."""

import logging
from collections.abc import Callable
from typing import Any

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
    rest = data[6:]
    if subcommand == 0:
        # Delay, Snooze, Rainsensor
        return {
            "controllerInfo": {
                "stationDelay": int(rest[0:4]),
                "rainDelay": int(rest[4:6]),
                "rainSensor": int(rest[6:8]),
            }
        }

    if subcommand & 16 == 16:
        program = subcommand & ~16
        fields = list(int(rest[i : i + 2], 16) for i in range(0, len(rest), 2))
        return {
            "programInfo": {
                "program": program,
                "daysOfWeekMask": fields[0],
                "period": fields[1],
                "synchro": fields[2],
                "permanentDaysOff": fields[3],
                "reserved": fields[4],
                "frequency": fields[5],
            }
        }

    if subcommand & 96 == 96:
        program = subcommand & ~96
        # Note: 65535 is disabled
        entries = list(int(rest[i : i + 4], 16) for i in range(0, len(rest), 4))
        return {
            "programStartInfo": {
                "program": program,
                "startTime": entries,
            }
        }

    if subcommand & 128 == 128:
        station = subcommand & ~128
        rest = bytes(data[6:], "utf-8")
        durations = list(int(rest[i : i + 4], 16) for i in range(0, len(rest), 4))
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

    return {"data": data}


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
            for i in range(0, 11):
                base = i * 6
                zone = int(data[base + 4 : base + 6], 16) & 31
                runtime = int(data[base + 6 : base + 10], 16)
                if zone:
                    queue.append({"zone": zone, "seconds": runtime})
        else:  # ME3
            for i in range(0, 8):
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
        for i in range(0, 8):
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


DEFAULT_DECODER = "decode_template"

DECODERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "decode_template": decode_template,
    "decode_schedule": decode_schedule,
    "decode_queue": decode_queue,
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
        params = (cmd_code,) + tuple(map(lambda x: int(x), args))
        arg_placeholders = (
            ("%%0%dX" % ((length - len(args)) * 2)) if len(args) > 0 else ""
        ) + ("%02X" * (len(args) - 1))
        return ("%s" + arg_placeholders) % (params)

    data = cmd_code + ("00" * (length - 1))
    args_list = list(args)
    for k in command_set:
        if k in RESERVED_FIELDS:
            continue
        command_arg = command_set[k]
        command_arg_length = command_arg[LENGTH]
        arg = args_list.pop(0)
        if isinstance(arg, str):
            arg = int(arg, 16)
        param_template = "%%0%dX" % (command_arg_length)
        start_ = command_arg[POSITION]
        end_ = start_ + command_arg_length
        data = "%s%s%s" % (
            data[:start_],
            # TODO: Replace with kwargs
            (param_template % arg),
            data[end_:],
        )
    return data
