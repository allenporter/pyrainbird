"""Resources related to rainbird devices."""

from typing import Any

import yaml
from pkg_resources import resource_stream

COMMAND = "command"
TYPE = "type"
LENGTH = "length"
RESPONSE = "response"
POSITION = "position"
DECODER = "decoder"
# Fields in the command template that should not be encoded
RESERVED_FIELDS = [COMMAND, TYPE, LENGTH, RESPONSE, DECODER]

SIP_COMMANDS = yaml.load(
    resource_stream("pyrainbird.resources", "sipcommands.yaml"), Loader=yaml.FullLoader
)
MODEL_INFO = yaml.load(
    resource_stream("pyrainbird.resources", "models.yaml"), Loader=yaml.FullLoader
)

RAINBIRD_MODELS = { info["device_id"]: info for info in MODEL_INFO }


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
