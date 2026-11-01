"""Protocol constants, BLE GATT UUIDs, CDT schema re-export, and Universal enum tables."""

from __future__ import annotations

from .cdt_schema import (
    CDT_ACK,
    CDT_NAK_INVALID_DATA,
    CDT_NAK_INVALID_DATATYPE,
    CDT_NAK_INVALID_ID,
    CDT_NAK_INVALID_INDEX,
    CDT_NAK_INVALID_RANK,
    CDT_SCHEMA,
)

# BLE GATT UUID Constants
BLE_CBOS_SIP_WRITE_UUID = "0000fe46-8e22-4541-9d4c-21edae82ed19"
BLE_CBOS_SIP_NOTIFY_UUID = "0000fe47-8e22-4541-9d4c-21edae82ed19"
BLE_CBOS_OTA_WRITE_UUID = "0000fe44-8e22-4541-9d4c-21edae82ed19"
BLE_CBOS_OTA_NOTIFY_UUID = "0000fe45-8e22-4541-9d4c-21edae82ed19"
BLE_CBOS_AUX_NOTIFY_UUID = "0000fe42-8e22-4541-9d4c-21edae82ed19"
BLE_CCCD_UUID = "00002902-0000-1000-8000-00805F9B34FB"

TBOS_BT_SERVICE_UUID = "F4780001-F54B-4C45-B4BE-6DB9FFB0703F"
TBOS_BT_NOTIFY_UUID = "F4780002-F54B-4C45-B4BE-6DB9FFB0703F"
TBOS_BT_WRITE_UUID = "F4780003-F54B-4C45-B4BE-6DB9FFB0703F"

TBOS_BT_LT_SERVICE_UUID = "863A0001-008C-4AEE-92CF-0B6F98FEE25D"
TBOS_BT_LT_NOTIFY_UUID = "863A0002-008C-4AEE-92CF-0B6F98FEE25D"
TBOS_BT_LT_WRITE_UUID = "863A0003-008C-4AEE-92CF-0B6F98FEE25D"

# Universal Alarm Bitmask Constants
ALARM_STATUS_MASKS: dict[str, int] = {
    "NO_WATER_DAYS": 1 << 8,
    "NO_RUN_TIME": 1 << 9,
    "NO_START_TIME": 1 << 10,
    "NO_PROGRAM_AUTO_RUN": 1 << 11,
    "MAX_PROGRAM_QUEUED_EXCEEDED": 1 << 12,
    "FLOW_ALARM": 1 << 13,
    "ZERO_LEARNED_FLOW": 1 << 14,
    "LOW_FLO_ZONE_RATE": 1 << 15,
    "TWO_WIRE_PATH_OFF": 1 << 32,
    "NO_TWO_WIRE_MODULE": 1 << 33,
    "INVALID_MODULE_INSTALL": 1 << 34,
    "ALL_ADDRESS_ZERO": 1 << 36,
    "DUPLICATE_ADDRESS": 1 << 37,
    "SHORT_FINDING": 1 << 38,
    "SHORT_TWO_WIRE_SEGMENTS": 1 << 39,
    "NOT_RESPONDING": 1 << 40,
    "TWO_WIRE_MAPPING": 1 << 41,
    "IRRIGATION_NOT_READY": 1 << 43,
    "MV_SHORT": 1 << 48,
    "STATION_SHORT": 1 << 49,
    "VALVE_SHORTS": 1 << 50,
}

WEATHER_SENSOR_STATUS_CODES: dict[str, int] = {
    "ByPassed": 0,
    "Monitoring": 1,
    "Prevent": 2,
    "Pause": 3,
    "Inactive": 4,
    "Unknown": 0xFF,
}

DISCOVERY_PROGRESS_STATUS_CODES: dict[str, int] = {
    "NOT_STARTED": 0,
    "DISCOVERY_NOT_STARTED": 0,
    "IN_PROGRESS": 1,
    "DISCOVERY_IN_PROGRESS": 1,
    "COMPLETED": 2,
    "DISCOVERY_COMPLETED": 2,
    "ABORTED": 3,
    "DISCOVERY_ABORTED": 3,
    "ABORTED_BY_SHORT": 4,
    "ASSIGNING": 5,
    "ASSIGN_FAILED": 6,
}

STATION_STATE_CODES: dict[str, int] = {
    "Idle": 0,
    "Pending": 1,
    "Cycling": 2,
    "Soaking": 3,
    "InterStationDelay": 4,
    "DisableBySensor": 5,
    "PreventedBySensor": 6,
    "PauseBySensor": 7,
}

PROGRAM_SOURCE_CODES: dict[str, int] = {
    "Unknown": 0,
    "ManualTest": 1,
    "RemoteTest": 2,
    "ManualValve": 3,
    "RemoteValve": 4,
    "ManualProgram": 5,
    "RemoteProgram": 6,
    "AutoProgram": 7,
    "CentralTest": 8,
    "CentralValve": 9,
    "CentralProgram": 10,
}

MANUAL_RUN_SOURCE_NAMES: dict[int, str] = {
    0: "FROM_UNKNOWN",
    1: "FROM_GUI",
    2: "FROM_REMOTE",
    3: "FROM_CIC",
    4: "FROM_AUTO",
    5: "FROM_UBUS",
}

MANUAL_RUN_TO_PROGRAM_SOURCE: dict[int, str] = {
    0: "RemoteProgram",
    1: "ManualProgram",
    2: "RemoteProgram",
    3: "CentralProgram",
    4: "AutoProgram",
    5: "RemoteProgram",
}

__all__ = [
    "ALARM_STATUS_MASKS",
    "BLE_CBOS_AUX_NOTIFY_UUID",
    "BLE_CBOS_OTA_NOTIFY_UUID",
    "BLE_CBOS_OTA_WRITE_UUID",
    "BLE_CBOS_SIP_NOTIFY_UUID",
    "BLE_CBOS_SIP_WRITE_UUID",
    "BLE_CCCD_UUID",
    "CDT_ACK",
    "CDT_NAK_INVALID_DATA",
    "CDT_NAK_INVALID_DATATYPE",
    "CDT_NAK_INVALID_ID",
    "CDT_NAK_INVALID_INDEX",
    "CDT_NAK_INVALID_RANK",
    "CDT_SCHEMA",
    "DISCOVERY_PROGRESS_STATUS_CODES",
    "MANUAL_RUN_SOURCE_NAMES",
    "MANUAL_RUN_TO_PROGRAM_SOURCE",
    "PROGRAM_SOURCE_CODES",
    "STATION_STATE_CODES",
    "TBOS_BT_LT_NOTIFY_UUID",
    "TBOS_BT_LT_SERVICE_UUID",
    "TBOS_BT_LT_WRITE_UUID",
    "TBOS_BT_NOTIFY_UUID",
    "TBOS_BT_SERVICE_UUID",
    "TBOS_BT_WRITE_UUID",
    "WEATHER_SENSOR_STATUS_CODES",
]
