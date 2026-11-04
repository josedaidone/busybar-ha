"""Sensors: what is on the bar and the BUSY timer; for buZyist, what it is doing."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .buzyist import BuzyistHub
from .const import APPS_MENU, BUZYIST_STATES, CONF_KIND, KIND_BUZYIST, OFF_APP, TIMER_APP
from .coordinator import BusyBarCoordinator
from .entity import BusyBarEntity, BuzyistEntity
from .timer import IDLE, PAUSED, RUNNING


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    if entry.data.get(CONF_KIND) == KIND_BUZYIST:
        hub = entry.runtime_data
        async_add_entities(
            [
                BuzyistStateSensor(hub),
                BuzyistActivitySensor(hub),
                BuzyistTaskSensor(hub),
                BuzyistPhaseEndSensor(hub),
                BuzyistTodaySensor(hub, "pomodoros_today", "pomodoros"),
                BuzyistTodaySensor(hub, "focus_today", "minutes"),
            ]
        )
        return
    coordinator = entry.runtime_data
    async_add_entities([RunningAppSensor(coordinator), TimerSensor(coordinator)])


class RunningAppSensor(BusyBarEntity, SensorEntity):
    """The app on the bar: "Off", "Apps menu", "Timer" or the app's name."""

    _attr_icon = "mdi:application-outline"

    def __init__(self, coordinator: BusyBarCoordinator) -> None:
        super().__init__(coordinator, "running_app")

    @property
    def native_value(self) -> str:
        data = self.coordinator.data
        name = data.running_name
        if name == OFF_APP:
            return "Off"
        if name == APPS_MENU:
            return "Apps menu"
        if name == TIMER_APP:
            return "Timer"
        return self.coordinator.label(data.running_value) if data.running_value else name

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {
            "value": data.running_value,
            "raw_name": data.running_name,
            "runtime": data.running.get("runtime", ""),
            "app_id": data.running.get("app_id", ""),
            "is_off": data.is_off,
            "is_idle": data.is_idle,
        }


class TimerSensor(BusyBarEntity, SensorEntity):
    """The BUSY timer: idle, running or paused."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [IDLE, RUNNING, PAUSED]
    _attr_icon = "mdi:timer-outline"

    def __init__(self, coordinator: BusyBarCoordinator) -> None:
        super().__init__(coordinator, "timer")

    @property
    def native_value(self) -> str:
        return self.coordinator.data.timer.state

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        timer = self.coordinator.data.timer
        left = timer.time_left_ms
        return {
            "mode": timer.mode,
            "phase": timer.phase,
            "time_left_s": None if left is None else round(left / 1000),
        }


# ------------------------------------------------------------------ buZyist


class BuzyistStateSensor(BuzyistEntity, SensorEntity):
    """What buZyist is doing: idle, focus, break, paused or call; the session's details as attributes."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = BUZYIST_STATES
    _attr_icon = "mdi:timer-sand"

    def __init__(self, hub: BuzyistHub) -> None:
        super().__init__(hub, "state")

    @property
    def native_value(self) -> str | None:
        state = self.hub.data.get("state")
        return state if state in BUZYIST_STATES else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        session = self.hub.session
        activity = session.get("activity") or {}
        return {
            "kind": session.get("kind"),
            "source": session.get("source"),
            "task": session.get("task"),
            "activity": activity.get("name"),
            "activity_id": activity.get("id"),
            "round": session.get("round"),
            "rounds": session.get("rounds"),
            "phase_minutes": session.get("phase_minutes"),
            "started_at": session.get("started_at"),
            "apps": session.get("apps") or [],
            "device": self.hub.data.get("device"),
            "version": self.hub.data.get("version"),
        }


class BuzyistActivitySensor(BuzyistEntity, SensorEntity):
    """The session's activity (Email, Call, ...); unknown with none or nothing running."""

    _attr_icon = "mdi:shape-outline"

    def __init__(self, hub: BuzyistHub) -> None:
        super().__init__(hub, "activity")

    @property
    def native_value(self) -> str | None:
        return (self.hub.session.get("activity") or {}).get("name") or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        activity = self.hub.session.get("activity") or {}
        return {"activity_id": activity.get("id"), "detail": activity.get("detail")}


class BuzyistTaskSensor(BuzyistEntity, SensorEntity):
    """What the session is on: the Todoist task or the name typed in."""

    _attr_icon = "mdi:checkbox-marked-circle-outline"

    def __init__(self, hub: BuzyistHub) -> None:
        super().__init__(hub, "task")

    @property
    def native_value(self) -> str | None:
        return (self.hub.session.get("task") or "")[:255] or None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"task_id": self.hub.session.get("task_id") or None, "project": self.hub.session.get("project") or None}


class BuzyistPhaseEndSensor(BuzyistEntity, SensorEntity):
    """When the work phase or break running now ends; unknown while paused, on a call or idle."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:timer-alert-outline"

    def __init__(self, hub: BuzyistHub) -> None:
        super().__init__(hub, "phase_end")

    @property
    def native_value(self) -> datetime | None:
        ends = self.hub.session.get("ends_at")
        return dt_util.parse_datetime(ends) if isinstance(ends, str) else None


class BuzyistTodaySensor(BuzyistEntity, SensorEntity):
    """Today's pomodoros, or focus minutes, as buZyist counts them (back to 0 at midnight)."""

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def __init__(self, hub: BuzyistHub, key: str, field: str) -> None:
        super().__init__(hub, key)
        self._field = field
        if field == "minutes":
            self._attr_device_class = SensorDeviceClass.DURATION
            self._attr_native_unit_of_measurement = UnitOfTime.MINUTES
            self._attr_icon = "mdi:brain"
        else:
            self._attr_icon = "mdi:timer-check-outline"

    @property
    def native_value(self) -> int | None:
        value = (self.hub.data.get("today") or {}).get(self._field)
        return value if isinstance(value, int) else None
