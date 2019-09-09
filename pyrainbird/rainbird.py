from pyrainbird.resources import RAIBIRD_COMMANDS


def decode(data):
    if data[:2] in RAIBIRD_COMMANDS["ControllerResponses"]:
        cmd_template = RAIBIRD_COMMANDS["ControllerResponses"][data[:2]]
        result = {"type": cmd_template["type"]}
        for k, v in cmd_template.items():
            if isinstance(v, dict) and "position" in v and "length" in v:
                position_ = v["position"]
                length_ = v["length"]
                result[k] = int(data[position_: position_ + length_], 16)
        return result
    else:
        return {"data": data}


def encode(command, *args):
    request_command = "%sRequest" % command
    command_set = RAIBIRD_COMMANDS["ControllerCommands"][request_command]
    if request_command in RAIBIRD_COMMANDS["ControllerCommands"]:
        cmd_code = command_set["command"]
    else:
        raise Exception(
            "Command %s not available. Existing commands: %s"
            % (request_command, RAIBIRD_COMMANDS["ControllerCommands"])
        )
    if len(args) > command_set["length"] - 1:
        raise Exception(
            "Too much parameters. %d expected:\n%s"
            % (command_set["length"] - 1, command_set)
        )
    params = (cmd_code,) + tuple(map(lambda x: int(x), args))
    arg_placeholders = (("%%0%dX" % ((command_set["length"] - len(args)) * 2))
                        if len(args) > 0
                        else "") + ("%02X" * (len(args) - 1))
    return ("%s" + arg_placeholders) % (params)
