"""Sensors: what is on the bar, and the BUSY timer."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import APPS_MENU, OFF_APP, TIMER_APP
from .coordinator import BusyBarConfigEntry, BusyBarCoordinator
from .entity import BusyBarEntity
from .timer import IDLE, PAUSED, RUNNING


async def async_setup_entry(
    hass: HomeAssistant, entry: BusyBarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
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
