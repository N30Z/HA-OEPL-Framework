"""The ``select.<tag>_active_page`` entity: the HA-side page-switch control."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    data.add_entities_callbacks["select"] = async_add_entities


class OeplFrameworkPageSelect(OeplFrameworkTagEntity, SelectEntity):
    """Selecting an option here *is* the "HA control" page-switch trigger."""

    _attr_icon = "mdi:file-image-outline"
    _attr_translation_key = "active_page"

    def __init__(self, matched_tag: MatchedTag, data: FrameworkData) -> None:
        super().__init__(matched_tag, "active_page")
        self._data = data

    @property
    def _engine(self) -> TagCycleEngine | None:
        return self._data.cycle_engine_registry.get(self.device_id)

    @property
    def options(self) -> list[str]:
        engine = self._engine
        if engine is None:
            return []
        return [entry.get("page_id", "") for entry in engine.config.page_sequence]

    @property
    def current_option(self) -> str | None:
        engine = self._engine
        page = engine.current_page if engine else None
        return page.get("page_id") if page else None

    async def async_select_option(self, option: str) -> None:
        engine = self._engine
        if engine is None:
            return
        await engine.async_set_page(option)
        self.async_write_ha_state()
