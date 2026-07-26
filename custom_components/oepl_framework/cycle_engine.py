"""Per-tag page selection/cycling and the button-action dispatch registry.

Three trigger modes converge on the same engine methods, so they combine
freely per tag: a time interval, an HA `select`/`button` entity, and the
tag's own physical buttons (via OEPL's ``open_epaper_link_event`` bus
event).
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    ACTION_NEXT_PAGE,
    ACTION_PREVIOUS_PAGE,
    ACTION_SHOW_BATTERY_LED,
    DEFAULT_LED_THRESHOLDS,
    OEPL_EVENT,
)
from .led_controller import LedEffectContext, LedEffectRegistry
from .plugin_api import PageContext
from .renderer import async_build_and_push

if TYPE_CHECKING:
    from .plugin_manager import PluginManager
    from .tag_registry import TagDefinition

_LOGGER = logging.getLogger(__name__)

ActionHandler = Callable[["TagCycleEngine"], Awaitable[None]]


class ActionRegistry:
    """Named actions a button (physical or HA-side) can trigger.

    Kept open-ended (string keys) so future core features or plugins can
    register more actions without changing the dispatch mechanism.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, ActionHandler] = {}

    def register(self, name: str, handler: ActionHandler) -> None:
        self._handlers[name] = handler

    def get(self, name: str) -> ActionHandler | None:
        return self._handlers.get(name)

    def names(self) -> list[str]:
        return list(self._handlers)


def build_default_action_registry(led_effect_registry: LedEffectRegistry) -> ActionRegistry:
    """The framework's built-in actions: page navigation + LED effects."""
    registry = ActionRegistry()

    async def _next_page(engine: TagCycleEngine) -> None:
        await engine.async_next_page()

    async def _previous_page(engine: TagCycleEngine) -> None:
        await engine.async_previous_page()

    async def _show_battery_led(engine: TagCycleEngine) -> None:
        effect = led_effect_registry.get("battery_status")
        if effect is None:
            return
        ctx = LedEffectContext(
            hass=engine.hass,
            device_id=engine.device_id,
            tag_definition=engine.tag_definition,
            options={"thresholds": engine.led_thresholds},
        )
        await effect.async_run(ctx)

    registry.register(ACTION_NEXT_PAGE, _next_page)
    registry.register(ACTION_PREVIOUS_PAGE, _previous_page)
    registry.register(ACTION_SHOW_BATTERY_LED, _show_battery_led)
    return registry


@dataclass
class TagCycleConfig:
    page_sequence: list[dict[str, Any]] = field(default_factory=list)
    auto_cycle_enabled: bool = False
    cycle_interval_seconds: int = 30
    physical_buttons_enabled: bool = True
    button_action_map: dict[str, str] = field(default_factory=dict)
    led_thresholds: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LED_THRESHOLDS))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TagCycleConfig:
        return cls(
            page_sequence=list(data.get("page_sequence", [])),
            auto_cycle_enabled=data.get("auto_cycle_enabled", False),
            cycle_interval_seconds=data.get("cycle_interval_seconds", 30),
            physical_buttons_enabled=data.get("physical_buttons_enabled", True),
            button_action_map=dict(data.get("button_action_map", {})),
            led_thresholds=dict(data.get("led_thresholds", DEFAULT_LED_THRESHOLDS)),
        )


