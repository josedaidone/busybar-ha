"""
What the BUSY timer is doing, from a /api/busy/snapshot.

A snapshot is frozen at `snapshot_timestamp_ms`: the time left has to be
advanced to now (a ported, trimmed busylib.features.timer.timer_state).
"""

from __future__ import annotations

import time
from dataclasses import dataclass

IDLE = "idle"
RUNNING = "running"
PAUSED = "paused"


@dataclass(frozen=True)
class TimerState:
    state: str  # idle, running, paused
    mode: str  # not_started, infinite, simple, interval
    time_left_ms: int | None = None
    phase: str | None = None  # work / rest (interval timers)

    @property
    def active(self) -> bool:
        """A session under way, paused or not."""
        return self.state != IDLE


def timer_state(snap: dict, now_ms: int | None = None) -> TimerState:
    now = int(time.time() * 1000) if now_ms is None else now_ms
    inner = snap.get("snapshot") or {}
    kind = inner.get("type", "NOT_STARTED")
    stamp = snap.get("snapshot_timestamp_ms")
    elapsed = 0 if stamp is None else max(0, now - int(stamp))
    paused = bool(inner.get("is_paused"))

    if kind == "INFINITE":
        return TimerState(PAUSED if paused else RUNNING, "infinite", phase="work")

    if kind == "SIMPLE":
        left = int(inner.get("time_left_ms") or 0)
        if paused:
            return TimerState(PAUSED, "simple", left)
        left -= elapsed
        return TimerState(RUNNING, "simple", left) if left > 0 else TimerState(IDLE, "simple", 0)

    if kind == "INTERVAL":
        settings = inner.get("interval_settings") or {}
        interval = int(inner.get("current_interval") or 0)
        left = int(inner.get("current_interval_time_left_ms") or 0)
        phase = "work" if interval % 2 == 0 else "rest"
        if paused:
            return TimerState(PAUSED, "interval", left, phase)
        work = int(settings.get("interval_work_ms") or 0)
        rest = int(settings.get("interval_rest_ms") or 0)
        last = int(settings.get("interval_work_cycles_count") or 1) * 2 - 1  # the index a session ends at
        left -= elapsed
        while left <= 0:
            interval += 1
            if interval >= last:
                return TimerState(IDLE, "interval", 0)
            duration = work if interval % 2 == 0 else rest
            if duration <= 0:
                break
            left += duration
        return TimerState(RUNNING, "interval", max(0, left), "work" if interval % 2 == 0 else "rest")

    return TimerState(IDLE, "not_started")
