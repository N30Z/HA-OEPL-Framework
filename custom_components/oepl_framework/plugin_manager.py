"""Loads, tracks and drives plugins (bundled and custom-installed)."""

from __future__ import annotations

import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORAGE_KEY_PLUGINS, STORAGE_VERSION
from .plugin_api import OeplPlugin, PageContext, PluginRuntime
from .plugin_installer import async_install_from_github

_LOGGER = logging.getLogger(__name__)

BUILTIN_PLUGINS_DIR = Path(__file__).parent / "plugins" / "builtin"
INSTALLED_PLUGINS_DIR = Path(__file__).parent / "installed_plugins"
PLUGIN_REGISTRY_FILE = Path(__file__).parent / "plugin_registry.json"

INSTALLED_PACKAGE = "custom_components.oepl_framework.installed_plugins"
BUILTIN_PACKAGE = "custom_components.oepl_framework.plugins.builtin"


def _list_plugin_dirs(root: Path) -> list[Path]:
    """Blocking directory scan for plugin subfolders — run via an executor."""
    if not root.is_dir():
        return []
    return sorted(
        p for p in root.iterdir() if p.is_dir() and (p / "plugin.json").is_file()
    )


class PluginError(Exception):
    """Raised for plugin load/validation errors."""


@dataclass(frozen=True)
class PluginManifest:
    id: str
    name: str
    version: str
    entry_point: str
    pages: list[dict[str, str]]
    min_framework_version: str = "0.0.0"
    description: str = ""
    author: str = ""
    homepage: str = ""
    source: str = "custom"  # "builtin" or "custom"
    repo: str | None = None
    ref: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source: str) -> PluginManifest:
        required = ("id", "name", "version", "entry_point")
        missing = [key for key in required if key not in data]
        if missing:
            raise PluginError(f"plugin.json missing required fields: {missing}")
        if ":" not in data["entry_point"]:
            raise PluginError(
                f"entry_point must be '<module>:<ClassName>', got {data['entry_point']!r}"
            )
        return cls(
            id=data["id"],
            name=data["name"],
            version=data["version"],
            entry_point=data["entry_point"],
            pages=list(data.get("pages", [])),
            min_framework_version=data.get("min_framework_version", "0.0.0"),
            description=data.get("description", ""),
            author=data.get("author", ""),
            homepage=data.get("homepage", ""),
            source=source,
            repo=data.get("repo"),
            ref=data.get("ref"),
        )


@dataclass
class LoadedPlugin:
    manifest: PluginManifest
    instance: OeplPlugin
    enabled: bool = True


@dataclass(frozen=True)
class PluginPageRef:
    plugin_id: str
    page_id: str
    name: str
    icon: str | None = None


class _Runtime(PluginRuntime):
    """The :class:`PluginRuntime` handed to each plugin instance."""

    def __init__(self, manager: PluginManager) -> None:
        self.hass = manager.hass
        self._manager = manager

    async def async_request_page_refresh(self, tag_id: str) -> None:
        if self._manager.refresh_callback is not None:
            await self._manager.refresh_callback(tag_id)

    def get_config_entry_options(self) -> dict[str, Any]:
        return self._manager.get_config_entry_options()


