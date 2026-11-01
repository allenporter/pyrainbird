"""CDT schema definitions, per-model index limits, and value validators."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..profiles import ControllerProfile

CDT_ACK = 0x00
CDT_NAK_INVALID_DATA = 0x01
CDT_NAK_INVALID_RANK = 0x02
CDT_NAK_INVALID_ID = 0x03
CDT_NAK_INVALID_INDEX = 0x04
CDT_NAK_INVALID_DATATYPE = 0x05

# CDT Metadata: data_id -> (rank, value_width, is_float, default_value)
CDT_SCHEMA: dict[str, tuple[int, int, bool, Any]] = {
    "0100": (0, 2, False, 0),
    "0200": (0, 1, False, 0),
    "0300": (0, 1, False, 0),
    "0400": (0, 1, False, 0),
    "0500": (0, 1, False, 0),
    "0600": (0, 1, False, 0),
    "0700": (1, 1, False, 255),
    "0800": (1, 1, False, 255),
    "0900": (1, 2, False, 255),
    "0A00": (1, 2, False, 0),
    "0B00": (1, 2, False, 0),
    "0C00": (1, 2, False, 0),
    "0D00": (0, 1, False, 0),
    "0E00": (0, 1, False, 0),
    "0F00": (2, 1, False, 1),
    "1000": (2, 1, False, 0),
    "1100": (1, 1, False, 0),
    "1200": (1, 1, False, 3),
    "1300": (1, 1, False, 0),
    "1400": (0, 2, False, 0),
    "1500": (2, 4, False, 0),
    "1600": (1, 2, False, 100),
    "1700": (1, 1, False, 0),
    "1800": (1, 2, False, 100),
    "1900": (2, 1, False, 0),
    "1A00": (1, 1, False, 0),
    "1B00": (0, 1, False, 1),
    "1C00": (0, 1, False, 1),
    "1D00": (3, 2, False, 1440),
    "1E00": (1, 2, False, 1),
    "1F00": (0, 1, False, 0),
    "2000": (0, 1, False, 1),
    "2100": (1, 1, False, 1),
    "2200": (1, 2, False, 1440),
    "2300": (1, 2, False, 1440),
    "2400": (0, 1, False, 0),
    "2500": (0, 1, False, 0),
    "2600": (0, 2, False, 0),
    "2700": (0, 2, False, 0),
    "2800": (0, 2, False, 130),
    "2900": (0, 2, False, 0),
    "2A00": (0, 2, False, 0),
    "2B00": (0, 2, False, 70),
    "2C00": (0, 2, False, 0),
    "2D00": (1, 1, False, 0),
    "2E00": (1, 4, True, 0.0),
    "2F00": (1, 4, False, 0),
    "3000": (1, 255, False, 0),
    "3100": (1, 255, False, 0),
    "3200": (1, 1, False, 0),
    "3300": (0, 4, False, 0),
    "3400": (0, 4, False, 0),
    "3500": (1, 4, False, 0),
    "3600": (1, 4, False, 0),
    "3700": (0, 1, False, 0),
    "3800": (0, 4, False, 0),
    "3900": (1, 1, False, 0),
    "3A00": (1, 4, True, 0.0),
    "3B00": (1, 4, False, 0),
    "3C00": (1, 1, False, 0),
    "3D00": (1, 4, True, 0.0),
    "3E00": (1, 255, False, 0),
    "3F00": (1, 4, True, 0.0),
    "4000": (1, 1, False, 0),
    "4100": (1, 2, False, 0),
    "4200": (1, 2, False, 0),
    "4300": (1, 2, False, 0),
    "4400": (1, 1, False, 0),
    "4500": (0, 2, False, 1440),
    "4600": (0, 1, False, 0),
    "4700": (0, 4, True, 0.0),
    "4800": (1, 1, False, 1),
    "4900": (1, 255, False, 0),
    "4A00": (0, 2, False, 1440),
    "4B00": (0, 2, False, 1440),
    "4C00": (1, 1, False, 0),
    "4D00": (1, 2, False, 0),
    "4E00": (1, 4, True, 0.0),
    "4F00": (1, 4, True, 0.0),
    "5000": (1, 4, True, 0.0),
    "5100": (1, 2, False, 0),
    "5200": (1, 1, False, 0),
    "5300": (1, 1, False, 0),
    "5400": (1, 2, False, 0),
    "5500": (1, 1, False, 0),
    "5600": (1, 2, False, 0),
    "5700": (1, 1, False, 0),
    "5800": (1, 1, False, 0),
    "5900": (1, 1, False, 0),
    "5A00": (1, 1, False, 0),
    "5B00": (1, 2, False, 0),
    "5C00": (1, 2, False, 0),
    "5D00": (1, 1, False, 0),
    "5E00": (1, 1, False, 0),
    "5F00": (1, 1, False, 0),
    "6000": (0, 1, False, 0),
    "6100": (0, 1, False, 0),
    "6200": (0, 1, False, 0),
    "6300": (0, 1, False, 1),
    "6400": (0, 1, False, 0),
    "6500": (0, 1, False, 0),
    "6600": (0, 1, False, 0),
    "6700": (0, 1, False, 0),
    "6800": (0, 1, False, 0),
    "6900": (0, 1, False, 0),
    "6A00": (0, 1, False, 1),
    "6B00": (0, 1, False, 0),
    "6C00": (0, 1, False, 0),
    "6D00": (0, 1, False, 0),
    "6E00": (0, 1, False, 0),
    "7C00": (1, 2, False, 0),
    "8000": (1, 255, False, 0),
    "8100": (1, 1, False, 0),
    "8300": (1, 2, False, 0),
    "8400": (1, 1, False, 0),
    "8500": (1, 2, False, 0),
    "8600": (2, 255, False, 0),
    "8700": (1, 255, False, 0),
    "8B00": (1, 1, False, 0),
}

_PROG_1D_IDS = frozenset(
    {"0C00", "1100", "1200", "1300", "1700", "1800", "2100", "2200", "2300"}
)
_STATION_1D_IDS = frozenset(
    {
        "0A00",
        "0B00",
        "1E00",
        "2D00",
        "2E00",
        "2F00",
        "3000",
        "3100",
        "3D00",
        "3E00",
        "4300",
        "5500",
        "5600",
        "8000",
    }
)
_MV_1D_IDS = frozenset(
    {
        "4100",
        "4400",
        "4900",
        "5200",
        "5300",
        "5400",
        "7C00",
        "8300",
        "8400",
        "8500",
        "8700",
        "8B00",
    }
)
_WEATHER_1D_IDS = frozenset({"1A00", "5A00", "5B00", "5C00", "8100"})
_FLOW_1D_IDS = frozenset(
    {
        "3200",
        "3900",
        "3A00",
        "3B00",
        "3C00",
        "3F00",
        "4000",
        "4200",
        "4D00",
        "4E00",
        "4F00",
        "5000",
        "5100",
    }
)
_BOOL_IDS = frozenset(
    {"0D00", "0F00", "1000", "1700", "1900", "2400", "2500", "4800", "8100"}
)
_TIME_OF_DAY_IDS = frozenset({"1D00", "2200", "2300", "4500", "4A00", "4B00"})


def get_cdt_default(profile: ControllerProfile, data_id: str) -> Any:
    """Return profile-aware factory default for a CDT identifier."""
    if data_id == "1200":
        return profile.default_cyclic_days
    schema = CDT_SCHEMA.get(data_id)
    return 0 if schema is None else schema[3]


def get_cdt_dim_limits(profile: ControllerProfile, data_id: str) -> tuple[int, ...]:
    """Return exclusive upper index bounds per dimension for a CDT identifier."""
    schema = CDT_SCHEMA.get(data_id)
    if schema is None or schema[0] == 0:
        return ()
    rank = schema[0]
    if rank == 1:
        return (_get_rank1_limit(profile, data_id),)
    if rank == 2:
        if data_id == "0F00":
            return (
                (profile.maximum_programs, 7)
                if profile.supports_permanent_days_off
                else (0, 0)
            )
        if data_id == "1000":
            return (profile.maximum_programs, 7)
        if data_id == "1500":
            return (profile.maximum_programs, profile.maximum_stations)
        if data_id == "1900":
            return (profile.maximum_weather_sensors, profile.maximum_stations)
        if data_id == "8600":
            return (profile.maximum_master_valves, profile.maximum_stations)
        return (255, 255)
    return (profile.maximum_programs, 1, profile.maximum_start_times)


def _get_rank1_limit(profile: ControllerProfile, data_id: str) -> int:
    if data_id in _PROG_1D_IDS:
        return profile.maximum_programs
    if data_id in _STATION_1D_IDS:
        return profile.maximum_stations
    if data_id in ("1600", "3500"):
        return 12
    if data_id == "4800":
        return 7
    if data_id in ("0700", "0800", "0900"):
        return profile.maximum_calendar_days_off
    if data_id in _MV_1D_IDS:
        return profile.maximum_master_valves
    if data_id in _WEATHER_1D_IDS:
        return profile.maximum_weather_sensors
    if data_id in _FLOW_1D_IDS:
        return profile.maximum_flow_sensors
    return 255


def is_valid_cdt_write_width(data_id: str, schema_width: int, req_width: int) -> bool:
    """Return True if requested wire value_width is valid for CDT batch write (050B)."""
    if req_width == schema_width:
        return True
    if schema_width == 255 and req_width == 1:
        return True
    if data_id in ("1900", "8100") and req_width == 255:
        return True
    return data_id == "1400" and req_width == 1


def validate_cdt_values(
    profile: ControllerProfile, data_id: str, values: list[Any]
) -> bool:
    """Validate decoded scalar values against controller hardware bounds."""
    for raw in values:
        if not _is_single_cdt_value_valid(profile, data_id, raw):
            return False
    return True


def _is_single_cdt_value_valid(
    profile: ControllerProfile, data_id: str, raw: Any
) -> bool:
    if isinstance(raw, float):
        return raw >= 0.0
    val = int(raw)
    if data_id in _BOOL_IDS:
        return val in (0, 1)
    if data_id in _TIME_OF_DAY_IDS:
        return 0 <= val <= 1440
    if data_id == "1300":
        return 0 <= val <= 5
    if data_id == "1200":
        return val == 0 or (
            profile.minimum_frequency_cycle_days
            <= val
            <= profile.maximum_frequency_cycle_days
        )
    if data_id == "1100":
        return 0 <= val <= profile.maximum_frequency_cycle_days
    if data_id == "1500":
        return 0 <= val <= profile.maximum_run_time_seconds
    if data_id in ("1800", "1600"):
        return profile.minimum_seasonal_adjust <= val <= profile.maximum_seasonal_adjust
    if data_id == "1400":
        return 0 <= val <= profile.maximum_rain_delay_days
    if data_id == "0C00":
        return 0 <= val <= profile.maximum_station_delay_seconds
    if data_id in ("0A00", "0B00"):
        return 0 <= val <= 1440
    if data_id == "0700":
        return (1 <= val <= 31) or val == 255
    if data_id == "0800":
        return (0 <= val <= 11) or val == 255
    if data_id == "0900":
        return (2000 <= val <= 2199) or val == 255
    return True
