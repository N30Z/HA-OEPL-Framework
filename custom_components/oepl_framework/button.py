"""Per-tag button entities: page navigation and the battery-LED effect."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ACTION_SHOW_BATTERY_LED, DOMAIN
from .cycle_engine import TagCycleEngine
from .entity import OeplFrameworkTagEntity
from .runtime import FrameworkData
from .tag_registry import MatchedTag


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    # Entities are created by tag_sync.async_sync_tags() once all platforms
    # have registered their callbacks, so both already-known and
    # later-discovered tags go through the same code path.
    data: FrameworkData = hass.data[DOMAIN][entry.entry_id]
    data.add_entities_callbacks["button"] = async_add_entities


class _EngineButton(OeplFrameworkTagEntity, ButtonEntity):
    def __init__(self, matched_tag: MatchedTag, data: FrameworkData, key: str, icon: str) -> None:
        super().__init__(matched_tag, key)
        self._data = data
        self._attr_translation_key = key
        self._attr_icon = icon

    @property
    def _engine(self) -> TagCycleEngine | None:
        return self._data.cycle_engine_registry.get(self.device_id)


class NextPageButton(_EngineButton):
    def __init__(self, matched_tag: MatchedTag, data: FrameworkData) -> None:
        super().__init__(matched_tag, data, "next_page", "mdi:page-next-outline")

    async def async_press(self) -> None:
        if (engine := self._engine) is not None:
            await engine.async_next_page()


class PreviousPageButton(_EngineButton):
    def __init__(self, matched_tag: MatchedTag, data: FrameworkData) -> None:
        super().__init__(matched_tag, data, "previous_page", "mdi:page-previous-outline")

    async def async_press(self) -> None:
        if (engine := self._engine) is not None:
            await engine.async_previous_page()


class RefreshPageButton(_EngineButton):
    def __init__(self, matched_tag: MatchedTag, data: FrameworkData) -> None:
        super().__init__(matched_tag, data, "refresh_page", "mdi:refresh")

    async def async_press(self) -> None:
        if (engine := self._engine) is not None:
            await engine.async_render_current()


class ShowBatteryLedButton(_EngineButton):
    """Flashes the status LED green/yellow/red for ~5s based on battery level."""

    def __init__(self, matched_tag: MatchedTag, data: FrameworkData) -> None:
        super().__init__(matched_tag, data, "show_battery_led", "mdi:battery-heart-variant")

    async def async_press(self) -> None:
        engine = self._engine
        if engine is None:
            return
        handler = self._data.cycle_engine_registry.action_registry.get(ACTION_SHOW_BATTERY_LED)
        if handler is not None:
            await handler(engine)
