import unittest
from typing import Any

import pytest
from parameterized import parameterized

from pyrainbird.data import ModelAndVersion, States


def encode_name_func(testcase_func, param_num, param):
    return f"{testcase_func.__name__}_{param_num}_{parameterized.to_safe_name(param.args[0])}"


class TestSequence(unittest.TestCase):
    @parameterized.expand(
        [
            ("01", (False,) * 0 + (True,) + (False,) * 7),
            ("02", (False,) * 1 + (True,) + (False,) * 6),
            ("04", (False,) * 2 + (True,) + (False,) * 5),
            ("08", (False,) * 3 + (True,) + (False,) * 4),
            ("10", (False,) * 4 + (True,) + (False,) * 3),
            ("20", (False,) * 5 + (True,) + (False,) * 2),
            ("40", (False,) * 6 + (True,) + (False,) * 1),
            ("80", (False,) * 7 + (True,) + (False,) * 0),
            ("01000000", (True,) + (False,) * 31),
            ("02000000", (False,) + (True,) + (False,) * 30),
            ("04000000", (False,) * 2 + (True,) + (False,) * 29),
            ("08000000", (False,) * 3 + (True,) + (False,) * 28),
            ("10000000", (False,) * 4 + (True,) + (False,) * 27),
            ("20000000", (False,) * 5 + (True,) + (False,) * 26),
            ("40000000", (False,) * 6 + (True,) + (False,) * 25),
            ("80000000", (False,) * 7 + (True,) + (False,) * 24),
            ("80000080", (False,) * 7 + (True,) + (False,) * 23 + (True,)),
            (
                "40000040",
                (False,) * 6 + (True,) + (False,) * 23 + (True,) + (False,),
            ),
            (
                "20000020",
                (False,) * 5 + (True,) + (False,) * 23 + (True,) + (False,) * 2,
            ),
        ],
        name_func=encode_name_func,
    )
    def test_states(self, mask, expected):
        states = States(mask)
        self.assertEqual(expected, states.states)
        i = 1
        print(states.active_set)
        for bit in expected:
            print(bit)
            active = i in states.active_set
            assert active == bit
            i = i + 1

    def test_update_zone(self) -> None:
        states = States("0000")
        assert not any(states.states)

        # Turn zone 2 on
        states2 = states.update_zone(2, True)
        assert states2.active(2) is True
        assert states2.active_set == {2}
        assert states2.states[1] is True
        assert states2.states[:8] == (
            False,
            True,
            False,
            False,
            False,
            False,
            False,
            False,
        )

        # Turn zone 2 off
        states3 = states2.update_zone(2, False)
        assert states3.active(2) is False
        assert states3.active_set == set()

        # Turn zone 9 on (across byte boundary)
        states4 = states.update_zone(9, True)
        assert states4.active(9) is True
        assert states4.active_set == {9}
        assert states4.states[8] is True


@pytest.mark.parametrize(
    ("response", "expected_name"),
    [
        (
            {"modelID": 2067, "protocolRevisionMajor": 2, "protocolRevisionMinor": 12},
            "ARC8",
        ),
        (
            {"modelID": 9999, "protocolRevisionMajor": 2, "protocolRevisionMinor": 12},
            "Unknown",
        ),
    ],
)
def test_model_info(response: dict[str, Any], expected_name: str) -> None:
    """Test parsing of ModelInfo responses."""
    mv = ModelAndVersion(
        response["modelID"],
        response["protocolRevisionMajor"],
        response["protocolRevisionMinor"],
    )
    assert mv.model_name == expected_name
    assert mv.model_info.name == expected_name


def test_lcr_series_capabilities() -> None:
    """Test LCR series capabilities grounded in isInLCRSeries() and ControllerType."""
    # Base ESP-RZXe (0x0003): Zone-based, 8 stations, no combined state or stacked watering
    rzxe = ModelAndVersion(0x0003, 1, 0).model_info
    assert rzxe.program_based is False
    assert rzxe.max_programs == 0
    assert rzxe.max_stations == 8
    assert rzxe.max_station_pages == 0
    assert rzxe.max_rain_delay_days == 14
    assert rzxe.max_runtime_seconds == 21600
    assert rzxe.supports_combined_state is False
    assert rzxe.supports_stacked_watering is False
    assert rzxe.supports_flow_sensor is False

    # Upgraded ESP-RZXe2 (0x0103): Zone-based, but supports combined state and stacked watering
    rzxe2 = ModelAndVersion(0x0103, 2, 0).model_info
    assert rzxe2.program_based is False
    assert rzxe2.max_stations == 8
    assert rzxe2.supports_combined_state is True
    assert rzxe2.supports_stacked_watering is True
    assert rzxe2.supports_event_timestamp is True


