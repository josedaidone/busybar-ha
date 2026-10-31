"""Base entity: one device per bar."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

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