class PluginManager:
    """Owns the lifecycle of all plugins known to this config entry."""

    def __init__(self, hass: HomeAssistant, options_provider=None) -> None:
        self.hass = hass
        self._plugins: dict[str, LoadedPlugin] = {}
        self._store: Store = Store(hass, STORAGE_VERSION, STORAGE_KEY_PLUGINS)
        self._install_meta: dict[str, dict[str, Any]] = {}
        self._options_provider = options_provider or (lambda: {})
        self.refresh_callback = None

    def get_config_entry_options(self) -> dict[str, Any]:
        return self._options_provider()

    # -- loading ---------------------------------------------------------

    async def async_load(self) -> None:
        """Load persisted install metadata, then builtin + installed plugins."""
        self._install_meta = await self._store.async_load() or {}
        await self.async_load_builtin_plugins()
        await self.async_load_installed_plugins()

    async def async_load_builtin_plugins(self) -> None:
        plugin_dirs = await self.hass.async_add_executor_job(
            _list_plugin_dirs, BUILTIN_PLUGINS_DIR
        )
        for plugin_dir in plugin_dirs:
            try:
                await self._async_load_plugin_dir(
                    plugin_dir, package=f"{BUILTIN_PACKAGE}.{plugin_dir.name}", source="builtin"
                )
            except PluginError as err:
                _LOGGER.error("Failed to load builtin plugin %s: %s", plugin_dir.name, err)

    async def async_load_installed_plugins(self) -> None:
        plugin_dirs = await self.hass.async_add_executor_job(
            _list_plugin_dirs, INSTALLED_PLUGINS_DIR
        )
        for plugin_dir in plugin_dirs:
            try:
                await self._async_load_plugin_dir(
                    plugin_dir, package=f"{INSTALLED_PACKAGE}.{plugin_dir.name}", source="custom"
                )
            except PluginError as err:
                _LOGGER.error("Failed to load installed plugin %s: %s", plugin_dir.name, err)

    async def _async_load_plugin_dir(self, plugin_dir: Path, *, package: str, source: str) -> None:
        manifest_data = await self.hass.async_add_executor_job(
            lambda: json.loads((plugin_dir / "plugin.json").read_text(encoding="utf-8"))
        )
        manifest = PluginManifest.from_dict(manifest_data, source=source)

        module_name, class_name = manifest.entry_point.split(":", 1)
        try:
            module = await self.hass.async_add_executor_job(
                importlib.import_module, f"{package}.{module_name}"
            )
            plugin_cls = getattr(module, class_name)
        except (ImportError, AttributeError) as err:
            raise PluginError(
                f"Could not import entry point {manifest.entry_point}: {err}"
            ) from err

        instance: OeplPlugin = plugin_cls(_Runtime(self))
        try:
            await instance.async_setup()
        except Exception as err:  # noqa: BLE001 - isolate one bad plugin from the rest
            raise PluginError(f"Plugin {manifest.id} raised during async_setup: {err}") from err

        enabled = self._install_meta.get(manifest.id, {}).get("enabled", True)
        self._plugins[manifest.id] = LoadedPlugin(
            manifest=manifest, instance=instance, enabled=enabled
        )
        _LOGGER.debug("Loaded plugin %s v%s (source=%s)", manifest.id, manifest.version, source)

    # -- install/enable/disable/remove -----------------------------------

    async def async_install_from_github(
        self, owner: str, repo: str, ref: str = "main"
    ) -> PluginManifest:
        manifest = await async_install_from_github(
            self.hass, owner, repo, ref, INSTALLED_PLUGINS_DIR
        )
        await self._async_load_plugin_dir(
            INSTALLED_PLUGINS_DIR / manifest.id,
            package=f"{INSTALLED_PACKAGE}.{manifest.id}",
            source="custom",
        )
        await self._async_save_meta(
            manifest.id,
            {
                "repo": f"{owner}/{repo}",
                "ref": ref,
                "version": manifest.version,
                "enabled": True,
            },
        )
        return manifest

    async def async_enable_plugin(self, plugin_id: str) -> None:
        await self._async_set_enabled(plugin_id, True)

    async def async_disable_plugin(self, plugin_id: str) -> None:
        await self._async_set_enabled(plugin_id, False)

    async def _async_set_enabled(self, plugin_id: str, enabled: bool) -> None:
        loaded = self._plugins.get(plugin_id)
        if loaded is None:
            raise PluginError(f"Unknown plugin: {plugin_id}")
        loaded.enabled = enabled
        await self._async_save_meta(plugin_id, {"enabled": enabled})

    async def async_remove_plugin(self, plugin_id: str) -> None:
        loaded = self._plugins.pop(plugin_id, None)
        if loaded is None:
            return
        await loaded.instance.async_unload()
        if loaded.manifest.source == "custom":
            import shutil

            plugin_dir = INSTALLED_PLUGINS_DIR / plugin_id
            await self.hass.async_add_executor_job(
                lambda: shutil.rmtree(plugin_dir, ignore_errors=True)
            )
        self._install_meta.pop(plugin_id, None)
        await self._store.async_save(self._install_meta)

    async def async_check_for_update(self, plugin_id: str) -> str | None:
        """Return the latest available version/ref string, or None if unknown."""
        from .plugin_installer import async_get_latest_ref

        loaded = self._plugins.get(plugin_id)
        meta = self._install_meta.get(plugin_id)
        if loaded is None or not meta or not meta.get("repo"):
            return None
        owner, repo = meta["repo"].split("/", 1)
        return await async_get_latest_ref(self.hass, owner, repo)

    async def _async_save_meta(self, plugin_id: str, updates: dict[str, Any]) -> None:
        self._install_meta.setdefault(plugin_id, {}).update(updates)
        await self._store.async_save(self._install_meta)

    # -- queries -----------------------------------------------------------

    def get_plugin(self, plugin_id: str) -> LoadedPlugin | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[LoadedPlugin]:
        return list(self._plugins.values())

    def get_available_pages(self, *, enabled_only: bool = True) -> list[PluginPageRef]:
        refs: list[PluginPageRef] = []
        for loaded in self._plugins.values():
            if enabled_only and not loaded.enabled:
                continue
            for page in loaded.instance.get_pages():
                refs.append(
                    PluginPageRef(
                        plugin_id=loaded.manifest.id,
                        page_id=page.id,
                        name=page.name,
                        icon=page.icon,
                    )
                )
        return refs

    async def async_render_page(
        self, plugin_id: str, page_id: str, ctx: PageContext
    ) -> list[dict[str, Any]]:
        loaded = self._plugins.get(plugin_id)
        if loaded is None or not loaded.enabled:
            raise PluginError(f"Plugin {plugin_id} is not available")
        return await loaded.instance.async_render_page(page_id, ctx)
