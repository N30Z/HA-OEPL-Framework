"""The ``switch.<tag>_auto_cycle`` entity: runtime on/off for time-based cycling."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
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
    data.add_entities_callbacks["switch"] = async_add_entities


class OeplFrameworkAutoCycleSwitch(OeplFrameworkTagEntity, SwitchEntity):
    _attr_icon = "mdi:autorenew"
    _attr_translation_key = "auto_cycle"

    def __init__(self, matched_tag: MatchedTag, data: FrameworkData) -> None:
        super().__init__(matched_tag, "auto_cycle")
        self._data = data

    @property
    def _engine(self) -> TagCycleEngine | None:
        return self._data.cycle_engine_registry.get(self.device_id)

    @property
    def is_on(self) -> bool:
        engine = self._engine
        return bool(engine and engine.config.auto_cycle_enabled)

    async def async_turn_on(self, **kwargs: Any) -> None:
        if (engine := self._engine) is not None:
            await engine.async_set_auto_cycle_enabled(True)
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if (engine := self._engine) is not None:
            await engine.async_set_auto_cycle_enabled(False)
            self.async_write_ha_state()
