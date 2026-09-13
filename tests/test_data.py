import unittest
from typing import Any

import pytest
from parameterized import parameterized

from pyrainbird.data import (
    Feature,
    ModelAndVersion,
    ModelInfo,
    ModelLimits,
    States,
)


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
    """Test LCR series profile (station-level scheduling architecture and upgraded RZXe2 commands)."""
    # Base ESP-RZXe (0x0003): Zone-based, 8 stations, no combined state or stacked watering
    rzxe = ModelAndVersion(0x0003, 1, 0).model_info
    assert not rzxe.is_feature_supported(Feature.PROGRAM_BASED)
    assert rzxe.max_programs == 0
    assert rzxe.max_stations == 8
    assert rzxe.supports_water_budget is True
    assert rzxe.limits.max_station_pages == 0
    assert rzxe.limits.max_rain_delay_days == 14
    assert rzxe.limits.max_runtime_seconds == 21600
    assert not rzxe.is_feature_supported(Feature.COMBINED_STATE)
    assert not rzxe.is_feature_supported(Feature.STACKED_WATERING)
    assert not rzxe.is_feature_supported(Feature.FLOW_SENSOR)

    # Upgraded ESP-RZXe2 (0x0103): Zone-based, but supports combined state and stacked watering
    rzxe2 = ModelAndVersion(0x0103, 2, 0).model_info
    assert not rzxe2.is_feature_supported(Feature.PROGRAM_BASED)
    assert rzxe2.max_stations == 8
    assert rzxe2.is_feature_supported(Feature.COMBINED_STATE)
    assert rzxe2.is_feature_supported(Feature.STACKED_WATERING)
    assert rzxe2.is_feature_supported(Feature.EVENT_TIMESTAMP)


def test_tm2_series_capabilities() -> None:
    """Test TM2 series profile (baseline vs upgraded TM2 with 0x4C combined state and 0x4A timestamps)."""
    # Base ESP-TM2 (0x0005): 12 stations, supports stacked watering, but not combined state or event timestamp
    tm2 = ModelAndVersion(0x0005, 1, 0).model_info
    assert tm2.is_feature_supported(Feature.PROGRAM_BASED)
    assert tm2.max_programs == 3
    assert tm2.max_run_times == 4
    assert tm2.max_stations == 12
    assert tm2.supports_water_budget is True
    assert tm2.limits.max_station_pages == 0
    assert tm2.limits.max_rain_delay_days == 14
    assert not tm2.is_feature_supported(Feature.COMBINED_STATE)
    assert not tm2.is_feature_supported(Feature.EVENT_TIMESTAMP)
    assert tm2.is_feature_supported(Feature.STACKED_WATERING)

    # Upgraded ESP-TM2v3 (0x010A): 12 stations, adds combined state and event timestamp support
    tm2v3 = ModelAndVersion(0x010A, 2, 0).model_info
    assert tm2v3.is_feature_supported(Feature.PROGRAM_BASED)
    assert tm2v3.max_stations == 12
    assert tm2v3.limits.max_station_pages == 0
    assert tm2v3.is_feature_supported(Feature.COMBINED_STATE)
    assert tm2v3.is_feature_supported(Feature.EVENT_TIMESTAMP)
    assert tm2v3.is_feature_supported(Feature.STACKED_WATERING)


