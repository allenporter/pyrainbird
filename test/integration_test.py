import datetime
import unittest

import responses

from pyrainbird import (
    RainbirdController,
    RAIBIRD_COMMANDS,
    ModelAndVersion,
    AvailableStations,
    CommandSupport,
    WaterBudget,
)
from pyrainbird.encryption import encrypt

MOCKED_RAINBIRD_URL = "rainbird.local"
MOCKED_PASSWORD = "test123"


class TestCase(unittest.TestCase):
    @responses.activate
    def test_get_model_and_version(self):
        mock_response(
            "82", modelID=16, protocolRevisionMajor=1, protocolRevisionMinor=3
        )
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(
            ModelAndVersion(16, 1, 3), rainbird.get_model_and_version()
        )

    @responses.activate
    def test_get_available_stations(self):
        mock_response("83", pageNumber=1, setStations=0x7F000000)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(
            AvailableStations("7f000000", 1), rainbird.get_available_stations()
        )

    @responses.activate
    def test_get_command_support(self):
        mock_response("84", commandEcho=6, support=1)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(
            CommandSupport(1, 6), rainbird.get_command_support(0x85)
        )

    @responses.activate
    def test_get_serial_number(self):
        mock_response("85", serialNumber=0x12635436566)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(0x12635436566, rainbird.get_serial_number())

    @responses.activate
    def test_get_current_time(self):
        time = datetime.time()
        mock_response(
            "90", hour=time.hour, minute=time.minute, second=time.second
        )
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(time, rainbird.get_current_time())

    @responses.activate
    def test_get_current_date(self):
        date = datetime.date.today()
        mock_response("92", year=date.year, month=date.month, day=date.day)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(date, rainbird.get_current_date())

    @responses.activate
    def test_get_water_budget(self):
        mock_response("B0", programCode=1, seasonalAdjust=65)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(WaterBudget(1, 65), rainbird.water_budget(5))

    def test_get_rain_sensor(self):
        self._assert_rain_sensor(1, True)
        self._assert_rain_sensor(0, False)

    def test_get_zone_state(self):
        for i in range(1, 9):
            for j in range(1, 9):
                self._assert_zone_state(i, j)

    @responses.activate
    def test_set_program(self):
        mock_response("01", commandEcho=5)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.set_program(5))

    @responses.activate
    def test_irrigate_zone(self):
        mock_response("01", pageNumber=0, commandEcho=6)
        mock_response(
            "BF", pageNumber=0, activeStations=0b10000000000000000000000000000
        )
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.irrigate_zone(5, 30))

    @responses.activate
    def test_test_zone(self):
        mock_response("01", commandEcho=6)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.test_zone(6))

    @responses.activate
    def test_stop_irrigation(self):
        mock_response("01", pageNumber=0, commandEcho=6)
        mock_response("BF", pageNumber=0, activeStations=0b0)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.stop_irrigation())

    @responses.activate
    def test_get_rain_delay(self):
        mock_response("B6", delaySetting=16)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(16, rainbird.get_rain_delay())

    @responses.activate
    def test_set_rain_delay(self):
        mock_response("01", pageNumber=0, commandEcho=6)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.set_rain_delay(3))

    @responses.activate
    def test_advance_zone(self):
        mock_response("01", commandEcho=3)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(True, rainbird.advance_zone(3))

    def test_get_current_irrigation(self):
        self._assert_get_current_irrigation(1, True)
        self._assert_get_current_irrigation(0, False)

    @responses.activate
    def _assert_get_current_irrigation(self, state, expected):
        mock_response("C8", irrigationState=state)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(expected, rainbird.get_current_irrigation())

    @responses.activate
    def test_not_acknowledge_response(self):
        with self.assertRaises(Exception):
            mock_response("00", commandEcho=17, NAKCode=28)
            rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
            self.assertEqual(False, rainbird.irrigate_zone(1, 30))

    @responses.activate
    def _assert_rain_sensor(self, state, expected):
        mock_response("BE", sensorState=state)
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        self.assertEqual(expected, rainbird.get_rain_sensor_state())

    @responses.activate
    def _assert_zone_state(self, i, j):
        rainbird = RainbirdController(MOCKED_RAINBIRD_URL, MOCKED_PASSWORD)
        mask_ = (1 << (i - 1)) * 0x1000000
        mock_response("BF", pageNumber=0, activeStations=mask_)
        self.assertEqual(i == j, rainbird.get_zone_state(j))


def mock_response(command, **kvargs):
    resp = RAIBIRD_COMMANDS["ControllerResponses"][command]
    data = command + ("00" * (resp["length"] - 1))
    for k in resp:
        if k in ["type", "length"]:
            continue
        param_template = "%%0%dX" % (resp[k]["length"])
        start_ = resp[k]["position"]
        end_ = start_ + resp[k]["length"]
        data = "%s%s%s" % (
            data[:start_],
            (param_template % kvargs[k]),
            data[end_:],
        )

    responses.add(
        responses.POST,
        "http://%s/stick" % MOCKED_RAINBIRD_URL,
        body=encrypt(
            (u'{"jsonrpc": "2.0", "result": {"data":"%s"}, "id": 1} ' % data),
            MOCKED_PASSWORD,
        ),
        content_type="application/octet-stream",
    )
