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
            ["30FF", "WaterBudget", 0xFF],
            ["3000", "WaterBudget", 0],
            ["31FF0096", "WaterBudgetSet", 0xFF, 150],
            ["3900010A", "ManuallyRunStation", 1, 10],
            ["39000106", "ManuallyRunStation", 1, 6],
            ["4B000101", "StackManuallyRunStation", 0, 1, 1],
            [
                "2100010A189090909090027F0300",
                "SetSchedule",
                0,
                1,
                "0A189090909090027F0300",
            ],
            [
                "2100012718909090909000120200",
                "SetSchedule",
                0,
                1,
                "2718909090909000120200",
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
    # Hardware-verified ESP-RZXe Zone 1 write (39 min, 04:00, Custom Mon+Thu, retained period=2)
    assert (
        encode_zone_schedule(
            duration=39,
            starts=[4 * 60],
            frequency=ProgramFrequency.CUSTOM,
            days_of_week_mask=sum(
                1 << day for day in (DayOfWeek.MONDAY, DayOfWeek.THURSDAY)
            ),
            period=2,
            synchro=0,
        )
        == "2718909090909000120200"
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


def test_decode_esp_rzxe_responses() -> None:
    """Test decoding hardware-verified responses from ESP-RZXe (Discussion #611)."""
    # Water budget on ESP-RZXe (program FF = controller-wide)
    assert decode("B0FF0064") == {
        "type": "WaterBudgetResponse",
        "programCode": 0xFF,
        "seasonalAdjust": 100,
    }
    assert decode("B0FF0096") == {
        "type": "WaterBudgetResponse",
        "programCode": 0xFF,
        "seasonalAdjust": 150,
    }

    # NAK 04 (Incompatible Data) when querying program 0 water budget (30 00) on ESP-RZXe
    assert decode("003004") == {
        "type": "NotAcknowledgeResponse",
        "commandEcho": 0x30,
        "NAKCode": 4,
    }

    # NAK 01 (Command Not Supported) for 0x0C, 0x4A, 0x4B, 0x4C on ESP-RZXe
    assert decode("000C01") == {
        "type": "NotAcknowledgeResponse",
        "commandEcho": 0x0C,
        "NAKCode": 1,
    }
    assert decode("004C01") == {
        "type": "NotAcknowledgeResponse",
        "commandEcho": 0x4C,
        "NAKCode": 1,
    }

    # ACK responses for SetSchedule (21), WaterBudgetSet (31), ManuallyRunStation (39),
    # StopIrrigation (40)
    for cmd_hex in ("21", "31", "39", "40"):
        assert decode(f"01{cmd_hex}") == {
            "type": "AcknowledgeResponse",
            "commandEcho": int(cmd_hex, 16),
        }


def test_decode_esp_tm2_responses() -> None:
    """Test decoding hardware-verified responses from ESP-TM2 (Discussion #611)."""
    # Water budget on ESP-TM2 (program 00 = Program A)
    assert decode("B0000064") == {
        "type": "WaterBudgetResponse",
        "programCode": 0,
        "seasonalAdjust": 100,
    }

    # ACK response for StackManuallyRunStation (4B)
    assert decode("014B") == {
        "type": "AcknowledgeResponse",
        "commandEcho": 0x4B,
    }

    # ESP-TM2 24-char CurrentQueueResponse (BB) with 359s (0x0167) remaining on Zone 1
    assert decode("BB0001000167000001000001") == {
        "type": "CurrentQueueResponse",
        "program": {
            "program": 0,
            "zone": 1,
            "seconds": 359,
            "active": True,
        },
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Issue: ESP-RZXe/ST8 global schedule page 0 (20 00 00) returns 4 bytes / 8 hex chars "
        "(A0000000 or A0000080), but decode_schedule checks len(rest) == 4 (expecting 10 hex chars)"
    ),
)
def test_decode_esp_rzxe_schedule_page_0() -> None:
    """Test decoding hardware-verified ESP-RZXe global schedule page 0 (20 00 00 -> A0 00 00 SS)."""
    # Global rain-sensor page 0 responses (A0000000 and A0000080) on physical ESP-RZXe (Discussion #611)
    assert decode("A0000000") == {
        "type": "RetrieveScheduleResponse",
        "controllerInfo": {"rainSensor": 0},
    }
    assert decode("A0000080") == {
        "type": "RetrieveScheduleResponse",
        "controllerInfo": {"rainSensor": 0x80},
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Issue: ESP-RZXe/ST8 20-hex-char CurrentQueueResponse (BB 00 QQ AA 00 00 ZZ TT SSSS) "
        "is not handled by decode_queue, which only checks len(data) == 24 or 14"
    ),
)
def test_decode_esp_rzxe_current_queue_page_0() -> None:
    """Test decoding hardware-verified ESP-RZXe CurrentQueueResponse (3B 00 -> BB 00 ...)."""
    # Zone 1 manual run (10 min): 596 seconds (0x0254) remaining, then 475 seconds (0x01DB)
    assert decode("BB000001000001020254") == {
        "type": "CurrentQueueResponse",
        "program": {
            "program": 0,
            "zone": 1,
            "seconds": 596,
            "active": True,
        },
    }
    assert decode("BB0000010000010201DB") == {
        "type": "CurrentQueueResponse",
        "program": {
            "program": 0,
            "zone": 1,
            "seconds": 475,
            "active": True,
        },
    }


@pytest.mark.xfail(
    strict=True,
    reason="Issue: encode_zone_schedule rejects duration=0, which LCR uses to disable a zone",
)
def test_encode_esp_rzxe_zone_schedule_disabled() -> None:
    """Test encoding an ESP-RZXe zone schedule with duration=0 (disabled zone)."""
    assert (
        encode_zone_schedule(
            duration=0,
            starts=[],
            frequency=ProgramFrequency.CUSTOM,
        )
        == "0090909090909000000000"
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Issue: decode_schedule masks bit 7 (0x80) out of the LCR SS byte "
        "(int(rest[20:22], 16) & 0x7F) instead of exposing the per-zone rain sensor flag"
    ),
)
def test_decode_esp_rzxe_zone_schedule_sensor_flag() -> None:
    """Test decoding ESP-RZXe zone schedule SS byte bit 7 (per-zone rain sensor enable flag)."""
    decoded = decode("A000012818909090909000120280")
    assert decoded["zoneInfo"][1]["rainSensor"] is True


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Issue: CurrentStationErrorRequest (0x3D) / CurrentStationErrorResponse (0xBD) "
        "polled by LNK2 on ESP-TM2 is not defined in sipcommands.yaml"
    ),
)
def test_decode_esp_tm2_station_error() -> None:
    """Test encoding 3D 00 and decoding BD 00 00000000 (CurrentStationError on ESP-TM2)."""
    assert encode("CurrentStationErrorRequest", 0) == "3D00"
    assert decode("BD0000000000") == {
        "type": "CurrentStationErrorResponse",
        "pageNumber": 0,
        "stationErrors": 0,
    }