def test_commercial_lx_series_capabilities() -> None:
    """Test commercial LX series profile (30-day rain delay, 96h runtimes, 300% seasonal adjust, multi-bank pages)."""
    # LXME2 (0x000C): 48 stations, 2 pages (pages 0-1), 40 programs, 10 starts, 30 days rain delay, 96h runtime
    lxme2 = ModelAndVersion(0x000C, 1, 3).model_info
    assert lxme2.is_feature_supported(Feature.PROGRAM_BASED)
    assert lxme2.max_programs == 40
    assert lxme2.max_run_times == 10
    assert lxme2.max_stations == 48
    assert lxme2.limits.max_station_pages == 1
    assert lxme2.limits.max_rain_delay_days == 30
    assert lxme2.limits.max_runtime_seconds == 345600
    assert lxme2.limits.max_seasonal_adjust == 300
    assert lxme2.is_feature_supported(Feature.EVENT_TIMESTAMP)
    assert lxme2.is_feature_supported(Feature.STACKED_WATERING)
    assert not lxme2.is_feature_supported(Feature.COMBINED_STATE)

    # LX-IVM (0x000D): 60 stations, 2 pages, 10 programs, 8 starts, 3 flow/weather sensors
    lxivm = ModelAndVersion(0x000D, 1, 0).model_info
    assert lxivm.max_stations == 60
    assert lxivm.limits.max_station_pages == 1
    assert lxivm.max_programs == 10
    assert lxivm.max_run_times == 8
    assert lxivm.limits.max_sensors == 3
    assert lxivm.limits.max_rain_delay_days == 30
    assert lxivm.limits.max_runtime_seconds == 345600
    assert lxivm.is_feature_supported(Feature.FLOW_SENSOR)
    assert lxivm.is_feature_supported(Feature.STACKED_WATERING)

    # LX-IVM-PRO (0x000E): 240 stations, 8 pages (pages 0-7), 40 programs, 8 starts, 7 sensors
    lxivm_pro = ModelAndVersion(0x000E, 1, 0).model_info
    assert lxivm_pro.max_stations == 240
    assert lxivm_pro.limits.max_station_pages == 7
    assert lxivm_pro.max_programs == 40
    assert lxivm_pro.max_run_times == 8
    assert lxivm_pro.limits.max_sensors == 7
    assert lxivm_pro.limits.max_rain_delay_days == 30
    assert lxivm_pro.limits.max_runtime_seconds == 345600
    assert lxivm_pro.is_feature_supported(Feature.FLOW_SENSOR)
    assert lxivm_pro.is_feature_supported(Feature.STACKED_WATERING)


def test_isk_series_capabilities() -> None:
    """Test ISK series profile (compact 8-station architecture, 0x4A timestamps, non-combined polling)."""
    for model_id in (0x0812, 0x0813):
        isk = ModelAndVersion(model_id, 2, 0).model_info
        assert isk.max_stations == 8
        assert isk.limits.max_station_pages == 0
        assert isk.max_programs == 3
        assert isk.max_run_times == 4
        assert isk.limits.max_rain_delay_days == 14
        assert isk.limits.max_runtime_seconds == 21600
        assert isk.is_feature_supported(Feature.EVENT_TIMESTAMP)
        assert not isk.is_feature_supported(Feature.COMBINED_STATE)
        assert not isk.is_feature_supported(Feature.STACKED_WATERING)
        assert not isk.is_feature_supported(Feature.FLOW_SENSOR)


def test_me3_and_2wire_capabilities() -> None:
    """Test modular expansion profile (ESP-ME3 and ESP-2Wire 2-page capacity and flow sensor telemetry)."""
    # ESP-ME3 (0x0009): 22 stations, 2 pages, flow sensor, schedule timestamp
    me3 = ModelAndVersion(0x0009, 1, 0).model_info
    assert me3.max_stations == 22
    assert me3.limits.max_station_pages == 1
    assert me3.max_programs == 4
    assert me3.max_run_times == 6
    assert me3.is_feature_supported(Feature.FLOW_SENSOR)
    assert me3.is_feature_supported(Feature.EVENT_TIMESTAMP)
    assert not me3.is_feature_supported(Feature.STACKED_WATERING)
    assert not me3.is_feature_supported(Feature.COMBINED_STATE)

    # ESP-2WIRE (0x0011): 50 stations, 2 pages, flow sensor, event timestamp
    esp2wire = ModelAndVersion(0x0011, 1, 0).model_info
    assert esp2wire.max_stations == 50
    assert esp2wire.limits.max_station_pages == 1
    assert esp2wire.is_feature_supported(Feature.FLOW_SENSOR)
    assert esp2wire.is_feature_supported(Feature.EVENT_TIMESTAMP)
    assert not esp2wire.is_feature_supported(Feature.STACKED_WATERING)


