"""Tests for the timer snapshot reading."""

from custom_components.busybar_apps.timer import timer_state


def test_not_started():
    assert timer_state({"snapshot": {"type": "NOT_STARTED"}, "snapshot_timestamp_ms": 0}, 1000).state == "idle"


def test_simple_runs_then_ends():
    snap = {"snapshot": {"type": "SIMPLE", "time_left_ms": 9000, "is_paused": False}, "snapshot_timestamp_ms": 0}
    assert timer_state(snap, 1000).state == "running"
    assert timer_state(snap, 1000).time_left_ms == 8000
    assert timer_state(snap, 9000).state == "idle"


def test_simple_paused_stays():
    snap = {"snapshot": {"type": "SIMPLE", "time_left_ms": 9000, "is_paused": True}, "snapshot_timestamp_ms": 0}
    assert timer_state(snap, 10**9).state == "paused"


def test_interval_walks_phases_and_ends():
    settings = {"interval_work_ms": 1000, "interval_rest_ms": 500, "interval_work_cycles_count": 2}
    snap = {
        "snapshot": {
            "type": "INTERVAL",
            "current_interval": 0,
            "current_interval_time_total_ms": 1000,
            "current_interval_time_left_ms": 1000,
            "is_paused": False,
            "interval_settings": settings,
        },
        "snapshot_timestamp_ms": 0,
    }
    assert timer_state(snap, 500).phase == "work"
    assert timer_state(snap, 1200).phase == "rest"
    assert timer_state(snap, 1600).phase == "work"
    assert timer_state(snap, 2600).state == "idle"  # work, rest, work: done


def test_infinite():
    snap = {"snapshot": {"type": "INFINITE", "is_paused": False}, "snapshot_timestamp_ms": 0}
    assert timer_state(snap, 10**9).state == "running"
