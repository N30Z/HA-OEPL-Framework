"""Status-LED effects, independent of the page/plugin system.

The tag's RGB status LED is a hardware capability like the display, so it is
driven by the framework's core rather than by a plugin. Effects are
registered in an :class:`LedEffectRegistry` so more can be added later
without touching the button-action wiring.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later

from .const import DEFAULT_LED_EFFECT_DURATION_SECONDS, DEFAULT_LED_THRESHOLDS
from .renderer import async_flash_led, async_led_off

if TYPE_CHECKING:
    from .tag_registry import TagDefinition

_LOGGER = logging.getLogger(__name__)

# Semantic fallback order if the tag doesn't report supporting the exact
# color we'd like to show (e.g. a tag with only red/green/blue).
_COLOR_FALLBACKS = {
    "yellow": ["yellow", "orange", "white"],
    "green": ["green", "cyan", "white"],
    "red": ["red", "magenta", "white"],
}


@dataclass(frozen=True)
class LedEffectContext:
    hass: HomeAssistant
    device_id: str
    tag_definition: TagDefinition
    options: dict[str, Any]


class LedEffect(ABC):
    """A named, self-contained status-LED behavior."""

    name: str

    @abstractmethod
    async def async_run(self, ctx: LedEffectContext) -> None:
        """Execute the effect. Must be resilient to a non-LED-capable tag."""


class LedEffectRegistry:
    """Holds all known LED effects, built-in and future/plugin-registered."""

    def __init__(self) -> None:
        self._effects: dict[str, LedEffect] = {}

    def register(self, effect: LedEffect) -> None:
        self._effects[effect.name] = effect

    def get(self, name: str) -> LedEffect | None:
        return self._effects.get(name)

    def names(self) -> list[str]:
        return list(self._effects)


class BatteryStatusLedEffect(LedEffect):
    """Flashes the LED green/yellow/red for the tag's battery level."""

    name = "battery_status"

    def __init__(self, duration_seconds: float = DEFAULT_LED_EFFECT_DURATION_SECONDS) -> None:
        self.duration_seconds = duration_seconds

    async def async_run(self, ctx: LedEffectContext) -> None:
        status_led = ctx.tag_definition.status_led
        if not status_led.controllable:
            _LOGGER.debug(
                "Tag %s has no controllable status LED; skipping battery_status effect",
                ctx.device_id,
            )
            return

        percent = await async_get_tag_battery_percent(ctx.hass, ctx.device_id)
        if percent is None:
            _LOGGER.debug(
                "No battery-percentage sensor found for device %s; skipping battery_status effect",
                ctx.device_id,
            )
            return

        thresholds = ctx.options.get("thresholds", DEFAULT_LED_THRESHOLDS)
        color = _color_for_percent(percent, thresholds)
        color = _resolve_supported_color(color, status_led.colors)
        if color is None:
            _LOGGER.debug(
                "Tag %s status LED does not support any color for the battery_status effect",
                ctx.device_id,
            )
            return
        rgb = status_led.rgb_for(color)
        if rgb is None:
            return

        duration = ctx.options.get("duration_seconds", self.duration_seconds)
        flash_speed = 0.2
        flash_count = 4
        delay = 0.1
        repeats = max(1, round(duration / (flash_count * flash_speed + delay)))

        await async_flash_led(
            ctx.hass,
            ctx.device_id,
            rgb,
            repeats=repeats,
            flash_speed=flash_speed,
            flash_count=flash_count,
            delay=delay,
        )

        async def _turn_off(_now: Any) -> None:
            await async_led_off(ctx.hass, ctx.device_id)

        async_call_later(ctx.hass, duration, _turn_off)


def _color_for_percent(percent: int, thresholds: dict[str, int]) -> str:
    if percent >= thresholds.get("green", DEFAULT_LED_THRESHOLDS["green"]):
        return "green"
    if percent >= thresholds.get("yellow", DEFAULT_LED_THRESHOLDS["yellow"]):
        return "yellow"
    return "red"


def _resolve_supported_color(color: str, supported: list[str]) -> str | None:
    if color in supported:
        return color
    for fallback in _COLOR_FALLBACKS.get(color, []):
        if fallback in supported:
            return fallback
    return supported[0] if supported else None


async def async_get_tag_battery_percent(hass: HomeAssistant, device_id: str) -> int | None:
    """Best-effort lookup of a tag's battery percentage.

    Matches any ``sensor`` entity on the device with device_class
    ``battery`` — this is the standard HA convention and is expected to
    match OEPL's battery sensor, but should be confirmed against a live
    OEPL setup (see docs/architecture.md verification notes).
    """
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_device(entity_registry, device_id):
        if entity.domain != "sensor":
            continue
        is_battery = (
            entity.original_device_class == "battery"
            or entity.device_class == "battery"
            or "battery" in entity.entity_id.lower()
        )
        if not is_battery:
            continue
        state = hass.states.get(entity.entity_id)
        if state is None:
            continue
        try:
            return int(float(state.state))
        except (TypeError, ValueError):
            continue
    return None
