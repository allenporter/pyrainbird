"""Unit tests for BaseControllerDevice core SIP state machine."""

from __future__ import annotations

from pyrainbird.testing.devices.base import BaseControllerDevice


def test_model_version_and_available_stations() -> None:
    """Verify 0x02 model/version, 0x03 available stations pages, 0x04 command support, 0x05 serial, 0x0B firmware."""
    dev_2wire = BaseControllerDevice("ESP_2WIRE")
    assert dev_2wire.handle_sip("02") == "8200110100"
    assert dev_2wire.handle_sip("0300") == "8300FFFFFFFF"
    assert dev_2wire.handle_sip("0301") == "8301FFFF0300"

    dev_tm2 = BaseControllerDevice(
        0x0005,
        version_major=1,
        version_minor=3,
        password="secret",
    )
    dev_tm2.fw_submodules = ["01020304"]
    assert dev_tm2.profile.controller_type == "ESP_TM2"
    assert dev_tm2.encryption_required is True
    assert dev_tm2.handle_sip("02") == "8200050103"
    assert dev_tm2.handle_sip("044C") == "844C00"
    assert dev_tm2.handle_sip("045C") == "845C00"
    assert dev_tm2.handle_sip("0402") == "840201"
    assert dev_tm2.handle_sip("05").startswith("85")
    assert dev_tm2.handle_sip("0B").endswith("0101020304")
    assert dev_tm2.handle_sip("FF") == "00FF01"
    assert dev_tm2.handle_sip("0") == "000002"


def test_core_sip_time_date_budget_and_irrigation() -> None:
    """Verify core SIP opcodes for time, date, water budget, rain delay, manual run, and combined state."""
    dev = BaseControllerDevice("ESP_ME3")

    # Set/Get Time (0x11 / 0x10)
    assert dev.handle_sip("11091E00") == "0111"
    assert dev.handle_sip("10") == "90091E00"
    assert dev.handle_sip("11990000") == "001104"

    # Set/Get Date (0x13 / 0x12): 2026-03-15 -> day=15 (0x0F), month=3, year=2026 (0x37EA)
    assert dev.handle_sip("130F37EA") == "0113"
    assert dev.handle_sip("12") == "920F37EA"
    assert dev.handle_sip("130007EA") == "001304"

    # Set/Get Water Budget (0x31 / 0x30) and Monthly Adjust (0x33 / 0x32)
    assert dev.handle_sip("3101007D") == "0131"
    assert dev.handle_sip("3001") == "B001007D"
    assert dev.handle_sip("3302006E") == "0133"
    assert dev.handle_sip("3202") == "B202006E"

    # Set/Get Rain Delay (0x37 / 0x36) and Rain Sensor (0x3E)
    assert dev.handle_sip("370005") == "0137"
    assert dev.handle_sip("36") == "B60005"
    assert dev.handle_sip("3E") == "BE00"

    # Manually Run Station (0x39), Stack Run Seconds (0x2B), Test All (0x2C / 0x3A), Advance (0x42), Stop (0x40)
    assert dev.handle_sip("3900020A") == "0139"
    assert dev.handle_sip("2B0003012C") == "012B"
    assert dev.handle_sip("3F00") == "BF0002000000"
    assert dev.handle_sip("2D") == "012D"
    assert dev.paused is True
    assert dev.handle_sip("2E") == "012E"
    assert dev.paused is False
    assert dev.handle_sip("4200") == "0142"
    assert dev.active_station == 3
    assert dev.handle_sip("40") == "0140"
    assert dev.handle_sip("3F00") == "BF0000000000"

    assert dev.handle_sip("3800") == "0138"
    assert dev.handle_sip("3A05") == "013A"
    assert dev.handle_sip("2C003C") == "012C"
    assert dev.handle_sip("3D01") == "BD0100000000"
    assert dev.handle_sip("48") == "C801"
    assert dev.handle_sip("4900") == "0149"
    assert dev.handle_sip("48") == "C800"
    assert dev.handle_sip("4A01") == "CA0100000000"
    assert dev.handle_sip("4D0001") == "CD000100000000"
    assert len(dev.handle_sip("4D0101")) == 54

    # Combined controller state (0x4C -> 0xCC) on a model supporting 0x4C
    dev_tm2v3 = BaseControllerDevice("ESP_TM2v3")
    dev_tm2v3.handle_sip("11091E00")
    dev_tm2v3.handle_sip("130F37EA")
    dev_tm2v3.handle_sip("370005")
    cc_resp = dev_tm2v3.handle_sip("4C")
    assert cc_resp.startswith("CC091E000F37EA0005")

    # NAK for bad length or manual run exceeding model maximum_manual_run_seconds (100 min = 0x64)
    assert dev.handle_sip("1109") == "001102"
    assert dev.handle_sip("39000164") == "0139"
    assert dev.handle_sip("39000165") == "003904"
    assert dev.handle_sip("4B000164") == "014B"
    assert dev.handle_sip("4B000165") == "004B04"
