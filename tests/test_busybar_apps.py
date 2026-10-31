"""Tests for BUSY Bar Apps, against a fake bar that behaves like VeryBUSY r12."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.busybar_apps.api import BarApp, BusyBarAuthError
from custom_components.busybar_apps.const import DOMAIN

SYSTEM = [
    {"name": "Busy", "appid": "busy", "group": "apps", "blocked": False},
    {"name": "Clock", "appid": "clock", "group": "apps", "blocked": False},
    {"name": "Software Power Off", "appid": "soft_off", "group": "system", "blocked": False},
    {"name": "AppsMenu", "appid": "apps_menu", "group": "system", "blocked": False},
]
APPS = [
    BarApp("system", "clock", "Clock"),
    BarApp("fap", "/ext/apps/misc/Nixie.fap", "Nixie"),
    BarApp("js", "app.busy.weather", "Weather"),
]
OFF = {"name": "Software Power Off", "runtime": "", "app_id": "", "js_id": ""}
MENU = {"name": "AppsMenu", "runtime": "", "app_id": "", "js_id": ""}
NOT_STARTED = {"snapshot": {"type": "NOT_STARTED"}, "snapshot_timestamp_ms": 0}


def infinite(paused: bool = False) -> dict:
    return {"snapshot": {"type": "INFINITE", "card_id": "x", "is_paused": paused}, "snapshot_timestamp_ms": 0}


class FakeBar:
    """Remembers the presses; apps open like on the real bar."""

    password_ok = True

    def __init__(self, session, host, password) -> None:
        self.password = password

    state = {"running": OFF, "snap": NOT_STARTED, "calls": []}

    def _auth(self):
        if not FakeBar.password_ok:
            raise BusyBarAuthError("403")

    async def status(self):
        self._auth()
        return {"device": {"serial_number": "SERIAL1"}}

    async def name(self):
        return "BUSY Bar"

    async def running(self):
        self._auth()
        return FakeBar.state["running"]

    async def snapshot(self):
        return FakeBar.state["snap"]

    async def system_apps(self):
        return SYSTEM

    async def apps(self, system=None):
        return APPS

    async def launch(self, runtime, app_id):
        FakeBar.state["calls"].append(("launch", runtime, app_id))
        if runtime == "system":
            name = next(a["name"] for a in SYSTEM if a["appid"] == app_id)
            FakeBar.state["running"] = {"name": name, "runtime": "", "app_id": "", "js_id": ""}
        else:
            FakeBar.state["running"] = {"name": app_id, "runtime": runtime, "app_id": app_id, "js_id": ""}

    async def press(self, key):
        FakeBar.state["calls"].append(("press", key))
        if key == "apps":
            FakeBar.state["running"] = MENU
        elif key == "off" and FakeBar.state["running"] == MENU:
            FakeBar.state["running"] = OFF


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture(autouse=True)
def fake_bar():
    FakeBar.password_ok = True
    FakeBar.state = {"running": OFF, "snap": NOT_STARTED, "calls": []}
    with (
        patch("custom_components.busybar_apps.BusyBarApi", FakeBar),
        patch("custom_components.busybar_apps.config_flow.BusyBarApi", FakeBar),
        patch("custom_components.busybar_apps.coordinator.LAUNCH_SETTLE_S", 0),
        patch("custom_components.busybar_apps.coordinator.KEY_SETTLE_S", 0),
    ):
        yield FakeBar


async def setup(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, unique_id="SERIAL1", data={"host": "1.2.3.4", "password": "1234"})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_config_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    FakeBar.password_ok = False
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": "1.2.3.4", "password": "1"})
    assert result["errors"] == {"base": "invalid_auth"}
    FakeBar.password_ok = True
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"host": "1.2.3.4", "password": "1234"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == "SERIAL1"


async def test_entities(hass: HomeAssistant) -> None:
    await setup(hass)
    assert hass.states.get("sensor.busy_bar_running_app").state == "Off"
    assert hass.states.get("sensor.busy_bar_timer").state == "idle"
    auto = hass.states.get("select.busy_bar_auto_app")
    assert auto.state == "Clock"
    assert auto.attributes["options"] == ["Clock", "Nixie", "Weather"]
    assert hass.states.get("select.busy_bar_app").state == "unknown"
    assert hass.states.get("button.busy_bar_power_off")


async def test_launch_when_off_opens_and_starts(hass: HomeAssistant) -> None:
    await setup(hass)
    await hass.services.async_call(
        "select", "select_option", {"entity_id": "select.busy_bar_auto_app", "option": "Nixie"}, blocking=True
    )
    resp = await hass.services.async_call(DOMAIN, "launch_app", {"only_if_idle": True}, blocking=True, return_response=True)
    assert resp == {"opened": True, "app": "fap:/ext/apps/misc/Nixie.fap"}
    assert FakeBar.state["calls"] == [("launch", "fap", "/ext/apps/misc/Nixie.fap"), ("press", "ok")]
    await hass.async_block_till_done()
    assert hass.states.get("sensor.busy_bar_running_app").state == "Nixie"
    assert hass.states.get("select.busy_bar_app").state == "Nixie"


async def test_launch_from_apps_menu(hass: HomeAssistant) -> None:
    FakeBar.state["running"] = MENU
    await setup(hass)
    resp = await hass.services.async_call(
        DOMAIN, "launch_app", {"app": "clock", "only_if_idle": True}, blocking=True, return_response=True
    )
    assert resp["opened"] is True
    assert FakeBar.state["calls"] == [("launch", "system", "clock"), ("press", "ok")]


async def test_launch_leaves_another_app_alone(hass: HomeAssistant) -> None:
    FakeBar.state["running"] = {"name": "JsAppLauncher", "runtime": "js", "app_id": "app.busy.weather", "js_id": ""}
    await setup(hass)
    resp = await hass.services.async_call(DOMAIN, "launch_app", {"only_if_idle": True}, blocking=True, return_response=True)
    assert resp["opened"] is False
    assert FakeBar.state["calls"] == []


@pytest.mark.parametrize("paused", [False, True])
async def test_launch_respects_timer(hass: HomeAssistant, paused: bool) -> None:
    FakeBar.state["running"] = MENU
    FakeBar.state["snap"] = infinite(paused)
    await setup(hass)
    assert hass.states.get("sensor.busy_bar_timer").state == ("paused" if paused else "running")
    resp = await hass.services.async_call(DOMAIN, "launch_app", {"only_if_idle": True}, blocking=True, return_response=True)
    assert resp["opened"] is False
    assert FakeBar.state["calls"] == []


async def test_launch_same_app_no_ok(hass: HomeAssistant) -> None:
    FakeBar.state["running"] = {"name": "Clock", "runtime": "", "app_id": "", "js_id": ""}
    await setup(hass)
    resp = await hass.services.async_call(DOMAIN, "launch_app", {"app": "Clock"}, blocking=True, return_response=True)
    assert resp["opened"] is True
    assert FakeBar.state["calls"] == []  # OK on a running app does something else


async def test_power_off(hass: HomeAssistant) -> None:
    FakeBar.state["running"] = {"name": "Clock", "runtime": "", "app_id": "", "js_id": ""}
    FakeBar.state["snap"] = infinite(True)
    await setup(hass)
    resp = await hass.services.async_call(DOMAIN, "power_off", {}, blocking=True, return_response=True)
    assert resp == {"off": False}
    assert FakeBar.state["calls"] == []
    FakeBar.state["snap"] = NOT_STARTED
    resp = await hass.services.async_call(DOMAIN, "power_off", {}, blocking=True, return_response=True)
    assert resp == {"off": True}
    assert FakeBar.state["calls"] == [("press", "apps"), ("press", "off")]
    assert FakeBar.state["running"] == OFF


async def test_power_off_button_ignores_timer(hass: HomeAssistant) -> None:
    FakeBar.state["running"] = {"name": "Clock", "runtime": "", "app_id": "", "js_id": ""}
    FakeBar.state["snap"] = infinite()
    await setup(hass)
    await hass.services.async_call("button", "press", {"entity_id": "button.busy_bar_power_off"}, blocking=True)
    assert FakeBar.state["calls"] == [("press", "apps"), ("press", "off")]


async def test_unknown_app(hass: HomeAssistant) -> None:
    await setup(hass)
    with pytest.raises(Exception, match="Unknown BUSY Bar app"):
        await hass.services.async_call(DOMAIN, "launch_app", {"app": "Nope"}, blocking=True)
