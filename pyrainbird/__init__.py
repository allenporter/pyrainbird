import logging

from . import rainbird
from .rainbird import RAIBIRD_COMMANDS
from .client import RainbirdClient


class RainbirdController:

    def __init__(self, server, password, retry=3, retry_sleep=10, logger=logging.getLogger(__name__)):
        self.rainbirdClient = RainbirdClient(server, password, retry, retry_sleep, logger)
        self.logger = logger

    def stopIrrigation(self):
        self.logger.debug("Irrigation stop requested")
        resp = self.command("StopIrrigation")
        if resp:
            if resp["type"] == 'AcknowledgeResponse':
                self.logger.debug("Irrigation stop request acknowledged")
            else:
                self.logger.warning("Irrigation stop request NOT acknowledged")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def startIrrigation(self, zone, minutes):
        self.logger.debug("Irrigation start requested for zone " +
                          str(zone) + " for duration " + str(minutes))
        resp = self.command("ManuallyRunStation", zone, minutes)
        if resp:
            if resp["type"] == 'AcknowledgeResponse':
                self.logger.debug("Irrigation request acknowledged")
            else:
                self.logger.warning("Irrigation request NOT acknowledged")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def currentIrrigation(self):
        self.logger.debug("Requesting current Irrigation station")
        resp = self.command("CurrentStationsActive")
        if resp:
            if resp["type"] == 'CurrentStationsActiveResponse':
                resp['sprinklers'] = dict()
                self.logger.debug("Status request acknowledged")
                resp['active'] = list()
                for i in range(0, 8):
                    mask = 1 << ((6 * 4) + i)
                    self.logger.debug('%08x X %08x' % (resp['activeStations'], mask))
                    active = bool(resp['activeStations'] & mask)
                    resp['sprinklers'][i + 1] = active
                    if active:
                        resp['active'].append(i + 1)
            else:
                self.logger.warning("Status request NOT acknowledged")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def currentRainSensorState(self):
        self.logger.debug("Requesting current Rain Sensor State")
        resp = self.command("CurrentRainSensorState")
        if resp:
            if resp['type'] == "CurrentRainSensorStateResponse":
                self.logger.debug(
                    "Current rainsensor state: %s" % (resp['sensorState']))
            else:
                self.logger.warning("Status request failed with wrong respone")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def command(self, command, *args):
        data = rainbird.encode(command, args)
        self.logger.debug("Request to line: " + str(data))
        decrypteddata = self.rainbirdClient.request(
            data, RAIBIRD_COMMANDS["ControllerCommands"]["%sRequest" % command]["length"])
        self.logger.debug("Response from line: " + str(decrypteddata))
        if decrypteddata is None:
            self.logger.warn("Empty response from controller")
            return None
        decoded = rainbird.decode(decrypteddata)
        if decrypteddata[:2] != RAIBIRD_COMMANDS["ControllerCommands"]['%sRequest' % command]["response"]:
            raise Exception('Status request failed with wrong respone! Requested %s but got %s:\n%s' %
                            (RAIBIRD_COMMANDS["ControllerCommands"]['%sRequest' % command]["response"],
                             decrypteddata[:2], decoded))
        self.logger.debug('Response: %s' % decoded)
        return decoded
