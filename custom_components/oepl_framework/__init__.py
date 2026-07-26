"""The OEPL Page Framework integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, OEPL_DOMAIN, PLATFORMS
from .cycle_engine import CycleEngineRegistry
from .led_controller import BatteryStatusLedEffect, LedEffectRegistry
from .plugin_manager import PluginManager
from .runtime import FrameworkData
from .tag_registry import TagDefinitionRegistry, TagRegistry
from .tag_sync import async_sync_tags

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up OEPL Page Framework from a config entry."""
    if not hass.config_entries.async_entries(OEPL_DOMAIN):
        raise ConfigEntryNotReady("The OpenEPaperLink integration is not set up")

    tag_definition_registry = TagDefinitionRegistry(hass)
    await tag_definition_registry.async_load()

    tag_registry = TagRegistry(hass, tag_definition_registry)

    plugin_manager = PluginManager(hass, options_provider=lambda: dict(entry.options))
    await plugin_manager.async_load()

    led_effect_registry = LedEffectRegistry()
    led_effect_registry.register(BatteryStatusLedEffect())

    cycle_engine_registry = CycleEngineRegistry(hass, plugin_manager, led_effect_registry)

    async def _async_request_refresh(tag_id: str) -> None:
        for engine in cycle_engine_registry.all().values():
            if engine.tag_mac == tag_id:
                await engine.async_render_current()

    plugin_manager.refresh_callback = _async_request_refresh

    data = FrameworkData(
        plugin_manager=plugin_manager,
        tag_definition_registry=tag_definition_registry,
        tag_registry=tag_registry,
        cycle_engine_registry=cycle_engine_registry,
        led_effect_registry=led_effect_registry,
    )
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Initial discovery pass, now that platforms have registered their
    # add_entities callbacks.
    await async_sync_tags(hass, entry)

    tag_registry.async_setup_discovery_listener(
        lambda: hass.async_create_task(async_sync_tags(hass, entry))
    )

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_sync_tags(hass, entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        data: FrameworkData = hass.data[DOMAIN].pop(entry.entry_id)
        await data.cycle_engine_registry.async_unload_all()
        data.tag_registry.async_unload()
    return unload_ok