def test_unknown_model_capabilities_fallback() -> None:
    """Test unknown model ID fallback to safe default capabilities."""
    unknown = ModelAndVersion(0x9999, 1, 0).model_info
    assert unknown.max_stations == 0
    assert unknown.max_programs == 0
    assert unknown.limits.max_station_pages == 0
    assert unknown.limits.max_rain_delay_days == 0
    assert unknown.limits.max_runtime_seconds == 0
    assert not unknown.is_feature_supported(Feature.COMBINED_STATE)
    assert not unknown.is_feature_supported(Feature.FLOW_SENSOR)


def test_feature_flag_and_limits_structures() -> None:
    """Test the Feature(Flag) enum and ModelLimits dataclass directly."""
    me3 = ModelAndVersion(0x0009, 1, 0).model_info
    assert isinstance(me3.limits, ModelLimits)
    assert me3.limits.max_stations == 22
    assert me3.limits.max_station_pages == 1
    assert me3.limits.max_programs == 4
    assert me3.limits.max_run_times == 6

    assert isinstance(me3.features, Feature)
    assert Feature.FLOW_SENSOR in me3.features
    assert me3.is_feature_supported(Feature.FLOW_SENSOR)
    assert Feature.EVENT_TIMESTAMP in me3.features
    assert Feature.WATER_BUDGET in me3.features
    assert Feature.PROGRAM_BASED in me3.features
    assert Feature.COMBINED_STATE not in me3.features
    assert not me3.is_feature_supported(Feature.COMBINED_STATE)
    assert Feature.STACKED_WATERING not in me3.features

    lxme2 = ModelAndVersion(0x000C, 1, 3).model_info
    assert isinstance(lxme2.limits, ModelLimits)
    assert lxme2.limits.max_stations == 48
    assert lxme2.limits.max_rain_delay_days == 30
    assert Feature.STACKED_WATERING in lxme2.features
    assert lxme2.is_feature_supported(Feature.STACKED_WATERING)
    assert Feature.EVENT_TIMESTAMP in lxme2.features
    assert Feature.FLOW_SENSOR not in lxme2.features
    assert not lxme2.is_feature_supported(Feature.FLOW_SENSOR)


def test_model_info_from_dict_compatibility() -> None:
    """Test ModelInfo.from_dict handles both legacy flat and direct Feature formats."""
    # Legacy flat dictionary
    legacy = ModelInfo.from_dict(
        {
            "device_id": "0009",
            "code": "ESP_ME3",
            "name": "ESP-ME3",
            "max_stations": 22,
            "max_programs": 4,
            "max_run_times": 6,
            "max_station_pages": 1,
            "program_based": True,
            "seconds_based": True,
            "supports_water_budget": True,
            "supports_combined_state": True,
            "supports_event_timestamp": True,
            "supports_stacked_watering": True,
            "supports_flow_sensor": True,
        }
    )
    assert legacy.limits.max_stations == 22
    assert legacy.max_stations == 22
    assert legacy.is_feature_supported(Feature.SECONDS_BASED)
    assert legacy.is_feature_supported(Feature.COMBINED_STATE)

    # Direct Feature instance
    direct_feat = ModelInfo.from_dict(
        {
            "device_id": "0009",
            "code": "ESP_ME3",
            "name": "ESP-ME3",
            "limits": {"max_stations": 22},
            "features": Feature.WATER_BUDGET | Feature.FLOW_SENSOR,
        }
    )
    assert direct_feat.is_feature_supported(Feature.WATER_BUDGET)
    assert direct_feat.is_feature_supported(Feature.FLOW_SENSOR)

    # List of Feature enums
    enum_list = ModelInfo.from_dict(
        {
            "device_id": "0009",
            "code": "ESP_ME3",
            "name": "ESP-ME3",
            "limits": {"max_stations": 22},
            "features": [Feature.FLOW_SENSOR],
        }
    )
    assert enum_list.is_feature_supported(Feature.FLOW_SENSOR)
