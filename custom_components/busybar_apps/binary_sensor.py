"""Binary sensors (buZyist only): in focus, on a call."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .buzyist import BuzyistHub
from .const import CONF_KIND, KIND_BUZYIST
from .entity import BuzyistEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    if entry.data.get(CONF_KIND) != KIND_BUZYIST:
        return
    hub = entry.runtime_data
    async_add_entities([FocusBinarySensor(hub), CallBinarySensor(hub)])


class FocusBinarySensor(BuzyistEntity, BinarySensorEntity):
    """On during a work phase or a call (what buZyist blocks apps and sites for); off in a break, a pause, idle."""

    _attr_icon = "mdi:bullseye-arrow"

    def __init__(self, hub: BuzyistHub) -> None:
        super().__init__(hub, "focus")

    @property
    def is_on(self) -> bool:
        return bool(self.hub.data.get("focus"))


class CallBinarySensor(BuzyistEntity, BinarySensorEntity):
    """On while buZyist counts a call (an app holding the mic or camera)."""

    _attr_icon = "mdi:phone-in-talk"

    def __init__(self, hub: BuzyistHub) -> None:
        super().__init__(hub, "call")

    @property
    def is_on(self) -> bool:
        return self.hub.data.get("state") == "call"
