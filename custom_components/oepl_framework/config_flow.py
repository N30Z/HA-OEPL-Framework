"""Config + options flow: setup, plugin management, per-tag page/trigger setup."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    DEFAULT_CYCLE_INTERVAL_SECONDS,
    DEFAULT_LED_THRESHOLDS,
    DOMAIN,
    OEPL_DOMAIN,
    OPT_AUTO_CYCLE_ENABLED,
    OPT_BUTTON_ACTION_MAP,
    OPT_CYCLE_INTERVAL_SECONDS,
    OPT_LED_THRESHOLDS,
    OPT_PAGE_SEQUENCE,
    OPT_PHYSICAL_BUTTONS_ENABLED,
    OPT_PLUGIN_DISCOVERY_OWNER,
    OPT_TAGS,
    PLUGIN_REPO_PREFIX,
)
from .plugin_installer import PluginInstallError, async_list_repos_by_prefix
from .plugin_manager import PluginError
from .runtime import FrameworkData
from .tag_sync import async_sync_tags

_LOGGER = logging.getLogger(__name__)


class OeplFrameworkConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: single instance, requires OpenEPaperLink to be set up."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if not self.hass.config_entries.async_entries(OEPL_DOMAIN):
            return self.async_abort(reason="oepl_not_installed")

        if user_input is not None:
            return self.async_create_entry(title="OEPL Page Framework", data={}, options={})

        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OeplFrameworkOptionsFlow:
        return OeplFrameworkOptionsFlow(config_entry)


class OeplFrameworkOptionsFlow(OptionsFlow):
    """Menu-driven options: manage plugins, manage per-tag page/trigger setup."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry
        self._selected_device_id: str | None = None

    @property
    def _data(self) -> FrameworkData:
        return self.hass.data[DOMAIN][self.config_entry.entry_id]

    async def async_step_init(self, user_input: dict | None = None):
        return self.async_show_menu(
            step_id="init",
            menu_options=["manage_plugins", "manage_tags", "rescan_tags"],
        )

    # -- tags --------------------------------------------------------------

    async def async_step_rescan_tags(self, user_input: dict | None = None):
        await async_sync_tags(self.hass, self.config_entry)
        return self.async_create_entry(title="", data=dict(self.config_entry.options))

    async def async_step_manage_tags(self, user_input: dict | None = None):
        matched = self._data.tag_registry.matched
        unmatched_models = sorted(
            {model for model in self._data.tag_registry.unmatched.values() if model}
        )

        if not matched:
            return self.async_abort(
                reason="no_tags_found",
                description_placeholders={"unmatched": ", ".join(unmatched_models) or "-"},
            )

        if user_input is not None:
            self._selected_device_id = user_input["device_id"]
            return await self.async_step_tag_options()

        choices = {device_id: tag.name for device_id, tag in matched.items()}
        schema = vol.Schema({vol.Required("device_id"): vol.In(choices)})
        return self.async_show_form(
            step_id="manage_tags",
            data_schema=schema,
            description_placeholders={"unmatched": ", ".join(unmatched_models) or "-"},
        )

    async def async_step_tag_options(self, user_input: dict | None = None):
        matched_tag = self._data.tag_registry.matched.get(self._selected_device_id or "")
        if matched_tag is None:
            return self.async_abort(reason="tag_no_longer_available")

        available_pages = self._data.plugin_manager.get_available_pages()
        page_choices = {
            f"{ref.plugin_id}:{ref.page_id}": f"{ref.name} ({ref.plugin_id})"
            for ref in available_pages
        }

        current = self.config_entry.options.get(OPT_TAGS, {}).get(matched_tag.tag_mac, {})
        current_pages = [
            f"{page['plugin_id']}:{page['page_id']}" for page in current.get(OPT_PAGE_SEQUENCE, [])
        ]

        if user_input is not None:
            page_sequence = []
            for key in user_input.get("pages", []):
                plugin_id, page_id = key.split(":", 1)
                page_sequence.append({"plugin_id": plugin_id, "page_id": page_id, "options": {}})

            new_tag_config = {
                OPT_PAGE_SEQUENCE: page_sequence,
                OPT_AUTO_CYCLE_ENABLED: user_input["auto_cycle_enabled"],
                OPT_CYCLE_INTERVAL_SECONDS: user_input["cycle_interval_seconds"],
                OPT_PHYSICAL_BUTTONS_ENABLED: user_input["physical_buttons_enabled"],
                OPT_BUTTON_ACTION_MAP: current.get(OPT_BUTTON_ACTION_MAP, {}),
                OPT_LED_THRESHOLDS: current.get(OPT_LED_THRESHOLDS, dict(DEFAULT_LED_THRESHOLDS)),
            }

            new_options = dict(self.config_entry.options)
            tags_options = dict(new_options.get(OPT_TAGS, {}))
            tags_options[matched_tag.tag_mac] = new_tag_config
            new_options[OPT_TAGS] = tags_options

            # Apply immediately: update the entry's options first so the
            # sync below picks up the new config, not the stale one.
            self.hass.config_entries.async_update_entry(self.config_entry, options=new_options)
            await async_sync_tags(self.hass, self.config_entry)
            return self.async_create_entry(title="", data=new_options)

        schema = vol.Schema(
            {
                vol.Optional("pages", default=current_pages): cv.multi_select(page_choices),
                vol.Optional(
                    "auto_cycle_enabled", default=current.get(OPT_AUTO_CYCLE_ENABLED, False)
                ): bool,
                vol.Optional(
                    "cycle_interval_seconds",
                    default=current.get(
                        OPT_CYCLE_INTERVAL_SECONDS, DEFAULT_CYCLE_INTERVAL_SECONDS
                    ),
                ): vol.All(int, vol.Range(min=0)),
                vol.Optional(
                    "physical_buttons_enabled",
                    default=current.get(OPT_PHYSICAL_BUTTONS_ENABLED, True),
                ): bool,
            }
        )
        return self.async_show_form(
            step_id="tag_options",
            data_schema=schema,
            description_placeholders={"tag_name": matched_tag.name},
        )

    # -- plugins -------------------------------------------------------

    async def async_step_manage_plugins(self, user_input: dict | None = None):
        return self.async_show_menu(
            step_id="manage_plugins",
            menu_options=["add_custom_repo", "discover_plugins", "manage_installed"],
        )

    async def async_step_discover_plugins(self, user_input: dict | None = None):
        """Find + one-click install repos matching the naming convention.

        Repos named e.g. ``HAOEPL-Plugin_AWSH`` under a given GitHub owner
        are listed automatically, so plugin authors following this
        convention don't have to be added one-by-one via "Add custom repo".
        """
        errors: dict[str, str] = {}
        owner = (user_input or {}).get(
            "owner", self.config_entry.options.get(OPT_PLUGIN_DISCOVERY_OWNER, "")
        )

        installed_now: set[str] = set()
        if user_input is not None and user_input.get("repos"):
            if not user_input.get("confirm_trust"):
                errors["confirm_trust"] = "trust_required"
            else:
                for choice in user_input["repos"]:
                    repo_name, _, ref = choice.partition("@")
                    try:
                        await self._data.plugin_manager.async_install_from_github(
                            owner, repo_name, ref or "main"
                        )
                        installed_now.add(repo_name)
                    except (PluginError, PluginInstallError) as err:
                        _LOGGER.warning(
                            "Plugin install failed for %s/%s: %s", owner, repo_name, err
                        )
                        errors["base"] = "plugin_install_failed"

                if not errors:
                    new_options = dict(self.config_entry.options)
                    new_options[OPT_PLUGIN_DISCOVERY_OWNER] = owner
                    return self.async_create_entry(title="", data=new_options)

        found: list[dict[str, str]] = []
        if owner:
            try:
                found = await async_list_repos_by_prefix(self.hass, owner, PLUGIN_REPO_PREFIX)
            except PluginInstallError as err:
                _LOGGER.warning("Plugin discovery failed for owner %s: %s", owner, err)
                errors["base"] = "discovery_failed"

        installed_repo_names = {
            loaded.manifest.repo.split("/", 1)[1]
            for loaded in self._data.plugin_manager.list_plugins()
            if loaded.manifest.repo and "/" in loaded.manifest.repo
        } | installed_now

        choices = {
            f"{item['repo']}@{item['default_branch']}": (
                f"{item['repo']} — {item['description'] or 'no description'}"
            )
            for item in found
            if item["repo"] not in installed_repo_names
        }

        schema = vol.Schema(
            {
                vol.Required("owner", default=owner): str,
                vol.Optional("repos", default=[]): cv.multi_select(choices),
                vol.Required("confirm_trust", default=False): bool,
            }
        )
        return self.async_show_form(
            step_id="discover_plugins",
            data_schema=schema,
            errors=errors,
            description_placeholders={"prefix": PLUGIN_REPO_PREFIX},
        )

    async def async_step_add_custom_repo(self, user_input: dict | None = None):
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get("confirm_trust"):
                errors["confirm_trust"] = "trust_required"
            else:
                try:
                    await self._data.plugin_manager.async_install_from_github(
                        user_input["owner"], user_input["repo"], user_input.get("ref") or "main"
                    )
                except (PluginError, PluginInstallError) as err:
                    _LOGGER.warning("Plugin install failed: %s", err)
                    errors["base"] = "plugin_install_failed"
                else:
                    return self.async_create_entry(title="", data=dict(self.config_entry.options))

        schema = vol.Schema(
            {
                vol.Required("owner"): str,
                vol.Required("repo"): str,
                vol.Optional("ref", default="main"): str,
                vol.Required("confirm_trust", default=False): bool,
            }
        )
        return self.async_show_form(step_id="add_custom_repo", data_schema=schema, errors=errors)

    async def async_step_manage_installed(self, user_input: dict | None = None):
        plugins = self._data.plugin_manager.list_plugins()
        if not plugins:
            return self.async_abort(reason="no_plugins_installed")

        choices = {
            loaded.manifest.id: (
                f"{loaded.manifest.name} "
                f"({loaded.manifest.source}, {'enabled' if loaded.enabled else 'disabled'})"
            )
            for loaded in plugins
        }

        if user_input is not None:
            plugin_id = user_input["plugin_id"]
            action = user_input["action"]
            if action == "enable":
                await self._data.plugin_manager.async_enable_plugin(plugin_id)
            elif action == "disable":
                await self._data.plugin_manager.async_disable_plugin(plugin_id)
            elif action == "remove":
                await self._data.plugin_manager.async_remove_plugin(plugin_id)
            return self.async_create_entry(title="", data=dict(self.config_entry.options))

        schema = vol.Schema(
            {
                vol.Required("plugin_id"): vol.In(choices),
                vol.Required("action", default="enable"): vol.In(
                    {"enable": "Enable", "disable": "Disable", "remove": "Remove"}
                ),
            }
        )
        return self.async_show_form(step_id="manage_installed", data_schema=schema)
