"""Unit tests for LCRZoneDevice, ST8ZoneDevice, LegacyProgramDevice, and UpgradedTM2Device."""

from __future__ import annotations

from pyrainbird.testing.devices.lcr import LCRZoneDevice, ST8ZoneDevice
from pyrainbird.testing.devices.legacy_sip import (
    LegacyProgramDevice,
    UpgradedTM2Device,
)


def test_lcr_zone_schedule_and_st8_rain_sensor() -> None:
    """Verify zone-centric LCR schedule pages and ST8 bit-7 rain sensor polarity."""
    rzxe = LCRZoneDevice("ESP_RZXe")
    assert rzxe.handle_sip("21000001") == "0121"
    assert rzxe.handle_sip("200000") == "A0000001"
    assert rzxe.handle_sip("21000214219090909090037F0302") == "0121"
    assert rzxe.handle_sip("200002") == "A0000214219090909090037F0302"

    # 8-zone seasonal adjust vector (0x33 / 0x32)
    assert rzxe.handle_sip("33FF00780064006400640064006400640064") == "0133"
    assert rzxe.handle_sip("32FF") == "B2FF00780064006400640064006400640064"

    st8 = ST8ZoneDevice("ST8X_WF2")
    assert st8.handle_sip("21000080") == "0121"
    assert st8.rain_sensor_bypassed is True
    assert st8.handle_sip("200000") == "A0000080"

    # ST8 10-byte queue page 0 response (0x3B00 -> 0xBB00...)
    st8.handle_sip("39000305")
    q_resp = st8.handle_sip("3B00")
    assert q_resp.startswith("BB00")
    assert len(q_resp) == 20


def test_program_centric_schedules_and_current_queue() -> None:
    """Verify program-centric SIP schedules and queue status (0x3B -> 0xBB)."""
    tm2v3 = UpgradedTM2Device("ESP_TM2v3")
    assert tm2v3.handle_sip("21000000050201") == "0121"
    assert tm2v3.handle_sip("200000") == "A0000000050201"
    assert tm2v3.handle_sip("210008003C0078") == "0121"
    assert tm2v3.handle_sip("200008") == "A00008003C0078"
    assert tm2v3.handle_sip("2100107F0000006402") == "0121"
    assert tm2v3.handle_sip("200010") == "A000107F0000006402"
    assert tm2v3.handle_sip("21002001000101") == "0121"
    assert tm2v3.handle_sip("200020") == "A0002001000101"
    assert tm2v3.handle_sip("21004000010001") == "0121"
    assert tm2v3.handle_sip("200040") == "A0004000010001"
    assert tm2v3.handle_sip("210080000A0014001E0005000F0000") == "0121"
    assert tm2v3.handle_sip("200080") == "A00080000A0014001E0005000F0000"

    # Stack run station 1 (10m) and station 2 (10m), then check queue pages 0 and 1, advance and stop
    assert tm2v3.handle_sip("4B00010A") == "014B"
    assert tm2v3.handle_sip("4B00020A") == "014B"
    assert tm2v3.active_station == 1
    assert tm2v3.handle_sip("3B00").startswith("BB00")
    assert tm2v3.handle_sip("3B01").startswith("BB01")
    assert tm2v3.handle_sip("4200") == "0142"
    assert tm2v3.active_station == 2
    assert tm2v3.handle_sip("40") == "0140"
    assert tm2v3.active_station == 0

    me = LegacyProgramDevice("ESP_ME")
    assert me.handle_sip("210060012C0474FFFFFFFFFFFFFFFF") == "0121"
    assert me.handle_sip("200060") == "A00060012C0474FFFFFFFFFFFFFFFF"

    # BLE schedule subpages (6-byte page 0000, 8-byte program config, calendar days off 0084/0085)
    bat = LegacyProgramDevice("ESP_BAT_PRO")
    assert bat.handle_sip("210000000A0301010F") == "0121"
    assert bat.handle_sip("200000") == "A00000000A0301010F"
    assert bat.handle_sip("2100107F03010000780201") == "0121"
    assert bat.handle_sip("200010") == "A000107F03010000780201"
    days_off_15b = "0C191A" + "000000" * 4
    assert bat.handle_sip("210085" + days_off_15b) == "0121"
    assert bat.handle_sip("200085") == "A00085" + days_off_15b
