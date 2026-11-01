import unittest

import pytest
from parameterized import parameterized
from pytest_golden.plugin import GoldenTestFixture

from pyrainbird.const import DayOfWeek, ProgramFrequency
from pyrainbird.exceptions import RainbirdCodingException
from pyrainbird.rainbird import (
    decode,
    encode,
    encode_universal_schedule_commands,
    encode_zone_schedule,
)
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


def test_encode_universal_schedule_commands() -> None:
    """Test generating Universal (0x0C) schedule commands for ESP-ME3 and ARC8/RC2."""
    me3_cmds = encode_universal_schedule_commands(
        max_programs=4, max_run_times=6, max_stations=22
    )
    assert me3_cmds == [
        "0C200001000805000000000C0000000000050000001700070B041400000D00001800010000030013000100000300",
        "0C200001000805000000000C0000000000050000001C00070B0312000100000300110001000003001000020000030000000600",
        "0C200001000805000000000C0000000000050000001200070B011D0003000003000000000000000500",
        "0C200001000805000000000C0000000000050000000E00070B011500020000000000001500",
        "0C200001000805000000000C0000000000050000000E00070B011500020100010000001500",
        "0C200001000805000000000C0000000000050000000E00070B011500020200020000001500",
        "0C200001000805000000000C0000000000050000000E00070B011500020300030000001500",
    ]

    isk_cmds = encode_universal_schedule_commands(
        max_programs=3, max_run_times=4, max_stations=8
    )
    assert isk_cmds == [
        "0C200001000805000000000C0000000000050000001700070B041400000D00001800010000020013000100000200",
        "0C200001000805000000000C0000000000050000001C00070B0312000100000200110001000002001000020000020000000600",
        "0C200001000805000000000C0000000000050000001200070B011D0003000002000000000000000300",
        "0C200001000805000000000C0000000000050000000E00070B011500020000000000000700",
        "0C200001000805000000000C0000000000050000000E00070B011500020100010000000700",
        "0C200001000805000000000C0000000000050000000E00070B011500020200020000000700",
    ]
    assert encode_universal_schedule_commands(0, 4, 8) == []


def test_encode_universal_schedule_commands_lx_chunking() -> None:
    """Test 5-program metadata chunking and 25-station runtime chunking for LX controllers."""
    # LX-IVM: 10 programs (2 slices: 0..4, 5..9), 8 start times (0..7), 60 stations (3 chunks: 0..24, 25..49, 50..59)
    ivm_cmds = encode_universal_schedule_commands(
        max_programs=10, max_run_times=8, max_stations=60
    )
    assert len(ivm_cmds) == 2 * 3 + 10 * 3
    assert ivm_cmds[:6] == [
        # Slice 0..4 (includes global 0x14 rain delay and 0x0D sensor bypass)
        "0C200001000805000000000C0000000000050000001700070B041400000D00001800010000040013000100000400",
        "0C200001000805000000000C0000000000050000001C00070B0312000100000400110001000004001000020000040000000600",
        "0C200001000805000000000C0000000000050000001200070B011D0003000004000000000000000700",
        # Slice 5..9 (program-scoped blocks only)
        "0C200001000805000000000C0000000000050000001100070B021800010500090013000105000900",
        "0C200001000805000000000C0000000000050000001C00070B0312000105000900110001050009001000020500090000000600",
        "0C200001000805000000000C0000000000050000001200070B011D0003050009000000000000000700",
    ]
    assert all(len(bytes.fromhex(cmd)) <= 255 for cmd in ivm_cmds)

    # LXME2: 40 programs (8 slices of 5), 10 start times (0..9), 48 stations (2 chunks: 0..24, 25..47)
    lxme2_cmds = encode_universal_schedule_commands(
        max_programs=40, max_run_times=10, max_stations=48
    )
    assert len(lxme2_cmds) == 8 * 3 + 40 * 2
    assert lxme2_cmds[21:24] == [
        # Final metadata slice 35..39 (0x23..0x27)
        "0C200001000805000000000C0000000000050000001100070B021800012300270013000123002700",
        "0C200001000805000000000C0000000000050000001C00070B0312000123002700110001230027001000022300270000000600",
        "0C200001000805000000000C0000000000050000001200070B011D0003230027000000000000000900",
    ]
    assert all(len(bytes.fromhex(cmd)) <= 255 for cmd in lxme2_cmds)