def test_tm2_series_capabilities() -> None:
    """Test TM2 series capabilities grounded in isUpgradedTM2() and ControllerType."""
    # Base ESP-TM2 (0x0005): 12 stations, supports stacked watering, but not combined state or event timestamp
    tm2 = ModelAndVersion(0x0005, 1, 0).model_info
    assert tm2.program_based is True
    assert tm2.max_programs == 3
    assert tm2.max_run_times == 4
    assert tm2.max_stations == 12
    assert tm2.max_station_pages == 0
    assert tm2.max_rain_delay_days == 14
    assert tm2.supports_combined_state is False
    assert tm2.supports_event_timestamp is False
    assert tm2.supports_stacked_watering is True

    # Upgraded ESP-TM2v3 (0x010A): 12 stations, adds combined state and event timestamp support
    tm2v3 = ModelAndVersion(0x010A, 2, 0).model_info
    assert tm2v3.program_based is True
    assert tm2v3.max_stations == 12
    assert tm2v3.max_station_pages == 0
    assert tm2v3.supports_combined_state is True
    assert tm2v3.supports_event_timestamp is True
    assert tm2v3.supports_stacked_watering is True


def test_commercial_lx_series_capabilities() -> None:
    """Test commercial LX series capabilities grounded in isLXController() and definitions."""
    # LXME2 (0x000C): 48 stations, 2 pages (pages 0-1), 40 programs, 10 starts, 30 days rain delay, 96h runtime
    lxme2 = ModelAndVersion(0x000C, 1, 3).model_info
    assert lxme2.program_based is True
    assert lxme2.max_programs == 40
    assert lxme2.max_run_times == 10
    assert lxme2.max_stations == 48
    assert lxme2.max_station_pages == 1
    assert lxme2.max_rain_delay_days == 30
    assert lxme2.max_runtime_seconds == 345600
    assert lxme2.max_seasonal_adjust == 300
    assert lxme2.supports_event_timestamp is True
    assert lxme2.supports_stacked_watering is True
    assert lxme2.supports_combined_state is False

    # LX-IVM (0x000D): 60 stations, 2 pages, 10 programs, 8 starts, 3 flow/weather sensors
    lxivm = ModelAndVersion(0x000D, 1, 0).model_info
    assert lxivm.max_stations == 60
    assert lxivm.max_station_pages == 1
    assert lxivm.max_programs == 10
    assert lxivm.max_run_times == 8
    assert lxivm.max_sensors == 3
    assert lxivm.max_rain_delay_days == 30
    assert lxivm.max_runtime_seconds == 345600
    assert lxivm.supports_flow_sensor is True
    assert lxivm.supports_stacked_watering is True

    # LX-IVM-PRO (0x000E): 240 stations, 8 pages (pages 0-7), 40 programs, 8 starts, 7 sensors
    lxivm_pro = ModelAndVersion(0x000E, 1, 0).model_info
    assert lxivm_pro.max_stations == 240
    assert lxivm_pro.max_station_pages == 7
    assert lxivm_pro.max_programs == 40
    assert lxivm_pro.max_run_times == 8
    assert lxivm_pro.max_sensors == 7
    assert lxivm_pro.max_rain_delay_days == 30
    assert lxivm_pro.max_runtime_seconds == 345600
    assert lxivm_pro.supports_flow_sensor is True
    assert lxivm_pro.supports_stacked_watering is True


def test_isk_series_capabilities() -> None:
    """Test ISK series (RC2 / ARC8) capabilities grounded in isISKController()."""
    for model_id in (0x0812, 0x0813):
        isk = ModelAndVersion(model_id, 2, 0).model_info
        assert isk.max_stations == 8
        assert isk.max_station_pages == 0
        assert isk.max_programs == 3
        assert isk.max_run_times == 4
        assert isk.max_rain_delay_days == 14
        assert isk.max_runtime_seconds == 21600
        assert isk.supports_event_timestamp is True
        assert isk.supports_combined_state is False
        assert isk.supports_stacked_watering is False
        assert isk.supports_flow_sensor is False


def test_me3_and_2wire_capabilities() -> None:
    """Test ESP-ME3 and ESP-2WIRE capabilities grounded in ControllerType."""
    # ESP-ME3 (0x0009): 22 stations, 2 pages, flow sensor, schedule timestamp
    me3 = ModelAndVersion(0x0009, 1, 0).model_info
    assert me3.max_stations == 22
    assert me3.max_station_pages == 1
    assert me3.max_programs == 4
    assert me3.max_run_times == 6
    assert me3.supports_flow_sensor is True
    assert me3.supports_event_timestamp is True
    assert me3.supports_stacked_watering is False
    assert me3.supports_combined_state is False

    # ESP-2WIRE (0x0011): 50 stations, 2 pages, flow sensor, event timestamp
    esp2wire = ModelAndVersion(0x0011, 1, 0).model_info
    assert esp2wire.max_stations == 50
    assert esp2wire.max_station_pages == 1
    assert esp2wire.supports_flow_sensor is True
    assert esp2wire.supports_event_timestamp is True
    assert esp2wire.supports_stacked_watering is False


def test_unknown_model_capabilities_fallback() -> None:
    """Test unknown model ID fallback to safe default capabilities."""
    unknown = ModelAndVersion(0x9999, 1, 0).model_info
    assert unknown.max_stations == 0
    assert unknown.max_programs == 0
    assert unknown.max_station_pages == 0
    assert unknown.max_rain_delay_days == 0
    assert unknown.max_runtime_seconds == 0
    assert unknown.supports_combined_state is False
    assert unknown.supports_flow_sensor is False
