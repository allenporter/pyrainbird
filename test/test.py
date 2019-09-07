import unittest

import responses

from pyrainbird import RainbirdController, RAIBIRD_COMMANDS
from pyrainbird.encryption import encrypt

MOCKED_RAINBIRD_URL = "rainbird.local"
MOCKED_PASSWORD = "test123"


class TestCase(unittest.TestCase):

    @responses.activate
    def testGetRainDelay(self):
        mock_response('B6', delaySetting=86400)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(86400, rainbird.get_rain_delay())

    @responses.activate
    def testSetRainDelay(self):
        mock_response('01', pageNumber=0, commandEcho=6)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.set_rain_delay(3))

    @responses.activate
    def testIrrigateZone(self):
        mock_response('01', pageNumber=0, commandEcho=6)
        mock_response('BF', pageNumber=0, activeStations=0b00010000000000000000000000000000)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.irrigate_zone(5, 30))

    @responses.activate
    def testStopIrrigation(self):
        mock_response('01', pageNumber=0, commandEcho=6)
        mock_response('BF', pageNumber=0, activeStations=0b00000000000000000000000000000000)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.stop_irrigation())

    @responses.activate
    def testGetRainSensor(self):
        mock_response('BE', sensorState=1)
        mock_response('BE', sensorState=0)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(1, rainbird.get_rain_sensor_state())
        self.assertEqual(0, rainbird.get_rain_sensor_state())

    @responses.activate
    def testNotAcknowledgeResponse(self):
        with self.assertRaises(Exception):
            mock_response('00', commandEcho=17, NAKCode=28)
            rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
            self.assertEqual(False, rainbird.irrigate_zone(1, 30))


def mock_response(command, **kvargs):
    resp = RAIBIRD_COMMANDS['ControllerResponses'][command]
    data = command
    for k in resp:
        if k in ["type", "length"]:
            continue
        param_template = '%%0%dX' % (resp[k]['length'] * 2)
        data += param_template % kvargs[k]

    responses.add(
        responses.POST,
        'http://%s/stick' % MOCKED_RAINBIRD_URL,
        body=encrypt((u'{"jsonrpc": "2.0", "result": {"data":"%s"}, "id": 1} ' % data), MOCKED_PASSWORD),
        content_type='application/octet-stream'
    )
