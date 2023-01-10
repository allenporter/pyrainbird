"""Library for encoding and decoding rainbird tunnelSip commands."""

from collections.abc import Callable
from typing import Any

from .resources import RAINBIRD_COMMANDS


def decode_template(data: str, cmd_template: dict[str, Any]) -> dict[str, int]:
    """Decode the command from the template in yaml."""
    result = {}
    for k, v in cmd_template.items():
        if isinstance(v, dict) and "position" in v and "length" in v:
            position_ = v["position"]
            length_ = v["length"]
            result[k] = int(data[position_ : position_ + length_], 16)
    return result


def decode_schedule(data: str, cmd_template: dict[str, Any]) -> dict[str, Any]:
    """Decode a schedule command."""
    subcommand = int(data[4:6], 16)
    rest = data[6:]
    if subcommand == 0:
        # Delay, Snooze, Rainsensor
        return {
            "stationDelay": int(rest[0:4]),
            "snooze": int(rest[4:6]),
            "rainSensor": int(rest[6:8]),
        }

    if subcommand & 16 == 16:
        program = subcommand & ~16
        fields = list(int(rest[i : i + 2], 16) for i in range(0, len(rest), 2))
        return {
            "program": program,
            "daysOfWeekMask": fields[0],
            "period": fields[1],
            "synchro": fields[2],
            "permanentDaysOff": fields[3],
            "reserved": fields[4],
            "frequency": fields[5],
        }

    if subcommand & 96 == 96:
        program = subcommand & ~96
        # Note: 65535 is disabled
        entries = list(int(rest[i : i + 4], 16) for i in range(0, len(rest), 4))
        return {"program": program, "startTime": entries}

    if subcommand & 128 == 128:
        station = subcommand & ~128
        numPrograms = 3
        rest = bytes(data[6:], "utf-8")
        durations = list(int(rest[i : i + 4], 16) for i in range(0, len(rest), 4))
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


DEFAULT_DECODER = "decode_template"

DECODERS: dict[str, Callable[[str, dict[str, Any]], dict[str, Any]]] = {
    "decode_template": decode_template,
    "decode_schedule": decode_schedule,
}


def decode(data: str) -> dict[str, Any]:
    """Decode a rainbird tunnelSip command response."""
    command_code = data[:2]
    if command_code not in RAINBIRD_COMMANDS["ControllerResponses"]:
        return {"data": data}
    cmd_template = RAINBIRD_COMMANDS["ControllerResponses"][command_code]
    decoder = DECODERS[cmd_template.get("decoder", DEFAULT_DECODER)]
    return {"type": cmd_template["type"], **decoder(data, cmd_template)}


def encode(command: str, *args) -> str:
    """Encode a rainbird tunnelSip command request."""
    request_command = "%sRequest" % command
    command_set = RAINBIRD_COMMANDS["ControllerCommands"][request_command]
    if request_command in RAINBIRD_COMMANDS["ControllerCommands"]:
        cmd_code = command_set["command"]
    else:
        raise Exception(
            "Command %s not available. Existing commands: %s"
            % (request_command, RAINBIRD_COMMANDS["ControllerCommands"])
        )
    if len(args) > command_set["length"] - 1:
        raise Exception(
            "Too much parameters. %d expected:\n%s"
            % (command_set["length"] - 1, command_set)
        )
    params = (cmd_code,) + tuple(map(lambda x: int(x), args))
    arg_placeholders = (
        ("%%0%dX" % ((command_set["length"] - len(args)) * 2)) if len(args) > 0 else ""
    ) + ("%02X" * (len(args) - 1))
    return ("%s" + arg_placeholders) % (params)
