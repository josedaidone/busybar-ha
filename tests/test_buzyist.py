"""Tests for the buZyist entries: the flow, the webhook, the entities and the events."""

from __future__ import annotations

import time
from unittest.mock import patch

import pytest
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_capture_events

from custom_components.busybar_apps.const import BUZYIST_STALE_S, DOMAIN, EVENT_BUZYIST_ENDED, EVENT_BUZYIST_STATE

HOOK = "buzyist-test-hook"

IDLE = {
    "v": 1,
    "app": "buZyist",
    "version": "2.17.0",
    "device": "DESK-PC",
    "state": "idle",
    "focus": False,
    "session": None,
    "ended": None,
    "today": {"pomodoros": 2, "minutes": 50, "completed": 1},
}
FOCUS = {
    **IDLE,
    "state": "focus",
    "focus": True,
    "session": {
        "kind": "pomodoro",
        "source": "here",
        "task": "Email - inbox zero",
        "task_id": "",
        "project": "",
        "activity": {"id": "email", "name": "Email", "detail": "inbox zero"},
        "phase": "work",
        "paused": False,
        "ends_at": "2026-11-04T15:25:00+00:00",
        "ends_ms": 1793805900000,
        "phase_minutes": 25,
        "round": 1,
        "rounds": 4,
        "done": 0,
        "started_at": "2026-11-04T12:00:00",
        "apps": [],
    },
}
ENDED = {
    **IDLE,
    "today": {"pomodoros": 3, "minutes": 75, "completed": 1},
    "ended": {
        "reason": "stopped",
        "kind": "pomodoro",
        "task": "Email - inbox zero",
        "task_id": "",
        "activity": {"id": "email", "name": "Email", "detail": "inbox zero"},
        "pomodoros": 1,
        "minutes": 25,
        "at": "2026-11-04T15:30:00+00:00",
    },
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
async def post(hass: HomeAssistant, hass_client_no_auth):
    """Sets up a buZyist entry; ``post(payload)`` sends it to the webhook and returns (status, json)."""
    assert await async_setup_component(hass, "http", {})
    entry = MockConfigEntry(
        domain=DOMAIN, title="buZyist", unique_id=HOOK, data={"kind": "buzyist", "webhook_id": HOOK}
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    async def send(payload, raw=None):
        if raw is not None:
            response = await client.post(f"/api/webhook/{HOOK}", data=raw)
        else:
            response = await client.post(f"/api/webhook/{HOOK}", json=payload)
        await hass.async_block_till_done()
        return response.status, await response.json()

    send.entry = entry
    return send


async def test_flow_makes_a_webhook(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"next_step_id": "buzyist"})
    assert result["type"] is FlowResultType.FORM
    with patch("custom_components.busybar_apps.async_setup_entry", return_value=True):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Desk PC"})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Desk PC"
    assert result["data"]["kind"] == "buzyist"
    hook = result["data"]["webhook_id"]
    assert result["description_placeholders"]["url"].endswith(f"/api/webhook/{hook}")


async def test_reconfigure_shows_the_url_and_makes_a_new_one(hass: HomeAssistant, post) -> None:
    entry = post.entry
    result = await entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure_buzyist"
    assert result["description_placeholders"]["url"].endswith(f"/api/webhook/{HOOK}")
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {"name": "Desk PC", "new_url": True})
    assert result["type"] is FlowResultType.ABORT
    assert entry.title == "Desk PC"
    assert entry.data["webhook_id"] != HOOK


async def test_nothing_heard_yet_is_unavailable(hass: HomeAssistant, post) -> None:
    assert hass.states.get("sensor.buzyist_state").state == STATE_UNAVAILABLE
    assert hass.states.get("binary_sensor.buzyist_focus").state == STATE_UNAVAILABLE


async def test_a_session(hass: HomeAssistant, post) -> None:
    assert await post(FOCUS) == (200, {"ok": True, "name": "buZyist"})
    state = hass.states.get("sensor.buzyist_state")
    assert state.state == "focus"
    assert state.attributes["activity_id"] == "email" and state.attributes["rounds"] == 4
    assert state.attributes["version"] == "2.17.0"
    assert hass.states.get("binary_sensor.buzyist_focus").state == "on"
    assert hass.states.get("binary_sensor.buzyist_call").state == "off"
    assert hass.states.get("sensor.buzyist_activity").state == "Email"
    assert hass.states.get("sensor.buzyist_task").state == "Email - inbox zero"
    assert hass.states.get("sensor.buzyist_phase_ends").state == "2026-11-04T15:25:00+00:00"
    assert hass.states.get("sensor.buzyist_pomodoros_today").state == "2"
    assert hass.states.get("sensor.buzyist_focus_today").state == "50"


async def test_events(hass: HomeAssistant, post) -> None:
    changed = async_capture_events(hass, EVENT_BUZYIST_STATE)
    ended = async_capture_events(hass, EVENT_BUZYIST_ENDED)
    await post(IDLE)
    assert changed == []  # the first message after a restart isn't news
    await post(FOCUS)
    await post(FOCUS)
    assert [(e.data["from"], e.data["to"]) for e in changed] == [("idle", "focus")]
    assert changed[0].data["activity"]["id"] == "email"
    await post(ENDED)
    await post(ENDED)
    assert (changed[-1].data["from"], changed[-1].data["to"]) == ("focus", "idle")
    assert len(ended) == 1
    assert ended[0].data["reason"] == "stopped" and ended[0].data["pomodoros"] == 1
    assert ended[0].data["device"] == "DESK-PC"
    assert hass.states.get("sensor.buzyist_activity").state == STATE_UNKNOWN
    assert hass.states.get("sensor.buzyist_phase_ends").state == STATE_UNKNOWN


async def test_a_call(hass: HomeAssistant, post) -> None:
    session = {**FOCUS["session"], "kind": "call", "ends_at": None, "apps": ["Zoom"]}
    await post({**FOCUS, "state": "call", "session": session})
    assert hass.states.get("binary_sensor.buzyist_call").state == "on"
    assert hass.states.get("sensor.buzyist_state").attributes["apps"] == ["Zoom"]
    assert hass.states.get("sensor.buzyist_phase_ends").state == STATE_UNKNOWN


async def test_closed_and_quiet_go_unavailable(hass: HomeAssistant, post) -> None:
    await post(FOCUS)
    await post({"v": 1, "closed": True})
    assert hass.states.get("sensor.buzyist_state").state == STATE_UNAVAILABLE
    await post(IDLE)
    assert hass.states.get("sensor.buzyist_state").state == "idle"
    hub = post.entry.runtime_data
    hub.seen = time.monotonic() - BUZYIST_STALE_S - 1
    assert not hub.available


async def test_not_a_message(hass: HomeAssistant, post) -> None:
    assert (await post(None, raw=b"nope"))[0] == 400
    assert (await post({"state": "focus"}))[0] == 400


async def test_unload_removes_the_webhook(hass: HomeAssistant, post) -> None:
    assert await hass.config_entries.async_unload(post.entry.entry_id)
    assert HOOK not in hass.data.get("webhook", {})
