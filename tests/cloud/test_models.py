"""Unit tests for Rain Bird cloud integration data models."""

import datetime
import pytest

from pyrainbird.cloud.models import (
    DeviceStateRecord,
    StationStateData,
    ConnectedData,
)


def test_device_state_record_updated_at_success() -> None:
    """Test updated_at conversion with a valid timestamp."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="test-sk",
        data="{}",
        timestamp=1686700000,
    )
    expected = datetime.datetime.fromtimestamp(1686700000, datetime.timezone.utc)
    assert record.updated_at == expected


def test_device_state_record_updated_at_fallback_ose_overflow_exceptions() -> None:
    """Test updated_at fallback behavior when timestamp parsing raises OSError or OverflowError."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="test-sk",
        data="{}",
        timestamp=2**60,  # Huge value to trigger OSError/OverflowError
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    updated_at = record.updated_at
    # Ensure it fallback-generated a time close to now (within 5 seconds)
    assert abs((updated_at - now).total_seconds()) < 5


def test_device_state_record_updated_at_fallback_value_error_nan() -> None:
    """Test updated_at fallback behavior when timestamp parsing raises ValueError via NaN."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="test-sk",
        data="{}",
        timestamp=float(
            "nan"
        ),  # NaN triggers ValueError: cannot convert float NaN to integer
    )
    now = datetime.datetime.now(datetime.timezone.utc)
    updated_at = record.updated_at
    assert abs((updated_at - now).total_seconds()) < 5


def test_station_state_data_parse_record_success() -> None:
    """Test parsing a valid station state record."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Station1",
        data='{"state": 1, "remainSec": 30, "programNumber": 2}',
        timestamp=1686700000,
    )
    parsed = StationStateData.parse_record(record)
    assert parsed.state == 1
    assert parsed.remain_sec == 30
    assert parsed.program_number == 2
    assert parsed.is_watering is True


def test_station_state_data_parse_record_no_data_error() -> None:
    """Test StationStateData.parse_record raises ValueError when record data is missing."""
    record = DeviceStateRecord(
        pk="test-pk", sk="Station1", data=None, timestamp=1686700000
    )
    with pytest.raises(ValueError, match="No data found in record"):
        StationStateData.parse_record(record)


def test_station_state_data_parse_record_malformed_json_error() -> None:
    """Test StationStateData.parse_record raises ValueError when record data is malformed JSON."""
    record = DeviceStateRecord(
        pk="test-pk", sk="Station1", data="{invalid_json", timestamp=1686700000
    )
    with pytest.raises(ValueError, match="Failed to parse record data"):
        StationStateData.parse_record(record)


def test_station_state_data_parse_record_epoch_calculation() -> None:
    """Test relative offset subtraction for remain_sec when it holds a unix epoch timestamp."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Station1",
        data='{"state": 1, "remainSec": 1686700050, "programNumber": 2}',
        timestamp=1686700000,
    )
    parsed = StationStateData.parse_record(record)
    assert parsed.remain_sec == 50  # 1686700050 - 1686700000 = 50


def test_connected_data_parse_record_success() -> None:
    """Test parsing a valid connected state record."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Connected",
        data='{"state": "online", "activeStation": 3, "remainSec": 45, "rainDelay": 0}',
        timestamp=1686700000,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.state == "online"
    assert parsed.active_station == 3
    assert parsed.remain_sec == 45
    assert parsed.rain_delay == 0
    assert parsed.is_connected is True


def test_connected_data_parse_record_scalar_offline() -> None:
    """Test parsing a scalar string connected state record."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Connected",
        data='"offline"',
        timestamp=1686700000,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.state == "offline"
    assert parsed.is_connected is False


def test_connected_data_parse_record_scalar_zero() -> None:
    """Test parsing a scalar integer connected state record."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Connected",
        data="0",
        timestamp=1686700000,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.state == 0
    assert parsed.is_connected is False


def test_connected_data_parse_record_no_data_error() -> None:
    """Test ConnectedData.parse_record raises ValueError when record data is missing."""
    record = DeviceStateRecord(
        pk="test-pk", sk="Connected", data=None, timestamp=1686700000
    )
    with pytest.raises(ValueError, match="No data found in record"):
        ConnectedData.parse_record(record)


def test_connected_data_parse_record_malformed_json_error() -> None:
    """Test ConnectedData.parse_record raises ValueError when record data is malformed JSON."""
    record = DeviceStateRecord(
        pk="test-pk", sk="Connected", data="{invalid_json", timestamp=1686700000
    )
    with pytest.raises(ValueError, match="Failed to parse record data"):
        ConnectedData.parse_record(record)


def test_connected_data_parse_record_epoch_calculation_standard() -> None:
    """Test relative offset subtraction for ConnectedData.remain_sec under normal conditions."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Connected",
        data='{"state": "online", "remainSec": 1686700080}',
        timestamp=1686700000,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.remain_sec == 80  # 1686700080 - 1686700000 = 80


def test_connected_data_parse_record_epoch_calculation_no_timestamp() -> None:
    """Test that relative offset subtraction is skipped when timestamp is missing."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Connected",
        data='{"state": "online", "remainSec": 1686700080}',
        timestamp=None,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.remain_sec == 1686700080


def test_connected_data_parse_record_epoch_calculation_below_threshold() -> None:
    """Test that relative offset subtraction is skipped when remainSec is below the threshold."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Connected",
        data='{"state": "online", "remainSec": 500}',
        timestamp=1686700000,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.remain_sec == 500


def test_connected_data_parse_record_epoch_calculation_remain_less_than_timestamp() -> (
    None
):
    """Test that offset subtraction is skipped when remainSec is less than the timestamp."""
    record = DeviceStateRecord(
        pk="test-pk",
        sk="Connected",
        data='{"state": "online", "remainSec": 1686700080}',
        timestamp=1686700100,
    )
    parsed = ConnectedData.parse_record(record)
    assert parsed.remain_sec == 1686700080
