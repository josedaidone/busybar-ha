"""Selects: the app on the bar now, and the app automations open (launch_app with no app)."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .coordinator import BusyBarConfigEntry, BusyBarCoordinator
from .entity import BusyBarEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: BusyBarConfigEntry, async_add_entities: AddConfigEntryEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    async_add_entities([CurrentAppSelect(coordinator), AutoAppSelect(coordinator)])


class CurrentAppSelect(BusyBarEntity, SelectEntity):
    """The app on the bar; picking one opens it there now."""

    _attr_icon = "mdi:apps"

    def __init__(self, coordinator: BusyBarCoordinator) -> None:
        super().__init__(coordinator, "app")

    @property
    def options(self) -> list[str]:
        return list(self.coordinator.choices())

    @property
    def current_option(self) -> str | None:
        value = self.coordinator.data.running_value if self.coordinator.data else ""
        label = self.coordinator.label(value) if value else None
        return label if label in self.options else None

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.launch(option)


class AutoAppSelect(BusyBarEntity, SelectEntity, RestoreEntity):
    """What busybar_apps.launch_app opens when it is given no app (e.g. the garage automation)."""

    _attr_icon = "mdi:auto-mode"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: BusyBarCoordinator) -> None:
        super().__init__(coordinator, "auto_app")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_state()) and (value := last.attributes.get("value")):
            self.coordinator.auto_app = value

    @property
    def options(self) -> list[str]:
        options = list(self.coordinator.choices())
        current = self.coordinator.label(self.coordinator.auto_app)
        return options if current in options else [*options, current]  # an app gone from the bar stays shown

    @property
    def current_option(self) -> str | None:
        return self.coordinator.label(self.coordinator.auto_app)

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        return {"value": self.coordinator.auto_app}

    async def async_select_option(self, option: str) -> None:
        self.coordinator.auto_app = self.coordinator.choices().get(option, self.coordinator.auto_app)
        self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self.async_write_ha_state()