def test_decode_universal() -> None:
    """Test decoding Universal (0x8C) schedule responses."""
    # Sensor, rain delay, seasonal adjust, and frequency
    decoded_sensor = decode(
        "8C200000000C00000000000805000000000500FFFF2900080B0414000001000D0000010018000100000300022D00320028003500130001000003000104040400"
    )
    assert decoded_sensor == {
        "type": "UniversalMessageTransportResponse",
        "controllerInfo": {"rainDelay": 0, "rainSensor": 0},
        "programInfo": [
            {"program": 0, "seasonalAdjust": 45, "frequency": ProgramFrequency.CYCLIC},
            {"program": 1, "seasonalAdjust": 50, "frequency": ProgramFrequency.CYCLIC},
            {"program": 2, "seasonalAdjust": 40, "frequency": ProgramFrequency.CYCLIC},
            {"program": 3, "seasonalAdjust": 53, "frequency": ProgramFrequency.CUSTOM},
        ],
    }

    # Cycle days, cycle count, and custom days of week
    decoded_days = decode(
        "8C200000000C00000000000805000000000500FFFF4300080B0312000100000300010404030311000100000300010100000210000200000300000006000100000000000000010101010101010000000000000001010101010101"
    )
    assert decoded_days == {
        "type": "UniversalMessageTransportResponse",
        "programInfo": [
            {"program": 0, "period": 4, "synchro": 1, "daysOfWeekMask": 0},
            {"program": 1, "period": 4, "synchro": 0, "daysOfWeekMask": 0x7F},
            {"program": 2, "period": 3, "synchro": 0, "daysOfWeekMask": 0},
            {"program": 3, "period": 3, "synchro": 2, "daysOfWeekMask": 0x7F},
        ],
    }

    # Start times
    decoded_starts = decode(
        "8C200000000C00000000000805000000000500FFFF4300080B011D0003000003000000000000000500022C01A005A005A005A005A005B400A005A005A005A005A0056801A005A005A005A005A005A005A005A005A005A005A005"
    )
    assert decoded_starts == {
        "type": "UniversalMessageTransportResponse",
        "programStartInfo": [
            {"program": 0, "startTime": [300, 1440, 1440, 1440, 1440, 1440]},
            {"program": 1, "startTime": [180, 1440, 1440, 1440, 1440, 1440]},
            {"program": 2, "startTime": [360, 1440, 1440, 1440, 1440, 1440]},
            {"program": 3, "startTime": [1440, 1440, 1440, 1440, 1440, 1440]},
        ],
    }

    # Program A runtimes
    decoded_runtimes = decode(
        "8C200000000C00000000000805000000000500FFFF6700080B0115000200000000000015000400000000100E000018150000201C000000000000302A000018150000282300000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"
    )
    assert decoded_runtimes == {
        "type": "UniversalMessageTransportResponse",
        "programDurations": [
            {
                "program": 0,
                "durations": [
                    {"zone": 2, "duration": 60},
                    {"zone": 3, "duration": 90},
                    {"zone": 4, "duration": 120},
                    {"zone": 6, "duration": 180},
                    {"zone": 7, "duration": 90},
                    {"zone": 8, "duration": 150},
                ],
            }
        ],
    }


@pytest.mark.parametrize(
    ("raw_code", "expected_frequency"),
    [
        (0, ProgramFrequency.CUSTOM),
        (1, ProgramFrequency.ODD),
        (2, ProgramFrequency.ODD),
        (3, ProgramFrequency.EVEN),
        (4, ProgramFrequency.CYCLIC),
        (5, ProgramFrequency.OFF),
        (99, ProgramFrequency.OFF),
    ],
)
def test_decode_universal_frequency_codes(
    raw_code: int, expected_frequency: ProgramFrequency
) -> None:
    """Test Universal CDT table 0x13 water cycle codes decode to ProgramFrequency."""
    # Single-block 080B response for table 1300 rank 1 [0..0] width 1
    payload = bytes.fromhex("080B011300010000000001") + bytes([raw_code])
    frame = (
        bytes.fromhex("8C200000000C00000000000805000000000500FFFF")
        + len(payload).to_bytes(2, "little")
        + payload
    )
    decoded = decode(frame.hex().upper())
    assert decoded == {
        "type": "UniversalMessageTransportResponse",
        "programInfo": [{"program": 0, "frequency": expected_frequency}],
    }


@pytest.mark.parametrize(
    ("raw_code", "expected_frequency"),
    [
        (0, ProgramFrequency.CUSTOM),
        (1, ProgramFrequency.CYCLIC),
        (2, ProgramFrequency.ODD),
        (3, ProgramFrequency.EVEN),
        (4, ProgramFrequency.OFF),
        (5, ProgramFrequency.ODD),
        (99, ProgramFrequency.OFF),
    ],
)
def test_decode_schedule_program_frequency_codes(
    raw_code: int, expected_frequency: ProgramFrequency
) -> None:
    """Test program-based SIP 0xA0 subpage 0x10 frequency codes decode cleanly."""
    decoded = decode(f"A000107F03010064{raw_code:02X}")
    assert decoded["programInfo"]["frequency"] == expected_frequency
