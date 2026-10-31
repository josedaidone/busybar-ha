"""Buttons: turn the bar off, read the app list again."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import BusyBarConfigEntry, BusyBarCoordinator
from .entity import BusyBarEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: BusyBarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([PowerOffButton(coordinator), OpenAutoAppButton(coordinator), RefreshAppsButton(coordinator)])


class PowerOffButton(BusyBarEntity, ButtonEntity):
    """Turn the bar off now (a press is on purpose: a running timer doesn't stop it)."""

    _attr_icon = "mdi:power"

    def __init__(self, coordinator: BusyBarCoordinator) -> None:
        super().__init__(coordinator, "power_off")

    async def async_press(self) -> None:
        await self.coordinator.power_off(respect_timer=False)


class OpenAutoAppButton(BusyBarEntity, ButtonEntity):
    """Open the auto app now."""

    _attr_icon = "mdi:play"

    def __init__(self, coordinator: BusyBarCoordinator) -> None:
        super().__init__(coordinator, "open_auto_app")

    async def async_press(self) -> None:
        await self.coordinator.launch(self.coordinator.auto_app)


class RefreshAppsButton(BusyBarEntity, ButtonEntity):
    """Read the app list from the bar again (after installing an app)."""

    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: BusyBarCoordinator) -> None:
        super().__init__(coordinator, "refresh_apps")

    async def async_press(self) -> None:
        await self.coordinator.refresh_apps()
        await self.coordinator.async_request_refresh()
