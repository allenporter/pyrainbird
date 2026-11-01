"""Tests for high-level local controller client commands using the testing server."""

import datetime
import struct
from collections.abc import AsyncIterator

import aiohttp
import pytest
from freezegun import freeze_time

from pyrainbird import async_client
from pyrainbird.async_client import AsyncRainbirdController
from pyrainbird.const import DayOfWeek, ProgramFrequency
from pyrainbird.exceptions import RainbirdDeviceNackError
from pyrainbird.testing.server import RainbirdFakeServer

PASSWORD = "keepsecret"


def _cdt_set_packet(*blocks: tuple[str, int, str, list[tuple[int, int]]]) -> str:
    """Build a Universal 0x0C CDT batch-write (050B) frame."""
    body_parts = [f"{len(blocks):02X}"]
    for data_id, width, payload_hex, ranges in blocks:
        dims = "".join(
            struct.pack("<HH", start, end).hex().upper() for start, end in ranges
        )
        body_parts.append(f"{data_id}{len(ranges):02X}{dims}{width:02X}{payload_hex}")
    inner = bytes.fromhex("050B" + "".join(body_parts))
    header = bytes.fromhex("0C200001000805000000000C000000000005000000")
    return (header + len(inner).to_bytes(2, "little") + inner).hex().upper()


@pytest.fixture
async def fake_server() -> AsyncIterator[RainbirdFakeServer]:
    """Fixture to start and stop the RainbirdFakeServer."""
    async with RainbirdFakeServer(password=PASSWORD) as server:
        yield server


@pytest.fixture
async def controller(
    fake_server: RainbirdFakeServer,
) -> AsyncIterator[AsyncRainbirdController]:
    """Fixture to create the client controller pointing to the fake server."""
    async with aiohttp.ClientSession() as session:
        controller = await async_client.create_controller(
            session, fake_server.host_port, PASSWORD
        )
        yield controller


@pytest.mark.asyncio
async def test_get_model_and_version(
    controller: AsyncRainbirdController,
) -> None:
    """Test getting model and version capability."""
    model_and_ver = await controller.get_model_and_version()
    assert model_and_ver.model == 5
    assert model_and_ver.model_code == "ESP_TM2"
    assert model_and_ver.major == 1
    assert model_and_ver.minor == 3


@pytest.mark.asyncio
async def test_get_serial_number(
    controller: AsyncRainbirdController,
) -> None:
    """Test getting serial number capability."""
    serial = await controller.get_serial_number()
    assert serial == 0x12635436566


@pytest.mark.asyncio
async def test_rain_delay(
    fake_server: RainbirdFakeServer, controller: AsyncRainbirdController
) -> None:
    """Test reading and setting rain delay capability."""
    fake_server.device.rain_delay = 2
    delay = await controller.get_rain_delay()
    assert delay == 2

    await controller.set_rain_delay(5)
    assert fake_server.device.rain_delay == 5


@pytest.mark.asyncio
async def test_get_zone_state(
    fake_server: RainbirdFakeServer, controller: AsyncRainbirdController
) -> None:
    """Test reading active/inactive zone states capability."""
    fake_server.device.zone_states = {"00": "BF0001000000"}  # Active zone 1
    zone_state = await controller.get_zone_state(1)
    assert zone_state is True

    fake_server.device.zone_states = {"00": "BF0000000000"}  # Inactive zone 1
    zone_state = await controller.get_zone_state(1)
    assert zone_state is False


@pytest.mark.asyncio
async def test_firmware_update_status(
    fake_server: RainbirdFakeServer, controller: AsyncRainbirdController
) -> None:
    """Test getting firmware update status."""
    fake_server.device.update_status = 0
    fake_server.device.lnk_progress = 50
    fake_server.device.unv_progress = 75

    status = await controller.get_firmware_update_status()
    assert status.update_status == 0
    assert status.lnk_progress == 50
    assert status.unv_progress == 75


