"""BUSY Bar Apps: open any app on a BUSY Bar (VeryBUSY firmware) from Home Assistant."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady, ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .api import BusyBarApi, BusyBarAuthError, BusyBarError
from .const import (
    ATTR_APP,
    ATTR_CONFIG_ENTRY_ID,
    ATTR_ONLY_IF_IDLE,
    ATTR_RESPECT_TIMER,
    CONF_PASSWORD,
    DOMAIN,
    SERVICE_LAUNCH_APP,
    SERVICE_POWER_OFF,
    SERVICE_REFRESH_APPS,
)
from .coordinator import BusyBarConfigEntry, BusyBarCoordinator

PLATFORMS = [Platform.BUTTON, Platform.SELECT, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

_ENTRY = {vol.Optional(ATTR_CONFIG_ENTRY_ID): cv.string}
LAUNCH_SCHEMA = vol.Schema({vol.Optional(ATTR_APP): cv.string, vol.Optional(ATTR_ONLY_IF_IDLE, default=False): cv.boolean, **_ENTRY})
POWER_OFF_SCHEMA = vol.Schema({vol.Optional(ATTR_RESPECT_TIMER, default=True): cv.boolean, **_ENTRY})
REFRESH_SCHEMA = vol.Schema(_ENTRY)


def _coordinator(hass: HomeAssistant, call: ServiceCall) -> BusyBarCoordinator:
    entries = [e for e in hass.config_entries.async_loaded_entries(DOMAIN)]
    if entry_id := call.data.get(ATTR_CONFIG_ENTRY_ID):
        entries = [e for e in entries if e.entry_id == entry_id]
    if len(entries) != 1:
        raise ServiceValidationError(
            "No loaded BUSY Bar" if not entries else "More than one BUSY Bar: give config_entry_id"
        )
    return entries[0].runtime_data


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    async def launch_app(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        app = call.data.get(ATTR_APP) or coordinator.auto_app
        opened = await coordinator.launch(app, only_if_idle=call.data[ATTR_ONLY_IF_IDLE])
        return {"opened": opened, "app": app}

    async def power_off(call: ServiceCall) -> ServiceResponse:
        coordinator = _coordinator(hass, call)
        return {"off": await coordinator.power_off(respect_timer=call.data[ATTR_RESPECT_TIMER])}

    async def refresh_apps(call: ServiceCall) -> None:
        coordinator = _coordinator(hass, call)
        await coordinator.refresh_apps()
        await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_LAUNCH_APP, launch_app, LAUNCH_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_POWER_OFF, power_off, POWER_OFF_SCHEMA, supports_response=SupportsResponse.OPTIONAL)
    hass.services.async_register(DOMAIN, SERVICE_REFRESH_APPS, refresh_apps, REFRESH_SCHEMA)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: BusyBarConfigEntry) -> bool:
    api = BusyBarApi(async_get_clientsession(hass), entry.data[CONF_HOST], entry.data.get(CONF_PASSWORD))
    try:
        await api.running()  # VeryBUSY only: stock firmware answers 404
    except BusyBarAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except BusyBarError as err:
        raise ConfigEntryNotReady(str(err)) from err
    coordinator = BusyBarCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: BusyBarConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
