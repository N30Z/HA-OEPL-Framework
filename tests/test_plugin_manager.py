import pytest

from custom_components.oepl_framework.plugin_api import PageContext
from custom_components.oepl_framework.plugin_manager import (
    PluginError,
    PluginManager,
    PluginManifest,
)
from custom_components.oepl_framework.tag_registry import TagDefinitionRegistry


async def test_builtin_demo_plugin_loads_and_lists_pages(hass):
    manager = PluginManager(hass)
    await manager.async_load()

    loaded = manager.get_plugin("demo_plugin")
    assert loaded is not None
    assert loaded.enabled is True
    assert loaded.manifest.source == "builtin"

    pages = manager.get_available_pages()
    page_ids = {ref.page_id for ref in pages if ref.plugin_id == "demo_plugin"}
    assert page_ids == {"clock", "sensor"}


async def test_render_page_returns_drawcustom_elements(hass):
    manager = PluginManager(hass)
    await manager.async_load()

    definition_registry = TagDefinitionRegistry(hass)
    await definition_registry.async_load()
    tag_definition = definition_registry.get("el026h3bra")

    ctx = PageContext(
        tag_id="AA:BB:CC:DD:EE:FF",
        tag_definition=tag_definition,
        hass=hass,
        options={},
    )
    elements = await manager.async_render_page("demo_plugin", "clock", ctx)
    assert isinstance(elements, list)
    assert elements
    assert all("type" in element for element in elements)


async def test_disable_plugin_removes_it_from_available_pages(hass):
    manager = PluginManager(hass)
    await manager.async_load()

    await manager.async_disable_plugin("demo_plugin")
    enabled_plugin_ids = {ref.plugin_id for ref in manager.get_available_pages(enabled_only=True)}
    assert "demo_plugin" not in enabled_plugin_ids
    all_plugin_ids = {ref.plugin_id for ref in manager.get_available_pages(enabled_only=False)}
    assert "demo_plugin" in all_plugin_ids

    await manager.async_enable_plugin("demo_plugin")
    assert manager.get_available_pages(enabled_only=True) != []


async def test_render_unavailable_plugin_raises(hass):
    manager = PluginManager(hass)
    await manager.async_load()
    await manager.async_disable_plugin("demo_plugin")

    with pytest.raises(PluginError):
        await manager.async_render_page("demo_plugin", "clock", None)


def test_plugin_manifest_requires_fields():
    with pytest.raises(PluginError):
        PluginManifest.from_dict({"id": "x"}, source="custom")


def test_plugin_manifest_requires_colon_entry_point():
    with pytest.raises(PluginError):
        PluginManifest.from_dict(
            {"id": "x", "name": "X", "version": "1.0", "entry_point": "no_colon"},
            source="custom",
        )