@pytest.mark.asyncio
async def test_request_firmware_update(
    controller: AsyncRainbirdController,
) -> None:
    """Test triggering a firmware update."""
    res = await controller.request_firmware_update(
        lnk_update_url="http://test/lnk",
        unv_update_url="http://test/unv",
    )
    assert res == {"status": "OK"}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "expected_code", "expected_programs", "expected_zone_schedules"),
    [
        ("ESP_RZXe", "ESP_RZXe", 0, 8),
        ("ESP_RZXe2", "ESP_RZXe2", 0, 8),
        ("ST8X_WF", "ST8X_WF", 0, 8),
        ("ST8X_WF2", "ST8X_WF2", 0, 8),
        ("ESP_TM2", "ESP_TM2", 3, 0),
        ("ESP_ME", "ESP_ME", 4, 0),
        ("ESP_TM2v3", "ESP_TM2v3", 3, 0),
        ("ESP_ME3", "ESP_ME3", 4, 0),
        ("ESP_2WIRE", "ESP_2WIRE", 4, 0),
        ("RC2", "RC2", 3, 0),
        ("ARC8", "ARC8", 3, 0),
    ],
)
async def test_client_across_common_device_models(
    model_name: str,
    expected_code: str,
    expected_programs: int,
    expected_zone_schedules: int,
) -> None:
    """Verify AsyncRainbirdController end-to-end across LCR, legacy SIP, and Universal CDT controllers."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        mv = await ctrl.get_model_and_version()
        assert mv.model_code == expected_code

        stations = await ctrl.get_available_stations()
        assert len(stations.active_set) > 0

        await ctrl.set_current_time(datetime.time(9, 45, 0))
        assert await ctrl.get_current_time() == datetime.time(9, 45, 0)

        await ctrl.set_current_date(datetime.date(2026, 6, 15))
        assert await ctrl.get_current_date() == datetime.date(2026, 6, 15)

        await ctrl.set_rain_delay(4)
        assert await ctrl.get_rain_delay() == 4

        await ctrl.irrigate_zone(2, 5)
        assert await ctrl.get_zone_state(2) is True
        await ctrl.stop_irrigation()
        assert await ctrl.get_zone_state(2) is False

        sched = await ctrl.get_schedule()
        assert len(sched.programs) == expected_programs
        assert len(sched.zone_schedules) == expected_zone_schedules
        assert (
            list(
                sched.timeline_tz(datetime.UTC).overlapping(
                    datetime.datetime(2026, 6, 15, 0, 0, tzinfo=datetime.UTC),
                    datetime.datetime(2026, 6, 22, 0, 0, tzinfo=datetime.UTC),
                )
            )
            == []
        )

        wifi = await ctrl.get_wifi_params()
        assert wifi.mac_address is not None
        net = await ctrl.get_network_status()
        assert net.network_up is True
        settings = await ctrl.get_settings()
        assert settings.num_programs > 0


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["ESP_RZXe", "ESP_RZXe2", "ST8X_WF", "ST8X_WF2"])
async def test_lcr_zone_schedule_roundtrip(model_name: str) -> None:
    """Verify set_zone_schedule and get_schedule roundtrip on LCR controllers."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        await ctrl.set_zone_schedule(
            zone=1,
            duration=datetime.timedelta(minutes=15),
            starts=[datetime.time(6, 0)],
            frequency=ProgramFrequency.CUSTOM,
            days_of_week={DayOfWeek.MONDAY, DayOfWeek.WEDNESDAY},
        )
        sched = await ctrl.get_schedule()
        assert len(sched.zone_schedules) == 8
        assert sched.zone_schedules[1].duration == datetime.timedelta(minutes=15)
        assert sched.zone_schedules[1].starts == [datetime.time(6, 0)]
        assert sched.zone_schedules[1].days_of_week == {
            DayOfWeek.MONDAY,
            DayOfWeek.WEDNESDAY,
        }


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["ESP_RZXe2", "ST8X_WF2", "ESP_TM2v3"])
async def test_combined_controller_state(model_name: str) -> None:
    """Verify get_combined_controller_state on controllers supporting 0x4C."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        await ctrl.set_rain_delay(4)
        state = await ctrl.get_combined_controller_state()
        assert state.delay_setting == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "minutes"),
    [
        ("ESP_RZXe", 100),
        ("ESP_ME3", 100),
        ("ESP_BAT_BT", 180),
    ],
)
async def test_manual_irrigation_within_model_limit(
    model_name: str, minutes: int
) -> None:
    """Verify irrigate_zone succeeds when duration is within max_manual_run_seconds."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        await ctrl.irrigate_zone(1, minutes)
        assert await ctrl.get_zone_state(1) is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("model_name", "display_name"),
    [
        ("ESP_RZXe", "ESP-RZXe"),
        ("ESP_RZXe2", "ESP-RZXe2"),
        ("ESP_ME", "ESP-Me"),
        ("ESP_ME3", "ESP-ME3"),
    ],
)
async def test_manual_irrigation_exceeding_model_limit_nacks(
    model_name: str, display_name: str
) -> None:
    """Verify irrigate_zone raises RainbirdDeviceNackError locally before sending when exceeding the limit."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        expected_msg = (
            "Manual irrigation duration of 101 minutes exceeds "
            f"the 100-minute limit for {display_name}"
        )
        with pytest.raises(RainbirdDeviceNackError) as exc_info:
            await ctrl.irrigate_zone(1, 101)
        assert str(exc_info.value) == expected_msg
        assert await ctrl.get_zone_state(1) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("model_name", ["ARC8", "RC2"])
@freeze_time("2026-06-15 00:00:00")
async def test_universal_isk_schedule_and_timeline(model_name: str) -> None:
    """Verify ARC8 and RC2 Universal schedule decoding and calendar timeline generation."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model=model_name) as server,
        aiohttp.ClientSession() as session,
    ):
        # Configure 3 programs via Universal CDT batch write (050B):
        # - PGM A (0): Custom (0) on Mon/Wed/Fri, 06:00, Zone 1=10m + Zone 2=15m
        # - PGM B (1): Odd days (1), 07:00, Zone 3=20m
        # - PGM C (2): Off (5), 08:00, Zone 4=30m (saved but disabled)
        starts_hex = struct.pack(
            "<12H",
            360,
            1440,
            1440,
            1440,
            420,
            1440,
            1440,
            1440,
            480,
            1440,
            1440,
            1440,
        ).hex()
        pgm_a_days_hex = bytes([0, 1, 0, 1, 0, 1, 0]).hex()
        runtimes_a_hex = struct.pack("<2I", 600, 900).hex()
        runtimes_b_hex = struct.pack("<I", 1200).hex()
        runtimes_c_hex = struct.pack("<I", 1800).hex()
        write_resp = server.device.handle_sip(
            _cdt_set_packet(
                ("1300", 1, "000105", [(0, 2)]),
                ("1000", 1, pgm_a_days_hex, [(0, 0), (0, 6)]),
                ("1D00", 2, starts_hex, [(0, 2), (0, 0), (0, 3)]),
                ("1500", 4, runtimes_a_hex, [(0, 0), (0, 1)]),
                ("1500", 4, runtimes_b_hex, [(1, 1), (2, 2)]),
                ("1500", 4, runtimes_c_hex, [(2, 2), (3, 3)]),
            )
        )
        assert write_resp.endswith("060B00")

        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        sched = await ctrl.get_schedule()
        assert len(sched.programs) == 3

        pgm_a, pgm_b, pgm_c = sched.programs
        assert pgm_a.frequency == ProgramFrequency.CUSTOM
        assert pgm_a.days_of_week == {
            DayOfWeek.MONDAY,
            DayOfWeek.WEDNESDAY,
            DayOfWeek.FRIDAY,
        }
        assert pgm_a.starts == [datetime.time(6, 0)]
        assert [(d.zone, d.duration) for d in pgm_a.durations] == [
            (1, datetime.timedelta(minutes=10)),
            (2, datetime.timedelta(minutes=15)),
        ]

        assert pgm_b.frequency == ProgramFrequency.ODD
        assert pgm_b.starts == [datetime.time(7, 0)]
        assert [(d.zone, d.duration) for d in pgm_b.durations] == [
            (3, datetime.timedelta(minutes=20)),
        ]

        assert pgm_c.frequency == ProgramFrequency.OFF
        assert pgm_c.starts == [datetime.time(8, 0)]
        assert [(d.zone, d.duration) for d in pgm_c.durations] == [
            (4, datetime.timedelta(minutes=30)),
        ]

        events = list(
            sched.timeline_tz(datetime.UTC).overlapping(
                datetime.datetime(2026, 6, 15, 0, 0, tzinfo=datetime.UTC),
                datetime.datetime(2026, 6, 19, 0, 0, tzinfo=datetime.UTC),
            )
        )
        assert [(e.program_id.name, e.start, e.end) for e in events] == [
            (
                "PGM A",
                datetime.datetime(2026, 6, 15, 6, 0, tzinfo=datetime.UTC),
                datetime.datetime(2026, 6, 15, 6, 25, tzinfo=datetime.UTC),
            ),
            (
                "PGM B",
                datetime.datetime(2026, 6, 15, 7, 0, tzinfo=datetime.UTC),
                datetime.datetime(2026, 6, 15, 7, 20, tzinfo=datetime.UTC),
            ),
            (
                "PGM A",
                datetime.datetime(2026, 6, 17, 6, 0, tzinfo=datetime.UTC),
                datetime.datetime(2026, 6, 17, 6, 25, tzinfo=datetime.UTC),
            ),
            (
                "PGM B",
                datetime.datetime(2026, 6, 17, 7, 0, tzinfo=datetime.UTC),
                datetime.datetime(2026, 6, 17, 7, 20, tzinfo=datetime.UTC),
            ),
        ]


