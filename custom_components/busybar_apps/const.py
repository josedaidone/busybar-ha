"""Constants for the BUSY Bar Apps integration."""

from __future__ import annotations

from datetime import timedelta

DOMAIN = "busybar_apps"
MANUFACTURER = "Flipper Devices"

CONF_PASSWORD = "password"

SCAN_INTERVAL = timedelta(seconds=5)
APPS_REFRESH_S = 600  # how often the app list is read again from the bar

# What GET /api/apps/running names (VeryBUSY firmware).
OFF_APP = "Software Power Off"  # the bar is off (mode switch on Off)
APPS_MENU = "AppsMenu"  # the Apps list
TIMER_APP = "Busy"  # the timer's own app
IDLE_APPS = (OFF_APP, APPS_MENU)  # nothing of the user's on show

RUNTIMES = ("system", "fap", "js", "python")
TIMER_APPID = "busy"  # the built-in timer, left out of the app list
DEFAULT_AUTO_APP = "system:clock"

LAUNCH_SETTLE_S = 1.5  # from the launch to the OK press (the app is loading)
KEY_SETTLE_S = 1.5  # between the two key presses of a power off

SERVICE_LAUNCH_APP = "launch_app"
SERVICE_POWER_OFF = "power_off"
SERVICE_REFRESH_APPS = "refresh_apps"

ATTR_APP = "app"
ATTR_ONLY_IF_IDLE = "only_if_idle"
ATTR_RESPECT_TIMER = "respect_timer"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"

# A buZyist entry (one per PC): buZyist POSTs what it is doing to this
# entry's webhook, as JSON (buzyist/home_assistant.py in the buZyist repo).
CONF_KIND = "kind"
KIND_BAR = "bar"  # entries from before buZyist have no kind: bars
KIND_BUZYIST = "buzyist"
CONF_WEBHOOK_ID = "webhook_id"

BUZYIST_PROTOCOL = 1  # the newest payload version ("v") understood
# buZyist sends every minute anyway: unheard from for this long, its entities go unavailable.
BUZYIST_STALE_S = 180
BUZYIST_STATES = ["idle", "focus", "break", "paused", "call"]

EVENT_BUZYIST_STATE = "buzyist_state_changed"
EVENT_BUZYIST_ENDED = "buzyist_session_ended"
