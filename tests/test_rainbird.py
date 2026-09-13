import unittest

import pytest
from parameterized import parameterized
from pytest_golden.plugin import GoldenTestFixture

from pyrainbird.const import DayOfWeek, ProgramFrequency
from pyrainbird.exceptions import RainbirdCodingException
from pyrainbird.rainbird import decode, encode, encode_zone_schedule
from pyrainbird.resources import LENGTH, RAINBIRD_COMMANDS


def encode_name_func(testcase_func, param_num, param):
    return f"{testcase_func.__name__}_{param_num}_{parameterized.to_safe_name(param.args[1])}"


def decode_name_func(testcase_func, param_num, param):
    return "{}_{}_{}".format(
        testcase_func.__name__,
        param_num,
        parameterized.to_safe_name(param.args[0]["type"]),
    )


@pytest.mark.golden_test("testdata/*.yaml")
def test_decode(golden: GoldenTestFixture) -> None:
    """Fixture to read golden file and compare to golden output."""
    data = golden["data"]
    decoded_data = [decode(case) for case in data]
    assert decoded_data == golden.out["decoded_data"]


@pytest.mark.golden_test("testdata/*.yaml")
def test_encode(golden: GoldenTestFixture) -> None:
    """Test that we can re-encode decoded output to get back the original."""
    data = golden["data"]
    decoded_data = [decode(case) for case in data]

    for entry in decoded_data:
        command = entry["type"]
        del entry["type"]
        expected_data = data.pop(0)
        if LENGTH not in RAINBIRD_COMMANDS[command]:
            continue
        assert encode(command, *entry.values()) == expected_data


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
            ["31FF0096", "WaterBudgetSet", 0xFF, 150],
            [
                "2100010A189090909090027F0300",
                "SetSchedule",
                0,
                1,
                "0A189090909090027F0300",
            ],
        ],
        name_func=encode_name_func,
    )
    def test_encode(self, expected, command, *vargs):
        self.assertEqual(expected, encode(f"{command}Request", *vargs))


def test_encode_zone_schedule() -> None:
    """Test encoding the schedule of a zone of an LCR series device."""
    # 10 minutes, a single start at 04:00, even days
    assert (
        encode_zone_schedule(
            duration=10,
            starts=[4 * 60],
            frequency=ProgramFrequency.EVEN,
            days_of_week_mask=0x7F,
            period=3,
        )
        == "0A189090909090027F0300"
    )
    # 15 minutes, starts at 06:00 and 21:00, cyclic every 3 days
    assert (
        encode_zone_schedule(
            duration=15,
            starts=[6 * 60, 21 * 60],
            frequency=ProgramFrequency.CYCLIC,
            days_of_week_mask=0x7F,
            period=3,
            synchro=1,
        )
        == "0F247E90909090037F0301"
    )
    # A custom schedule on Monday and Thursday
    assert (
        encode_zone_schedule(
            duration=5,
            starts=[8 * 60],
            days_of_week_mask=sum(
                1 << day for day in (DayOfWeek.MONDAY, DayOfWeek.THURSDAY)
            ),
        )
        == "0530909090909000120000"
    )


def test_encode_zone_schedule_round_trip() -> None:
    """Test that an encoded zone schedule decodes back to the same values."""
    body = encode_zone_schedule(
        duration=10,
        starts=[4 * 60],
        frequency=ProgramFrequency.EVEN,
        days_of_week_mask=0x7F,
        period=3,
    )
    decoded = decode(f"A00001{body}")
    assert decoded["zoneInfo"][1] == {
        "zone": 1,
        "duration": 10,
        "startTime": [240],
        "frequency": ProgramFrequency.EVEN,
        "daysOfWeekMask": 0x7F,
        "period": 3,
        "synchro": 0,
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"duration": 0, "starts": [240]}, "Duration"),
        ({"duration": 256, "starts": [240]}, "Duration"),
        ({"duration": 10, "starts": [0, 60, 120, 180, 240, 300, 360]}, "start times"),
        ({"duration": 10, "starts": [245]}, "boundary"),
        ({"duration": 10, "starts": [1440]}, "time of day"),
        ({"duration": 10, "starts": [240], "frequency": 9}, "frequency"),
    ],
)
def test_encode_zone_schedule_invalid(kwargs: dict, message: str) -> None:
    """Test values a zone schedule cannot hold."""
    with pytest.raises(RainbirdCodingException, match=message):
        encode_zone_schedule(**kwargs)
