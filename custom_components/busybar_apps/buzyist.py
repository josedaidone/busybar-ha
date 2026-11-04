"""
buZyist: a Windows app that runs pomodoros (on a BUSY Bar or on the PC)
tells Home Assistant what it is doing through a webhook, one entry per PC.

The payload (version 1), POSTed when something changes and every minute:

    {"v": 1, "app": "buZyist", "version": "2.17.0", "device": "DESK-PC",
     "state": "idle" | "focus" | "break" | "paused" | "call",
     "focus": bool,                      # a work phase or a call: apps and sites blocked
     "session": null | {"kind": "pomodoro" | "call", "source": "here" | "bar",
                        "task", "task_id", "project", "activity": null | {id, name, detail},
                        "phase", "paused", "ends_at" (ISO, UTC; null while paused or on a call),
                        "phase_minutes", "round", "rounds", "done", "started_at", "apps"},
     "ended": null | {"reason", "kind", "task", "task_id", "activity", "pomodoros", "minutes", "at"},
     "today": {"pomodoros", "minutes", "completed"}}

and {"v": 1, "closed": true} when buZyist quits. The webhook answers
{"ok": true, "name": <entry title>}, which buZyist checks: Home Assistant
answers an unknown webhook with an empty 200.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from aiohttp import web

from homeassistant.components import webhook
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError

from .const import (
    BUZYIST_PROTOCOL,
    BUZYIST_STALE_S,
    CONF_WEBHOOK_ID,
    DOMAIN,
    EVENT_BUZYIST_ENDED,
    EVENT_BUZYIST_STATE,
)

_LOGGER = logging.getLogger(__name__)

CHECK_EVERY = timedelta(seconds=30)  # how often a quiet PC is looked at (BUZYIST_STALE_S)

type BuzyistConfigEntry = ConfigEntry[BuzyistHub]


def webhook_url(hass: HomeAssistant, webhook_id: str) -> str:
    """The URL to paste into buZyist: the local one first (the PC is on the same network)."""
    try:
        return webhook.async_generate_url(hass, webhook_id, prefer_external=False)
    except NoURLAvailableError:
        return webhook.async_generate_path(webhook_id)


class BuzyistHub:
    """The last thing one buZyist said, and who listens to it (its entities)."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.data: dict[str, Any] = {}
        self.seen = 0.0  # time.monotonic() of the last message; 0: none since Home Assistant started
        self.closed = False  # buZyist said it quit
        self._listeners: list[Callable[[], None]] = []
        self._was_available = False
        self._unsub: CALLBACK_TYPE | None = None

    @property
    def available(self) -> bool:
        return bool(self.seen) and not self.closed and time.monotonic() - self.seen < BUZYIST_STALE_S

    @property
    def session(self) -> dict[str, Any]:
        return self.data.get("session") or {}

    @callback
    def add_listener(self, update: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update)
        return lambda: self._listeners.remove(update)

    @callback
    def _notify(self) -> None:
        self._was_available = self.available
        for update in list(self._listeners):
            update()

    async def async_start(self) -> None:
        # Local only: the PC is on the same network, and a URL that got out
        # can't be used from the internet.
        webhook.async_register(
            self.hass,
            DOMAIN,
            f"buZyist ({self.entry.title})",
            self.entry.data[CONF_WEBHOOK_ID],
            self.handle,
            local_only=True,
            allowed_methods=["POST"],
        )

        @callback
        def check(_now) -> None:  # a PC gone quiet (asleep, off, unplugged) goes unavailable
            if self.available != self._was_available:
                self._notify()

        self._unsub = async_track_time_interval(self.hass, check, CHECK_EVERY)

    @callback
    def async_stop(self) -> None:
        webhook.async_unregister(self.hass, self.entry.data[CONF_WEBHOOK_ID])
        if self._unsub:
            self._unsub()

    async def handle(self, hass: HomeAssistant, webhook_id: str, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"ok": False, "error": "not JSON"}, status=400)
        if not isinstance(payload, dict) or not isinstance(payload.get("v"), int):
            return web.json_response({"ok": False, "error": "not a buZyist message"}, status=400)
        if payload["v"] > BUZYIST_PROTOCOL:
            _LOGGER.debug("buZyist sends version %s; reading what version %s has", payload["v"], BUZYIST_PROTOCOL)
        self.receive(payload)
        return web.json_response({"ok": True, "name": self.entry.title})

    @callback
    def receive(self, payload: dict[str, Any]) -> None:
        """A message from buZyist: keep it, fire the events it means, update the entities."""
        if payload.get("closed"):
            self.closed = True
            self._notify()
            return
        old, first = self.data, not self.seen
        self.data, self.seen, self.closed = payload, time.monotonic(), False
        base = {"entry_id": self.entry.entry_id, "name": self.entry.title, "device": payload.get("device", "")}
        if not first:  # after a restart, what was already so isn't news
            if old.get("state") != payload.get("state"):
                session = payload.get("session") or {}
                self.hass.bus.async_fire(
                    EVENT_BUZYIST_STATE,
                    {
                        **base,
                        "from": old.get("state"),
                        "to": payload.get("state"),
                        "task": session.get("task", ""),
                        "activity": session.get("activity"),
                    },
                )
            ended = payload.get("ended")
            if isinstance(ended, dict) and ended.get("at") != (old.get("ended") or {}).get("at"):
                self.hass.bus.async_fire(EVENT_BUZYIST_ENDED, {**base, **ended})
        self._notify()

