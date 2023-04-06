"""Resources related to rainbird devices."""

import pkgutil
from typing import Any

import yaml


COMMAND = "command"
TYPE = "type"
LENGTH = "length"
RESPONSE = "response"
POSITION = "position"
DECODER = "decoder"
# Fields in the command template that should not be encoded
RESERVED_FIELDS = [COMMAND, TYPE, LENGTH, RESPONSE, DECODER]

SIP_COMMANDS = yaml.load(
    pkgutil.get_data(__name__, "sipcommands.yaml"), Loader=yaml.FullLoader
)
MODEL_INFO = yaml.load(
    pkgutil.get_data(__name__, "models.yaml"), Loader=yaml.FullLoader
)

RAINBIRD_MODELS = {info["device_id"]: info for info in MODEL_INFO}


def build_id_map(commands: dict[str, Any]) -> dict[str, Any]:
    """Build an ID based map for the specified command struct."""
    return {
        content[COMMAND]: {
            **content,
            TYPE: key,
        }
        for key, content in commands.items()
    }


CONTROLLER_COMMANDS = "ControllerCommands"
CONTROLLER_RESPONSES = "ControllerResponses"

RAINBIRD_COMMANDS = {
    **SIP_COMMANDS[CONTROLLER_COMMANDS],
    **SIP_COMMANDS[CONTROLLER_RESPONSES],
}
RAINBIRD_COMMANDS_BY_ID = {
    **build_id_map(SIP_COMMANDS[CONTROLLER_COMMANDS]),
    **build_id_map(SIP_COMMANDS[CONTROLLER_RESPONSES]),
}
