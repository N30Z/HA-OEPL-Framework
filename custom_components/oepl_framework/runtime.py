"""Per-config-entry runtime state, shared between __init__.py and platforms."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from .cycle_engine import CycleEngineRegistry
    from .led_controller import LedEffectRegistry
    from .plugin_manager import PluginManager
    from .tag_registry import TagDefinitionRegistry, TagRegistry


@dataclass
class FrameworkData:
    plugin_manager: PluginManager
    tag_definition_registry: TagDefinitionRegistry
    tag_registry: TagRegistry
    cycle_engine_registry: CycleEngineRegistry
    led_effect_registry: LedEffectRegistry
    add_entities_callbacks: dict[str, AddEntitiesCallback] = field(default_factory=dict)
    known_device_ids: set[str] = field(default_factory=set)
