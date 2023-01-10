import unittest

import pytest
from parameterized import parameterized
from pytest_golden.plugin import GoldenTestFixture

from pyrainbird import rainbird
from pyrainbird.rainbird import decode, encode


def encode_name_func(testcase_func, param_num, param):
    return "%s_%s_%s" % (
        testcase_func.__name__,
        param_num,
        parameterized.to_safe_name(param.args[1]),
    )


def decode_name_func(testcase_func, param_num, param):
    return "%s_%s_%s" % (
        testcase_func.__name__,
        param_num,
        parameterized.to_safe_name(param.args[0]["type"]),
    )


@pytest.mark.golden_test("testdata/*.yaml")
def test_decode(golden: GoldenTestFixture) -> None:
    """Fixture to read golden file and compare to golden output."""
    data = golden["data"]
    decoded_data = [rainbird.decode(case) for case in data]
    assert decoded_data == golden.out["decoded_data"]


class TestSequence(unittest.TestCase):
    @parameterized.expand(
        [
            ["02", "ModelAndVersion"],
            ["030C", "AvailableStations", 12],
            ["040B", "CommandSupport", 11],
            ["05", "SerialNumber"],
            ["10", "CurrentTime"],
            ["12", "CurrentDate"],
            ["300D", "WaterBudget", 13],
            ["3E", "CurrentRainSensorState"],
            ["3F10", "CurrentStationsActive", 16],
            ["3811", "ManuallyRunProgram", 17],
            ["39000612", "ManuallyRunStation", 6, 18],
            ["3A17", "TestStations", 23],
            ["40", "StopIrrigation"],
            ["36", "RainDelayGet"],
            ["37000F", "RainDelaySet", 15],
            ["4208", "AdvanceStation", 8],
            ["48", "CurrentIrrigationState"],
        ],
        name_func=encode_name_func,
    )
    def test_encode(self, expected, command, *vargs):
        self.assertEqual(expected, encode(f"{command}Request", *vargs))
