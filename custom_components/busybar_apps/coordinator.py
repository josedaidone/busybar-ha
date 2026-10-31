"""Polls the bar, and opens / closes apps on it."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import BarApp, BusyBarApi, BusyBarAuthError, BusyBarError, parse_value, running_value
from .const import (
    APPS_MENU,
    APPS_REFRESH_S,
    DEFAULT_AUTO_APP,
    DOMAIN,
    IDLE_APPS,
    KEY_SETTLE_S,
    LAUNCH_SETTLE_S,
    OFF_APP,
    SCAN_INTERVAL,
    TIMER_APP,
)
from .timer import TimerState, timer_state

_LOGGER = logging.getLogger(__name__)


@dataclass
class BarData:
    running: dict
    running_value: str
    timer: TimerState
    apps: list[BarApp] = field(default_factory=list)

    @property
    def running_name(self) -> str:
        return self.running.get("name", "")

    @property
    def is_off(self) -> bool:
        return self.running_name == OFF_APP

    @property
    def is_idle(self) -> bool:
        """Off or on the Apps list, with no timer: nothing of the user's on the bar."""
        return self.running_name in IDLE_APPS and not self.timer.active


type BusyBarConfigEntry = ConfigEntry[BusyBarCoordinator]


class BusyBarCoordinator(DataUpdateCoordinator[BarData]):
    """One bar: its state every few seconds, its app list every few minutes."""

    config_entry: BusyBarConfigEntry

    def __init__(self, hass: HomeAssistant, entry: BusyBarConfigEntry, api: BusyBarApi) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL)
        self.api = api
        self._system: list[dict] = []
        self._apps: list[BarApp] = []
        self._apps_at = 0.0
        self._lock = asyncio.Lock()  # one launch / power off at a time
        self.auto_app = DEFAULT_AUTO_APP  # what launch_app opens when given no app (the "Auto app" select)

    @property
    def apps(self) -> list[BarApp]:
        return self._apps

    async def refresh_apps(self) -> None:
        self._system = await self.api.system_apps()
        self._apps = await self.api.apps(self._system)
        self._apps_at = time.monotonic()

    async def _async_update_data(self) -> BarData:
        try:
            if not self._apps_at or time.monotonic() - self._apps_at > APPS_REFRESH_S:
                await self.refresh_apps()
            running = await self.api.running()
            snap = await self.api.snapshot()
        except BusyBarAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except BusyBarError as err:
            raise UpdateFailed(str(err)) from err
        return BarData(running, running_value(running, self._system), timer_state(snap), self._apps)

    # Names <-> values

    def choices(self) -> dict[str, str]:
        """{label: value} of the apps, labels made unique (two apps of one name get their runtime)."""
        counts: dict[str, int] = {}
        for app in self._apps:
            counts[app.name] = counts.get(app.name, 0) + 1
        return {(a.name if counts[a.name] == 1 else f"{a.name} ({a.runtime})"): a.value for a in self._apps}

    def label(self, value: str) -> str:
        for label, known in self.choices().items():
            if known == value:
                return label
        return value.partition(":")[2].rsplit("/", 1)[-1].removesuffix(".fap") or value

    def resolve(self, app: str) -> tuple[str, str]:
        """(runtime, app_id) of an app given by "runtime:id" or by its name (case-insensitive)."""
        app = app.strip()
        if app in (choices := self.choices()):
            return parse_value(choices[app])
        for known in self._apps:
            if app in (known.value, known.name) or app.casefold() == known.name.casefold():
                return known.runtime, known.app_id
        try:
            return parse_value(app)
        except ValueError as err:
            names = ", ".join(a.name for a in self._apps)
            raise HomeAssistantError(f"Unknown BUSY Bar app {app!r}. Known: {names}") from err

    # Actions

    async def _now(self) -> BarData:
        await self.async_refresh()
        if not self.last_update_success or self.data is None:
            raise HomeAssistantError(f"BUSY Bar unreachable: {self.last_exception}")
        return self.data

    async def launch(self, app: str, only_if_idle: bool = False) -> bool:
        """
        Open `app` and start it (OK, pressed only on an app just opened: on a
        running one it does something else). With `only_if_idle`, only when
        the bar is off or on the Apps list and no timer runs. True when the
        app is on the bar afterwards.
        """
        runtime, app_id = self.resolve(app)
        value = f"{runtime}:{app_id}"
        async with self._lock:
            data = await self._now()
            if only_if_idle and not data.is_idle:
                _LOGGER.debug("not opening %s: the bar shows %s, timer %s", value, data.running_name, data.timer.state)
                return False
            if data.running_value == value:
                return True
            try:
                await self.api.launch(runtime, app_id)
                await asyncio.sleep(LAUNCH_SETTLE_S)
                opened = await self.api.running()
                if opened.get("name") in ("", APPS_MENU, TIMER_APP, OFF_APP) or (
                    runtime != "system" and opened.get("app_id") != app_id
                ):
                    _LOGGER.warning("BUSY Bar: %s didn't open (the bar shows %s)", value, opened.get("name"))
                    return False
                await self.api.press("ok")
            except BusyBarError as err:
                raise HomeAssistantError(f"BUSY Bar: couldn't open {value}: {err}") from err
            finally:
                await self.async_request_refresh()
            _LOGGER.info("BUSY Bar: opened %s", value)
            return True

    async def power_off(self, respect_timer: bool = True) -> bool:
        """Turn the bar off (Apps then Off on the mode switch). With `respect_timer`, not while a timer runs."""
        async with self._lock:
            data = await self._now()
            if data.is_off:
                return True
            if respect_timer and data.timer.active:
                _LOGGER.debug("not turning off: timer %s", data.timer.state)
                return False
            try:
                await self.api.press("apps")
                await asyncio.sleep(KEY_SETTLE_S)
                await self.api.press("off")
            except BusyBarError as err:
                raise HomeAssistantError(f"BUSY Bar: couldn't turn off: {err}") from err
            finally:
                await self.async_request_refresh()
            return True
