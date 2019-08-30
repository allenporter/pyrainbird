# COMMAND FILE RAINBIRD API
RAIBIRD_COMMANDS = {
    "ControllerCommands":
        {
            "ModelAndVersionRequest": {"command": "02", "response": "82", "length": 1},
            "AvailableStationsRequest": {"command": "03", "parameter": 0, "response": "83", "length": 2},
            "CommandSupportRequest": {"command": "04", "commandToTest": "02", "response": "84", "length": 2},
            "SerialNumberRequest": {"command": "05", "response": "85", "length": 1},
            "CurrentTimeRequest": {"command": "10", "response": "90", "length": 1},
            "CurrentDateRequest": {"command": "12", "response": "92", "length": 1},
            "WaterBudgetRequest": {"command": "30", "parameter": 0, "response": "B0", "length": 2},
            "CurrentRainSensorStateRequest": {"command": "3E", "response": "BE", "length": 1},
            "CurrentStationsActiveRequest": {"command": "3F", "parameter": 0, "response": "BF", "length": 2},
            "ManuallyRunProgramRequest": {"command": "38", "parameter": 0, "response": "01", "length": 2},
            "ManuallyRunStationRequest": {"command": "39", "parameterOne": 0, "parameterTwo": 0, "response": "01",
                                          "length": 4},
            "TestStationsRequest": {"command": "3A", "parameter": 0, "response": "01", "length": 2},
            "StopIrrigationRequest": {"command": "40", "response": "01", "length": 1},
            "RainDelayGetRequest": {"command": "36", "response": "B6", "length": 1},
            "RainDelaySetRequest": {"command": "37", "parameter": 0, "response": "01", "length": 3},
            "AdvanceStationRequest": {"command": "42", "parameter": 0, "response": "01", "length": 2},
            "CurrentIrrigationStateRequest": {"command": "48", "response": "C8", "length": 1},
            "CurrentScheduleRequest": {"command": "20", "parameterOne": 0, "parameterTwo": 0, "response": "A0",
                                       "length": 3}
        },
    "ControllerResponses":
        {
            "00": {"length": 3, "type": "NotAcknowledgeResponse", "commandEcho": {"position": 2, "length": 2},
                   "NAKCode": {"position": 4, "length": 2}},
            "01": {"length": 2, "type": "AcknowledgeResponse", "commandEcho": {"position": 2, "length": 2}},
            "82": {"length": 5, "type": "ModelAndVersionResponse", "modelID": {"position": 2, "length": 4},
                   "protocolRevisionMajor": {"position": 6, "length": 2},
                   "protocolRevisionMinor": {"position": 8, "length": 2}},
            "83": {"length": 6, "type": "AvailableStationsResponse", "pageNumber": {"position": 2, "length": 2},
                   "setStations": {"position": 4, "length": 8}},
            "84": {"length": 3, "type": "CommandSupportResponse", "commandEcho": {"position": 2, "length": 2},
                   "support": {"position": 4, "length": 2}},
            "85": {"length": 9, "type": "SerialNumberResponse", "serialNumber": {"position": 2, "length": 16}},
            "90": {"length": 4, "type": "CurrentTimeResponse", "hour": {"position": 2, "length": 2},
                   "minute": {"position": 4, "length": 2}, "second": {"position": 6, "length": 2}},
            "92": {"length": 4, "type": "CurrentDateResponse", "day": {"position": 2, "length": 2},
                   "month": {"position": 4, "length": 1}, "year": {"position": 5, "length": 3}},
            "B0": {"length": 4, "type": "WaterBudgetResponse", "programCode": {"position": 2, "length": 2},
                   "highByte": {"position": 4, "length": 2}, "lowByte": {"position": 6, "length": 2}},
            "BE": {"length": 2, "type": "CurrentRainSensorStateResponse", "sensorState": {"position": 2, "length": 2}},
            "BF": {"length": 6, "type": "CurrentStationsActiveResponse", "pageNumber": {"position": 2, "length": 2},
                   "activeStations": {"position": 4, "length": 8}},
            "B6": {"length": 3, "type": "RainDelaySettingResponse", "delaySetting": {"position": 2, "length": 4}},
            "C8": {"length": 2, "type": "CurrentIrrigationStateResponse",
                   "irrigationState": {"position": 2, "length": 2}}
        }
}


def decode(data):
    if data[:2] in RAIBIRD_COMMANDS['ControllerResponses']:
        cmd_template = RAIBIRD_COMMANDS['ControllerResponses'][data[:2]]
        result = {'type': cmd_template['type']}
        for k, v in cmd_template.items():
            if isinstance(v, dict) and 'position' in v and 'length' in v:
                result[k] = int(data[v['position']:v['position'] + v['length']], 16)
        return result
    else:
        return {"data": data}


def encode(command, *args):
    request_command = '%sRequest' % command
    command_set = RAIBIRD_COMMANDS["ControllerCommands"][request_command]
    if request_command in RAIBIRD_COMMANDS["ControllerCommands"]:
        cmd_code = command_set["command"]
    else:
        raise Exception('Command %s not available. Existing commands: %s' % (
            request_command, RAIBIRD_COMMANDS["ControllerCommands"]))
    if len(*args) > command_set['length'] - 1:
        raise Exception('Too much parameters. %d expected:\n%s' % (command_set['length'] - 1, command_set))
    params = (cmd_code, *tuple(map(lambda x: int(x), *args)))
    zero_padding = ('00' * (command_set['length'] - len(*args) - 1))
    arg_placeholders = ('%02x' * (len(*args)))
    return ('%s' + zero_padding + arg_placeholders) % (params)