@pytest.mark.asyncio
async def test_universal_multi_chunk_station_schedule_esp_2wire() -> None:
    """Verify Universal schedule retrieval preserves runtimes across >25-station chunks."""
    async with (
        RainbirdFakeServer(password=PASSWORD, model="ESP_2WIRE") as server,
        aiohttp.ClientSession() as session,
    ):
        write_resp = server.device.handle_sip(
            _cdt_set_packet(
                ("1300", 1, "04030505", [(0, 3)]),
                ("1200", 1, "03", [(0, 0)]),
                ("1100", 1, "01", [(0, 0)]),
                ("1D00", 2, struct.pack("<H", 330).hex(), [(0, 0), (0, 0), (0, 0)]),
                ("1D00", 2, struct.pack("<H", 390).hex(), [(1, 1), (0, 0), (0, 0)]),
                ("1500", 4, struct.pack("<I", 720).hex(), [(0, 0), (0, 0)]),
                ("1500", 4, struct.pack("<I", 1080).hex(), [(0, 0), (29, 29)]),
                ("1500", 4, struct.pack("<I", 600).hex(), [(1, 1), (49, 49)]),
            )
        )
        assert write_resp.endswith("060B00")

        ctrl = await async_client.create_controller(session, server.host_port, PASSWORD)
        sched = await ctrl.get_schedule()
        assert len(sched.programs) == 4
        assert sched.programs[0].frequency == ProgramFrequency.CYCLIC
        assert sched.programs[0].period == 3
        assert sched.programs[0].synchro == 1
        assert [(d.zone, d.duration) for d in sched.programs[0].durations] == [
            (1, datetime.timedelta(minutes=12)),
            (30, datetime.timedelta(minutes=18)),
        ]
        assert sched.programs[1].frequency == ProgramFrequency.EVEN
        assert [(d.zone, d.duration) for d in sched.programs[1].durations] == [
            (50, datetime.timedelta(minutes=10)),
        ]
        assert sched.programs[2].frequency == ProgramFrequency.OFF
        assert sched.programs[3].frequency == ProgramFrequency.OFF