class TagCycleEngine:
    """Owns page-cycle state and rendering for exactly one tag."""

    def __init__(
        self,
        hass: HomeAssistant,
        device_id: str,
        tag_mac: str,
        tag_definition: TagDefinition,
        plugin_manager: PluginManager,
        config: TagCycleConfig,
        action_registry: ActionRegistry,
        on_page_changed: Callable[[str], None] | None = None,
    ) -> None:
        self.hass = hass
        self.device_id = device_id
        self.tag_mac = tag_mac
        self.tag_definition = tag_definition
        self.plugin_manager = plugin_manager
        self.config = config
        self._action_registry = action_registry
        self._on_page_changed = on_page_changed
        self._current_index = 0
        self._unsub_timer = None
        self._unsub_bus = None

    @property
    def led_thresholds(self) -> dict[str, int]:
        return self.config.led_thresholds

    @property
    def current_page(self) -> dict[str, Any] | None:
        if not self.config.page_sequence:
            return None
        return self.config.page_sequence[self._current_index % len(self.config.page_sequence)]

    async def async_setup(self) -> None:
        if self.config.auto_cycle_enabled and self.config.cycle_interval_seconds > 0:
            self._start_timer()
        if self.config.physical_buttons_enabled and self.tag_definition.buttons.count > 0:
            self._unsub_bus = self.hass.bus.async_listen(OEPL_EVENT, self._handle_oepl_event)

    async def async_unload(self) -> None:
        self._stop_timer()
        if self._unsub_bus:
            self._unsub_bus()
            self._unsub_bus = None

    async def async_update_config(self, config: TagCycleConfig) -> None:
        self.config = config
        self._current_index = 0
        await self.async_unload()
        await self.async_setup()

    async def async_set_auto_cycle_enabled(self, enabled: bool) -> None:
        """Runtime toggle for the time-based cycle (e.g. from a switch entity)."""
        self.config.auto_cycle_enabled = enabled
        if enabled and self.config.cycle_interval_seconds > 0:
            self._start_timer()
        else:
            self._stop_timer()

    # -- navigation ---------------------------------------------------------

    async def async_next_page(self) -> None:
        if not self.config.page_sequence:
            return
        self._current_index = (self._current_index + 1) % len(self.config.page_sequence)
        await self.async_render_current()

    async def async_previous_page(self) -> None:
        if not self.config.page_sequence:
            return
        self._current_index = (self._current_index - 1) % len(self.config.page_sequence)
        await self.async_render_current()

    async def async_set_page(self, page_id: str) -> None:
        for index, entry in enumerate(self.config.page_sequence):
            if entry.get("page_id") == page_id:
                self._current_index = index
                await self.async_render_current()
                return

    async def async_render_current(self) -> None:
        page = self.current_page
        if page is None:
            return
        ctx = PageContext(
            tag_id=self.tag_mac,
            tag_definition=self.tag_definition,
            hass=self.hass,
            options=page.get("options", {}),
        )
        try:
            elements = await self.plugin_manager.async_render_page(
                page["plugin_id"], page["page_id"], ctx
            )
        except Exception:
            _LOGGER.exception(
                "Failed to render page %s:%s for tag %s",
                page.get("plugin_id"),
                page.get("page_id"),
                self.tag_mac,
            )
            return

        await async_build_and_push(
            self.hass,
            self.device_id,
            elements,
            rotate=self.tag_definition.display.rotation_default,
        )
        if self._on_page_changed:
            self._on_page_changed(page["page_id"])

    # -- trigger sources ------------------------------------------------

    def _start_timer(self) -> None:
        self._stop_timer()
        from datetime import timedelta

        self._unsub_timer = async_track_time_interval(
            self.hass,
            self._handle_timer_tick,
            timedelta(seconds=self.config.cycle_interval_seconds),
        )

    def _stop_timer(self) -> None:
        if self._unsub_timer:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _handle_timer_tick(self, _now: Any) -> None:
        self.hass.async_create_task(self.async_next_page())

    @callback
    def _handle_oepl_event(self, event: Event) -> None:
        if event.data.get("device_id") != self.device_id:
            return
        trigger_type = event.data.get("type")
        allowed = set(self.tag_definition.buttons.trigger_types)
        if trigger_type not in allowed:
            return

        action_name = self.config.button_action_map.get(trigger_type)
        if action_name is None:
            action_name = next(
                (
                    mapping.default_action
                    for mapping in self.tag_definition.buttons.mapping
                    if mapping.trigger_type == trigger_type
                ),
                ACTION_NEXT_PAGE,
            )

        handler = self._action_registry.get(action_name)
        if handler is None:
            _LOGGER.warning("Unknown button action %r for tag %s", action_name, self.tag_mac)
            return
        self.hass.async_create_task(handler(self))


class CycleEngineRegistry:
    """One :class:`TagCycleEngine` per matched tag."""

    def __init__(
        self,
        hass: HomeAssistant,
        plugin_manager: PluginManager,
        led_effect_registry: LedEffectRegistry,
    ) -> None:
        self._hass = hass
        self._plugin_manager = plugin_manager
        self._action_registry = build_default_action_registry(led_effect_registry)
        self._engines: dict[str, TagCycleEngine] = {}

    @property
    def action_registry(self) -> ActionRegistry:
        return self._action_registry

    def get(self, device_id: str) -> TagCycleEngine | None:
        return self._engines.get(device_id)

    def all(self) -> dict[str, TagCycleEngine]:
        return dict(self._engines)

    async def async_create_or_update(
        self,
        device_id: str,
        tag_mac: str,
        tag_definition: TagDefinition,
        config: TagCycleConfig,
        on_page_changed: Callable[[str], None] | None = None,
    ) -> TagCycleEngine:
        existing = self._engines.get(device_id)
        if existing is not None:
            await existing.async_update_config(config)
            return existing

        engine = TagCycleEngine(
            self._hass,
            device_id,
            tag_mac,
            tag_definition,
            self._plugin_manager,
            config,
            self._action_registry,
            on_page_changed,
        )
        await engine.async_setup()
        self._engines[device_id] = engine
        return engine

    async def async_remove(self, device_id: str) -> None:
        engine = self._engines.pop(device_id, None)
        if engine:
            await engine.async_unload()

    async def async_unload_all(self) -> None:
        for device_id in list(self._engines):
            await self.async_remove(device_id)
