# BUSY Bar Apps for Home Assistant

Open any app on a [BUSY Bar](https://busy.bar) from Home Assistant: the built-in Clock, installed `.fap` apps, JavaScript and MicroPython apps. Use it from automations ("open the clock when I walk into the garage") or from a dashboard.

It needs **[VeryBUSY](https://code.mccullough.dev/christian/VeryBUSY)** firmware: the app API it uses (`/api/apps/launch`, `/api/apps/running`, `/api/apps/system`) isn't in the stock firmware. It talks to the bar over the local HTTP API only. No cloud involved.

## What you get

| Entity | What it does |
| --- | --- |
| `select.busy_bar_app` | The app on the bar. Pick one and it opens now. |
| `select.busy_bar_auto_app` | The app `busybar_apps.launch_app` opens when it isn't given one (your automations). Kept across restarts. |
| `sensor.busy_bar_running_app` | `Off`, `Apps menu`, `Timer` or the app's name. Attributes: `value` (`runtime:id`), `is_off`, `is_idle`. |
| `sensor.busy_bar_timer` | The BUSY timer: `idle`, `running` or `paused`, with `time_left_s` and `phase`. |
| `button.busy_bar_open_auto_app` | Open the auto app now. |
| `button.busy_bar_power_off` | Turn the bar off now, timer or not. |
| `button.busy_bar_refresh_apps` | Read the app list again (it's also re-read every 10 minutes). |

The app list is read from the bar: built-in apps from `/api/apps/system` (the timer left out), `.fap` files under `/ext/apps/*/`, and script apps under `/ext/user_assets/*/` (the ones with `appmeta/` and `scripts/`, debug apps left out).

## Actions

### `busybar_apps.launch_app`

| Field | Default | |
| --- | --- | --- |
| `app` | the auto app | A name as shown in the selects (`Clock`, `Nixie`, `Weather`) or `runtime:id` (`system:clock`, `fap:/ext/apps/misc/Nixie.fap`, `js:app.busy.weather`). |
| `only_if_idle` | `false` | Only when the bar is off or on the Apps list and no timer is running or paused. Otherwise nothing happens. |

The app opens on its Start screen, so OK is pressed to start it. OK is only pressed on an app that was just opened: pressed on a running app it does something else (Nixie changes colour). The bar wakes up by itself if it's off. Returns `{opened, app}`.

### `busybar_apps.power_off`

| Field | Default | |
| --- | --- | --- |
| `respect_timer` | `true` | Do nothing while a timer is running or paused. |

The mode switch goes to Apps and then Off. `key=off` on its own does nothing when the bar's mode was already Off, which is the case for an app launched from off. Returns `{off}`.

### `busybar_apps.refresh_apps`

Read the app list again.

## Example: the garage

```yaml
alias: Busy Bar - garage
mode: restart
triggers:
  - trigger: state
    entity_id: input_boolean.garage_presence
    to: "on"
    id: enter
  - trigger: state
    entity_id: input_boolean.garage_presence
    to: "off"
    for: { seconds: 10 }
    id: leave
actions:
  - choose:
      - conditions: [{ condition: trigger, id: enter }]
        sequence:
          - action: busybar_apps.launch_app
            data: { only_if_idle: true }
      - conditions: [{ condition: trigger, id: leave }]
        sequence:
          # A timer running or paused: wait for it to be over (walking back in restarts this).
          - wait_template: "{{ is_state('sensor.busy_bar_timer', 'idle') }}"
          - action: busybar_apps.power_off
```

## buZyist

buZyist runs pomodoros on Windows, on a BUSY Bar or on the PC itself. Add a **buZyist** entry (one per PC) and it tells Home Assistant what it is doing: focus, a break, a pause or a call, and on which task or activity. It works with no bar, and while the bar is out of reach.

Settings → Devices & services → Add integration → **BUSY Bar Apps** → **buZyist on a PC** → give it a name. Home Assistant shows a webhook URL: paste it into buZyist, Settings → Integrations → Home Assistant → Webhook URL, and save. (Reconfigure on the entry shows the URL again, or makes a new one.) The webhook only takes requests from your local network.

buZyist sends a message when something changes and every minute anyway; a PC not heard from for 3 minutes (asleep, off) goes unavailable, and so does one whose buZyist quit.

| Entity | What it is |
| --- | --- |
| `sensor.<name>_state` | `idle`, `focus` (a work phase), `break`, `paused` or `call`. Attributes: `task`, `activity`, `activity_id`, `round`, `rounds`, `phase_minutes`, `source` (`here`, or `bar` for a timer started on the bar), `apps` on a call. |
| `binary_sensor.<name>_focus` | On during a work phase or a call: what buZyist blocks apps and sites for. |
| `binary_sensor.<name>_call` | On during a call (an app holding the microphone or camera). |
| `sensor.<name>_activity` | The session's activity (`Email`, `Call`, ...). |
| `sensor.<name>_task` | The Todoist task or the name typed in. |
| `sensor.<name>_phase_ends` | When the work phase or break ends (unknown while paused or on a call). |
| `sensor.<name>_pomodoros_today`, `sensor.<name>_focus_today` | Today's pomodoros and focus minutes. |

Events, for automations:

- `buzyist_state_changed`: `from`, `to`, `task`, `activity`, plus `entry_id`, `name`, `device`.
- `buzyist_session_ended`: `reason` (`finished`, `stopped`, `replaced`), `kind` (`pomodoro` or `call`), `task`, `activity`, `pomodoros`, `minutes`, `at`.

```yaml
alias: Do not disturb while focusing
triggers:
  - trigger: state
    entity_id: binary_sensor.buzyist_focus
actions:
  - action: "light.turn_{{ 'on' if trigger.to_state.state == 'on' else 'off' }}"
    target: { entity_id: light.office_door_sign }
```

## Installation

HACS → Custom repositories → `https://github.com/josedaidone/busybar-ha` (Integration) → install **BUSY Bar Apps** → restart Home Assistant → Settings → Devices & services → Add integration → **BUSY Bar Apps**: enter the bar's IP and its HTTP API password.

On the bar, HTTP API access over Wi-Fi must be on. You set that over USB at `http://10.0.4.20`, Network tab.

## Development

```sh
pip install pytest-homeassistant-custom-component
pytest
```
