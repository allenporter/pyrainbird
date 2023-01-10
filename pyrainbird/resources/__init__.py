import yaml
from pkg_resources import resource_stream

_SIP_COMMANDS = yaml.load(
    resource_stream("pyrainbird.resources", "sipcommands.yaml"), Loader=yaml.FullLoader
)
RAINBIRD_MODELS = yaml.load(
    resource_stream("pyrainbird.resources", "models.yaml"), Loader=yaml.FullLoader
)

# Fields in the template that should not be encoded
RESERVED_FIELDS = [ "command", "type", "length" ]

RAINBIRD_COMMANDS = { **_SIP_COMMANDS['ControllerCommands'] }
RAINBIRD_COMMANDS_BY_ID = {
    request["command"]: {
        **request,
        "type": request_key,
    }
    for request_key, request in _SIP_COMMANDS['ControllerCommands'].items()
}
RAINBIRD_RESPONSES = { **_SIP_COMMANDS['ControllerResponses'] }
RAINBIRD_RESPONSES_BY_ID = {
    response["command"]: {
        **response,
        "type": response_key,
    }
    for response_key, response in _SIP_COMMANDS['ControllerResponses'].items()
}
