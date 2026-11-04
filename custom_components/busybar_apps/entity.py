"""Base entities: one device per bar, and one per buZyist (a PC)."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .buzyist import BuzyistHub
from .const import DOMAIN, MANUFACTURER
from .coordinator import BusyBarCoordinator


class BusyBarEntity(CoordinatorEntity[BusyBarCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: BusyBarCoordinator, key: str) -> None:
        super().__init__(coordinator)
        serial = coordinator.config_entry.unique_id or coordinator.config_entry.entry_id
        self._attr_unique_id = f"{serial}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            name="BUSY Bar",
            manufacturer=MANUFACTURER,
            model="BUSY Bar (VeryBUSY)",
            serial_number=serial,
            configuration_url=f"http://{coordinator.config_entry.data['host']}",
        )


class BuzyistEntity(Entity):
    """One device per buZyist entry (a PC), updated by its webhook (BuzyistHub)."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: BuzyistHub, key: str) -> None:
        self.hub = hub
        entry = hub.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"buzyist_{entry.entry_id}")},
            name=entry.title,
            manufacturer="buZyist",
            model="buZyist for Windows",
        )

    @property
    def available(self) -> bool:
        return self.hub.available

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.hub.add_listener(self.async_write_ha_state))
