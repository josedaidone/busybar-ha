"""Config flow: the bar's address and HTTP API password."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import BusyBarApi, BusyBarAuthError, BusyBarConnectionError, BusyBarError
from .const import CONF_PASSWORD, DOMAIN


async def _check(hass, host: str, password: str | None) -> tuple[str, str]:
    """(serial number, name) of the bar, once it has answered the apps API."""
    api = BusyBarApi(async_get_clientsession(hass), host, password)
    status = await api.status()
    await api.running()  # 404 on stock firmware
    try:
        name = await api.name()
    except BusyBarError:
        name = ""
    return status["device"]["serial_number"], name or "BUSY Bar"


class BusyBarAppsConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _try(self, user_input: dict[str, Any], errors: dict[str, str]) -> tuple[str, str] | None:
        try:
            return await _check(self.hass, user_input[CONF_HOST], user_input.get(CONF_PASSWORD))
        except BusyBarAuthError:
            errors["base"] = "invalid_auth"
        except BusyBarConnectionError:
            errors["base"] = "cannot_connect"
        except (BusyBarError, KeyError):
            errors["base"] = "not_verybusy"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            found = await self._try(user_input, errors)
            if found:
                serial, _name = found
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates=user_input)
                return self.async_create_entry(title="BUSY Bar", data=user_input)
        schema = vol.Schema({vol.Required(CONF_HOST): str, vol.Optional(CONF_PASSWORD): str})
        return self.async_show_form(
            step_id="user", data_schema=self.add_suggested_values_to_schema(schema, user_input), errors=errors
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reconfigure()

    async def async_step_reconfigure(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry() if self.source == "reauth" else self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            found = await self._try(user_input, errors)
            if found:
                await self.async_set_unique_id(found[0])
                self._abort_if_unique_id_mismatch()
                return self.async_update_reload_and_abort(entry, data_updates=user_input)
        schema = vol.Schema({vol.Required(CONF_HOST): str, vol.Optional(CONF_PASSWORD): str})
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or dict(entry.data)),
            errors=errors,
        )
