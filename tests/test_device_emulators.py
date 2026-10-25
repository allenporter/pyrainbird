"""Comprehensive unit tests for BLE battery, Solem, device factory, and emulator facade."""

from __future__ import annotations

import pytest

from pyrainbird.testing.devices.base import BaseControllerDevice
from pyrainbird.testing.devices.ble import BLEBatteryDevice, SolemTBOSDevice
from pyrainbird.testing.devices.constants import (
    BLE_CBOS_OTA_NOTIFY_UUID,
    BLE_CBOS_OTA_WRITE_UUID,
    BLE_CBOS_SIP_NOTIFY_UUID,
    BLE_CBOS_SIP_WRITE_UUID,
    TBOS_BT_NOTIFY_UUID,
    TBOS_BT_WRITE_UUID,
)
from pyrainbird.testing.devices.lcr import LCRZoneDevice, ST8ZoneDevice
from pyrainbird.testing.devices.legacy_sip import (
    LegacyProgramDevice,
    UpgradedTM2Device,
)
from pyrainbird.testing.devices.universal import UniversalCDTDevice
from pyrainbird.testing.emulator import (
    RainbirdDeviceEmulator,
    create_device_for_model,
    get_device_class_for_model,
)
from pyrainbird.testing.profiles import DEVICE_PROFILES
from pyrainbird.testing.stick import LNK2StickEmulator


def test_ble_gatt_battery_ota_flow_and_solem() -> None:
    """Verify BLE GATT routing, battery/radio status (0x5C), OTA (0x5D / fe44), flow (0x60..0x65), and Solem."""
    bat = RainbirdDeviceEmulator.for_model(
        "ESP_BAT_PRO_FLOW",
        initial_state={
            "battery_percent": 85,
            "battery_voltage_mv": 9100,
            "battery_source_type": "01",
            "ble_snr": 12,
            "ble_rssi": -65,
            "lora_snr": 0,
            "lora_rssi": 0,
            "ota_total_fragments": 0x1234,
            "current_flow_rate_milli": 1500,
        },
    )

    notify_uuid, resp_hex = bat.handle_gatt_write(BLE_CBOS_SIP_WRITE_UUID, "5C")
    assert notify_uuid == BLE_CBOS_SIP_NOTIFY_UUID
    assert resp_hex == "DC8C23010CBF0000"
    assert (
        bat.handle_ble_write(BLE_CBOS_SIP_WRITE_UUID, "5C")["payload_hex"] == resp_hex
    )

    # PIN security (0x55 / 0x59), factory defaults (0x57), raster test (0x58)
    assert bat.handle_sip("55", transport="BLE") == "560001"
    assert bat.handle_sip("5900000001E240", transport="BLE") == "0159"
    assert bat.is_pin_set is True
    assert bat.handle_sip("590000FFFFFFFF", transport="BLE") == "0159"
    assert bat.is_pin_set is False
    assert bat.handle_sip("57", transport="BLE") == "0157"
    assert bat.handle_sip("58", transport="BLE") == "0158"
    assert bat.raster_test_run is True

    # OTA start/end/cancel (0x5D..0x5F) and GATT fragment write
    assert bat.handle_sip("5D00", transport="BLE") == "015D"
    ota_notify_uuid, ota_resp = bat.handle_gatt_write(
        BLE_CBOS_OTA_WRITE_UUID, "01003412DEADBEEF"
    )
    assert ota_notify_uuid == BLE_CBOS_OTA_NOTIFY_UUID
    assert ota_resp == "0100341201"
    assert bat.handle_sip("5E00", transport="BLE") == "015E"
    assert bat.handle_sip("5F00", transport="BLE") == "015F"

    # Flow learn & monitor (0x60..0x65)
    assert bat.handle_sip("6005000000", transport="BLE") == "0160"
    assert bat.learning_stations_mask == "05000000"
    assert bat.handle_sip("62", transport="BLE") == "E201"
    assert bat.handle_sip("61", transport="BLE") == "6200"
    assert bat.handle_sip("61", transport="STICK_TUNNEL_SIP") == "0161"
    assert bat.handle_sip("640100", transport="STICK_TUNNEL_SIP") == "0164"
    assert bat.flow_monitor_enabled is True
    assert bat.handle_sip("63", transport="STICK_TUNNEL_SIP") == "E30100"
    assert bat.handle_sip("6500", transport="STICK_TUNNEL_SIP") == "E500DC05"

    # Solem TBOS-BT frame authentication
    tbos = RainbirdDeviceEmulator.for_model(
        "TBOS_BT", initial_state={"solem_install_code": "01020304"}
    )
    solem_notify, solem_resp = tbos.handle_gatt_write(
        TBOS_BT_WRITE_UUID, "190600010203042700"
    )
    assert solem_notify == TBOS_BT_NOTIFY_UUID
    assert solem_resp == "1A010001"
    assert tbos.solem_authenticated is True
    assert tbos.handle_solem_frame("3102050100") == "32010501"


