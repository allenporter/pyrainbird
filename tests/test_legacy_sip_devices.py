"""Unit tests for LCRZoneDevice, ST8ZoneDevice, LegacyProgramDevice, and UpgradedTM2Device."""

from __future__ import annotations

from pyrainbird import rainbird
from pyrainbird.testing.devices.lcr import LCRZoneDevice, ST8ZoneDevice
from pyrainbird.testing.devices.legacy_sip import (
    LegacyProgramDevice,
    UpgradedTM2Device,
)


def test_lcr_zone_schedule_and_st8_rain_sensor() -> None:
    """Verify zone-centric LCR schedule pages and bit-7 (0x80) rain sensor bypass polarity."""
    rzxe = LCRZoneDevice("ESP_RZXe")
    assert rzxe.handle_sip("05") == "850000000000000000"
    assert rzxe.handle_sip("200000") == "A0000000"
    assert rzxe.handle_sip("21000001") == "0121"
    assert rzxe.rain_sensor_bypassed is False
    assert rzxe.handle_sip("200000") == "A0000000"
    assert rzxe.handle_sip("21000080") == "0121"
    assert rzxe.rain_sensor_bypassed is True
    assert rzxe.handle_sip("200000") == "A0000080"
    assert rzxe.handle_sip("21000214219090909090037F0302") == "0121"
    assert rzxe.handle_sip("200002") == "A0000214219090909090037F0302"

    # v1 ESP-RZXe rejects per-zone 0x32/0x33; v2 ESP-RZXe2 / ST8X-WF2 support 18-byte 0xB2
    assert rzxe.handle_sip("0432") == "843200"
    assert rzxe.handle_sip("32FF") == "003201"
    rzxe2 = LCRZoneDevice("ESP_RZXe2")
    assert rzxe2.handle_sip("0432") == "843201"
    assert rzxe2.handle_sip("33FF00780064006400640064006400640064") == "0133"
    assert rzxe2.handle_sip("32FF") == "B2FF00780064006400640064006400640064"

    # LCR queue page 0 (10B) and page 1 (4B pending station entries)
    assert rzxe.handle_sip("3B00") == "BB000000000000000000"
    assert rzxe.handle_sip("3900010A") == "0139"
    assert rzxe.handle_sip("3B00") == "BB000001000001020258"
    assert rzxe.handle_sip("40") == "0140"
    assert rzxe.handle_sip("3B00") == "BB000000000000000000"

    # ManuallyRunProgram (0x38) with Zone 2 (20m * 100% = 1200s) and Zone 3 (10m * 100% = 600s)
    assert rzxe.handle_sip("2100030A219090909090037F0302") == "0121"
    assert rzxe.handle_sip("3800") == "0138"
    assert rzxe.active_station == 2
    assert rzxe.remaining_runtime_sec == 1200
    rzxe_q0 = rzxe.handle_sip("3B00")
    assert rzxe_q0 == "BB0001010000020104B0"
    rzxe_q1 = rzxe.handle_sip("3B01")
    assert rzxe_q1 == "BB010103025800000000"

    st8 = ST8ZoneDevice("ST8X_WF2")
    assert st8.handle_sip("05") == "850000000000000000"
    assert st8.handle_sip("21000080") == "0121"
    assert st8.rain_sensor_bypassed is True
    assert st8.handle_sip("200000") == "A0000080"

    # ST8 10-byte queue page 0 response (0x3B00 -> 0xBB00...) and pending-only page 1 entries
    st8.handle_sip("4B000305")
    st8.handle_sip("4B00040A")
    q_resp = st8.handle_sip("3B00")
    assert q_resp == "BB00010100000302012C"
    q_page1 = st8.handle_sip("3B01")
    assert q_page1 == "BB010204025800000000"


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

    # ManuallyRunProgram (0x38) expands configured station runtimes with water budget scaling
    assert tm2v3.handle_sip("31000078") == "0131"  # 120% water budget on Program A
    assert tm2v3.handle_sip("3800") == "0138"
    assert tm2v3.active_station == 1
    assert tm2v3.remaining_runtime_sec == 720  # 10 min * 60 * 120% = 720s
    assert tm2v3.auto_queue_count == 2
    tm2_q1 = tm2v3.handle_sip("3B01")
    assert tm2_q1.startswith("BB012102D0220168")
    assert rainbird.decode(tm2_q1) == {
        "type": "CurrentQueueResponse",
        "zones": [
            {"zone": 1, "seconds": 720},
            {"zone": 2, "seconds": 360},
        ],
    }
    assert tm2v3.handle_sip("4200") == "0142"
    assert tm2v3.active_station == 2
    assert tm2v3.remaining_runtime_sec == 360  # 5 min * 60 * 120% = 360s
    assert tm2v3.handle_sip("40") == "0140"

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
    assert me.handle_sip("0432") == "843200"
    assert me.handle_sip("3200") == "003201"
    assert me.handle_sip("210060012C0474FFFFFFFFFFFFFFFF") == "0121"
    assert me.handle_sip("200060") == "A00060012C0474FFFFFFFFFFFFFFFF"
    for stn in range(1, 13):
        assert me.handle_sip(f"4B{stn + 10:04X}05") == "014B"
    # Stations 11..21 on page 1 (5-bit station IDs >= 16 preserved) and station 22 on page 2
    me_q1 = me.handle_sip("3B01")
    assert rainbird.decode(me_q1)["zones"][5] == {"zone": 16, "seconds": 300}
    assert rainbird.decode(me_q1)["zones"][10] == {"zone": 21, "seconds": 300}
    me_q2 = me.handle_sip("3B02")
    assert me_q2.startswith("BB0216012C")

    # BLE schedule subpages (6-byte page 0000, 8-byte program config, calendar days off 0084/0085)
    bat = LegacyProgramDevice("ESP_BAT_PRO")
    assert bat.handle_sip("210000000A0301010F") == "0121"
    assert bat.handle_sip("200000") == "A00000000A0301010F"
    assert bat.handle_sip("2100107F03010000780201") == "0121"
    assert bat.handle_sip("200010") == "A000107F03010000780201"
    days_off_15b = "0C191A" + "000000" * 4
    assert bat.handle_sip("210085" + days_off_15b) == "0121"
    assert bat.handle_sip("200085") == "A00085" + days_off_15b
    # BLE CBOS queue page 1 packs 4-bit program nibble (1..12) in upper nibble + 4-bit station in lower nibble
    bat.queued_entries = [
        {"station_id": 3, "program_id": 9, "remaining_seconds": 600},
    ]
    assert bat.handle_sip("3B01").startswith("BB01A30258")
