"""State dataclasses and initialization helpers for Rain Bird device emulators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class LCRZoneSchedule:
    """Per-zone schedule entry for LCR controllers (ESP_RZXe, ST8X_WF)."""

    run_time_minutes: int = 0
    start_times_minutes: list[int] = field(
        default_factory=lambda: [1440, 1440, 1440, 1440, 1440, 1440]
    )
    frequency_type: int = 0
    custom_days_mask: int = 0x7F
    cyclic_days: int = 1
    sensor_enabled: bool = True
    days_remaining: int = 0


@dataclass
class ProgramScheduleConfig:
    """Per-program schedule configuration for program-centric SIP and BLE controllers."""

    custom_days_mask: int = 0
    cyclic_days: int = 0
    days_remaining: int = 0
    permanent_days_off: int = 0
    seasonal_adjust: int = 100
    water_cycle: int = 0
    auto_restart: bool = False
    start_times_minutes: list[int] = field(default_factory=lambda: [65535] * 8)


def init_core_state(device: Any) -> None:
    """Initialize core SIP clock, sensor, budget, and runtime queue state."""
    max_stns = device.profile.maximum_stations
    device.fw_major = 1
    device.fw_minor = 8
    device.fw_build = 0
    device.fw_submodules = []
    device.serial_number_hex = "0000000012345678"
    device.hour = 12
    device.minute = 0
    device.second = 0
    device.year = 2026
    device.month = 1
    device.day = 1
    device.posix_timezone = "UTC0"
    device.prevent_sntp_updates = False
    device.installed_stations_count = max_stns
    device.available_stations = set(range(1, max_stns + 1))
    device.available_stations_page_overrides = {}
    device.supported_commands = None
    device.sensor_state = 0
    device.rain_sensor_bypassed = False
    device.master_valve_enable = False
    device.rain_settling_time_minutes = 0
    device.inter_station_delay_seconds = 0
    device.rain_delay_days = 0
    device.controller_state = 1
    device.controller_state_str = "Auto"
    device.seasonal_adjust = 100
    device.water_budget = {i: 100 for i in range(12)}
    device.monthly_water_budget = {i: 100 for i in range(12)}
    device.zone_count = max(8, max_stns)
    device.event_timestamps = {1: 0}
    device.active_station = 0
    device.active_program = 0xFF
    device.remaining_runtime_sec = 0
    device.paused = False
    device.manual_queue_count = 0
    device.auto_queue_count = 0
    device.status_flags = 0
    device.mv_on_byte = 0
    device.queue = []
    device.queued_entries = []
    device.program_0_stations = []
    device.short_mask_by_page = {0: 0, 1: 0}
    device.open_mask_by_page = {0: 0, 1: 0}
    device.stats_page0 = {1: {"programmed": 0, "applied": 0}}
    device.stats_monthly = {}


def init_schedule_state(device: Any) -> None:
    """Initialize schedule storage for LCR and program-centric SIP controllers."""
    max_stns = device.profile.maximum_stations
    device.lcr_zones = {z: LCRZoneSchedule() for z in range(1, 9)}
    device.zone_seasonal_adjust = [100] * 8
    device.programs = {p: ProgramScheduleConfig() for p in range(1, 13)}
    device.station_run_times = {
        s: [0] * max(4, device.profile.maximum_programs)
        for s in range(1, max(24, max_stns) + 1)
    }
    device.page_run_times_sec = {}
    device.station_rain_sensor_obey = [True] * max(12, max_stns)
    device.station_mv_enable = [False] * max(12, max_stns)
    device.station_cycle_soak = [
        {"soak_seconds": 0, "cycle_seconds": 0} for _ in range(max(6, max_stns))
    ]
    device.calendar_days_off = [None] * 15


def init_ble_state(device: Any) -> None:
    """Initialize BLE battery, OTA, flow learn, and Solem state."""
    device.raster_test_run = False
    device.is_pin_set = False
    device.is_pin_corrected = True
    device.pin_code = ""
    device.transition_is_processing = False
    device.gatt_notifications_enabled = True
    device.battery_voltage_mv = 9000
    device.battery_source_type = "01"
    device.ble_snr = 10
    device.ble_rssi = -65
    device.lora_snr = 0
    device.lora_rssi = 0
    device.ota_active = False
    device.ota_last_fragment = 0
    device.ota_total_fragments = 0
    device.flow_learn_active = False
    device.flow_learn_state = 0
    device.learning_stations_mask = "00000000"
    device.flow_monitor_enabled = False
    device.current_flow_rate_milli = 0
    device.solem_authenticated = False
    device.solem_install_code = "01020304"


def init_universal_state(device: Any) -> None:
    """Initialize Universal CDT and subsystem state."""
    device.cdt_store = {}
    device.cdt_1500 = {}
    device.cdt_1d00 = {}
    device.uni_irrigation_queue = []
    device.flow_stations_learned = []
    device.mv_manual_open_duration_minutes = 0
    device.mv_open_status = False
    device.current_flow_rates_gpm = []
    device.flow_totalizer = {
        "current_month": 0,
        "previous_month": 0,
        "last_30_days": 0,
        "previous_30_days": 0,
    }
    device.front_panel_locked = False
    device.session_id = "A1A2A3A4A5A6A7A8"
    device.uni_raster_test = {
        "active": False,
        "progress": 100,
        "open_stations": [],
        "shorted_stations": [],
    }
    device.ping_polling_target = None
    device.last_ping = {
        "ready": True,
        "device_number": 1,
        "device_type": 1,
        "address": 1001,
        "status": True,
        "voltage": 28.5,
    }
    device.weather_sensor_status = ["Monitoring"]
    device.discovery = {
        "status": "DISCOVERY_COMPLETED",
        "percent_complete": 100,
        "devices": [],
    }
    device.segment_info = {
        "diagnostic_mode": 0,
        "shorted_map": 0,
        "test_path": 0,
        "current": 0,
    }
    device.ac_current_test = {"path": 0, "source_on": False}
    device.not_responding = {
        "weather": [],
        "flow": [],
        "mv": [],
        "pump": [],
        "stations": [],
    }
    device.alarms = []
    device.module_info_address = "0100"
    device.line_survey = {
        "peak_voltage_v": 28,
        "current_ma": 45,
        "limit_threshold_ma": 800,
    }


def init_stick_state(device: Any, password: str | None = None) -> None:
    """Initialize LNK2 WiFi Stick transport and JSON-RPC state."""
    device.password = password
    device.encryption_required = bool(password)
    device.request_encrypted = True
    device.lockout_active = False
    device.lockout_tries = 5
    device.lockout_timeout = 5
    device.failed_attempts = 0
    device.mac_address = "D8:B6:73:01:02:03"
    device.local_ip_address = "192.168.1.50"
    device.local_netmask = "255.255.255.0"
    device.local_gateway = "192.168.1.1"
    device.wifi_rssi = -55
    device.wifi_ssid = "HomeNetwork"
    device.wifi_password = "secret"
    device.wifi_security = "wpa2"
    device.ap_timeout_no_lan = 1800
    device.ap_timeout_idle = 1800
    device.ap_security = "none"
    device.stick_id = "RB4455667788"
    device.stick_version = "2.9"
    device.visible_aps = []
    device.network_up = True
    device.internet_up = True
    device.server_check_in_rsp = True
    device.server_open_socket = True
    device.ap_mode = False
    device.server_mode = True
    device.check_in_interval = 60
    device.server_url = "https://api.rainbird.com"
    device.missed_check_ins = 0
    device.relay_timeout = 30
    device.country = "US"
    device.zip_code = "92121"
    device.global_disable = False
    device.num_programs = max(1, device.profile.maximum_programs or 4)
    device.program_opt_out_mask = "0000000000000000"
    device.soil_types = [0] * 8
    device.flow_rates = [0] * 8
    device.flow_units = [0] * 8
    device.auto_queue = []
    device.manual_rpc_queue = []
    device.auto_queue_interval = 0
    device.update_status = 0
    device.lnk_progress = 0
    device.unv_progress = 0
    device.reboot_scheduled = False
    device.last_uart_tx_frame_hex = ""