def test_emulator_json_rpc_tunnel_sip_for_extended_commands() -> None:
    """Verify RainbirdDeviceEmulator routes JSON-RPC tunnelSip extended commands (e.g., 0x0B, 0x0C)."""
    emu = RainbirdDeviceEmulator.for_model("ESP-ME3")
    req = {
        "jsonrpc": "2.0",
        "id": 99,
        "method": "tunnelSip",
        "params": {"data": "0B", "length": 1},
    }
    resp_json = emu.handle_jsonrpc(req)
    assert resp_json is not None
    assert resp_json["result"]["data"].startswith("8B")


@pytest.mark.parametrize(
    ("model", "expected_cls"),
    [
        ("ESP_RZXe", LCRZoneDevice),
        ("ESP_RZXe2", LCRZoneDevice),
        ("ST8X_WF", ST8ZoneDevice),
        ("ST8X_WF2", ST8ZoneDevice),
        ("ESP_ME", LegacyProgramDevice),
        ("ESP_MEv2", LegacyProgramDevice),
        ("ESP_TM2", LegacyProgramDevice),
        ("ESP_TM2v2", UpgradedTM2Device),
        ("ESP_TM2v3", UpgradedTM2Device),
        ("ESP_TM2v4", UpgradedTM2Device),
        ("TM2R", UpgradedTM2Device),
        ("TRU", UpgradedTM2Device),
        ("ESP_CPTM2", UpgradedTM2Device),
        ("ESP_ME3", UniversalCDTDevice),
        ("RC2", UniversalCDTDevice),
        ("ARC8", UniversalCDTDevice),
        ("ESP_2WIRE", UniversalCDTDevice),
        ("LX_ME2", UniversalCDTDevice),
        ("LX_IVM", UniversalCDTDevice),
        ("LX_IVM_PRO", UniversalCDTDevice),
        ("ESP_BAT_BT", BLEBatteryDevice),
        ("ESP_BAT_BT_2", BLEBatteryDevice),
        ("ESP_BAT_BT_4", BLEBatteryDevice),
        ("ESP_BAT_BT_6", BLEBatteryDevice),
        ("ESP_BAT_PRO", BLEBatteryDevice),
        ("ESP_BAT_PRO_EU", BLEBatteryDevice),
        ("ESP_BAT_PRO_FLOW", BLEBatteryDevice),
        ("ESP_BAT_PRO_FLOW_EU", BLEBatteryDevice),
        ("TBOS_BT", SolemTBOSDevice),
        ("TBOS_BT_LT", SolemTBOSDevice),
        ("IQ_GATEWAY", BaseControllerDevice),
    ],
)
def test_device_class_for_model(
    model: str, expected_cls: type[BaseControllerDevice]
) -> None:
    """Verify get_device_class_for_model and create_device_for_model return the separated class."""
    assert get_device_class_for_model(model) is expected_cls
    device = create_device_for_model(model)
    assert type(device) is expected_cls
    assert isinstance(device, BaseControllerDevice)
    assert isinstance(device.stick, LNK2StickEmulator)

    emu = RainbirdDeviceEmulator.for_model(model)
    assert type(emu.device) is expected_cls


def test_all_catalog_models_instantiate_separated_device() -> None:
    """Verify all 31 catalog models instantiate cleanly and respond to 0x02 model/version."""
    assert len(DEVICE_PROFILES) == 31
    for model_name in DEVICE_PROFILES:
        device = create_device_for_model(model_name)
        resp = device.handle_sip("02")
        assert resp.startswith("82")
        assert len(resp) == 10
