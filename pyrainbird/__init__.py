import logging
import time
from functools import reduce

from . import rainbird
from .rainbird import RAIBIRD_COMMANDS
from .client import RainbirdClient


class RainbirdController:

    def __init__(self, server, password, update_delay=20, retry=3, retry_sleep=10, logger=logging.getLogger(__name__)):
        self.rainbird_client = RainbirdClient(server, password, retry, retry_sleep, logger)
        self.logger = logger
        self.zones = dict()
        self.rain_sensor = None
        self.update_delay = update_delay
        self.zone_update_time = None
        self.sensor_update_time = None

    def zone_state(self, zone):
        if self.zone_update_time is None or time.time() > self.zone_update_time + self.update_delay:
            resp = self._update_irrigation_state()
            if not (resp and resp["type"] == 'CurrentStationsActiveResponse'):
                self.zones.clear()
                return None
        return self.zones[zone]

    def irrigate_zone(self, zone, time):
        response = self._start_irrigation(zone, time)
        self._update_irrigation_state()
        return response is not None and response["type"] == 'CurrentStationsActiveResponse' and self.zones[zone]

    def stop_irrigation(self):
        response = self._stop_irrigation()
        self._update_irrigation_state()
        return response is not None and response["type"] == 'AcknowledgeResponse' and not reduce(lambda x, y: x or y,
                                                                                                 self.zones, False)

    def get_rain_sensor_state(self):
        if self.sensor_update_time is None or time.time() > self.sensor_update_time + self.update_delay:
            response = self._update_rain_sensor_state()
            self.rain_sensor = response['sensorState'] if response is not None and response[
                'type'] == "CurrentRainSensorStateResponse" else None
        return self.rain_sensor

    def get_rain_delay(self):
        response = self._update_current_rain_delay_state()
        return response['delaySetting'] if response is not None and 'delaySetting' in response and response[
            'type'] == "RainDelaySettingResponse" else None

    def set_rain_delay(self, days):
        response = self._set_rain_delay_state(days)
        return response is not None and response['type'] == "AcknowledgeResponse"

    def _stop_irrigation(self):
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

    def _start_irrigation(self, zone, minutes):
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

    def _update_irrigation_state(self):
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
                    self.zones[i + 1] = active
                    if active:
                        resp['active'].append(i + 1)
                resp['zones'] = self.zones
                self.zone_update_time = time.time()
            else:
                self.logger.warning("Status request NOT acknowledged")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def _update_rain_sensor_state(self):
        self.logger.debug("Requesting current Rain Sensor State")
        resp = self.command("CurrentRainSensorState")
        if resp:
            if resp['type'] == "CurrentRainSensorStateResponse":
                self.logger.debug(
                    "Current rainsensor state: %s" % (resp['sensorState']))
            else:
                self.logger.warning("Status request failed with wrong response")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def _update_current_rain_delay_state(self):
        self.logger.debug("Requesting current Rain Dealy State")
        resp = self.command("RainDelayGet")
        if resp:
            if resp['type'] == "RainDelaySettingResponse":
                self.logger.debug(
                    "Current rain delay state: %s" % (resp['delaySetting']))
            else:
                self.logger.warning("Status request failed with wrong response")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def _set_rain_delay_state(self, days):
        self.logger.debug("SettingRain DealyState")
        resp = self.command("RainDelaySet", days)
        if resp:
            if resp['type'] == "AcknowledgeResponse":
                self.logger.debug(
                    "Current rain delay state: %s" % (resp['delaySetting']))
            else:
                self.logger.warning("Status request failed with wrong response")
        else:
            self.logger.warning("Request resulted in no response")
        return resp

    def command(self, command, *args):
        data = rainbird.encode(command, args)
        self.logger.debug("Request to line: " + str(data))
        decrypted_data = self.rainbird_client.request(
            data, RAIBIRD_COMMANDS["ControllerCommands"]["%sRequest" % command]["length"])
        self.logger.debug("Response from line: " + str(decrypted_data))
        if decrypted_data is None:
            self.logger.warn("Empty response from controller")
            return None
        decoded = rainbird.decode(decrypted_data)
        if decrypted_data[:2] != RAIBIRD_COMMANDS["ControllerCommands"]['%sRequest' % command]["response"]:
            raise Exception('Status request failed with wrong response! Requested %s but got %s:\n%s' %
                            (RAIBIRD_COMMANDS["ControllerCommands"]['%sRequest' % command]["response"],
                             decrypted_data[:2], decoded))
        self.logger.debug('Response: %s' % decoded)
        return decoded
