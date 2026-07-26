"""Bundled demo plugin: a clock page and a generic HA-sensor page.

Serves as the minimal, working reference implementation of the Plugin API
(see docs/plugin-api.md). Plugin authors can copy this file's shape as a
starting point.
"""

from __future__ import annotations

from typing import Any

from custom_components.oepl_framework.plugin_api import OeplPlugin, PageContext, PageDescriptor


class DemoPlugin(OeplPlugin):
    id = "demo_plugin"
    version = "1.0.0"

    def get_pages(self) -> list[PageDescriptor]:
        return [
            PageDescriptor("clock", "Clock", icon="mdi:clock-outline"),
            PageDescriptor("sensor", "Sensor Value", icon="mdi:gauge"),
        ]

    async def async_render_page(self, page_id: str, ctx: PageContext) -> list[dict[str, Any]]:
        width = ctx.tag_definition.display.width
        height = ctx.tag_definition.display.height

        if page_id == "clock":
            return self._render_clock(width, height)
        if page_id == "sensor":
            return self._render_sensor(ctx, width, height)
        raise ValueError(f"Unknown page_id: {page_id}")

    def _render_clock(self, width: int, height: int) -> list[dict[str, Any]]:
        return [
            {
                "type": "text",
                "value": "{{ now().strftime('%H:%M') }}",
                "font": "default",
                "x": width // 2,
                "y": height // 2,
                "size": 40,
                "anchor": "mm",
                "color": "black",
            }
        ]

    def _render_sensor(self, ctx: PageContext, width: int, height: int) -> list[dict[str, Any]]:
        entity_id = ctx.options.get("entity_id", "sensor.date")
        state = ctx.hass.states.get(entity_id)
        value = state.state if state is not None else "N/A"
        return [
            {
                "type": "text",
                "value": entity_id,
                "x": 8,
                "y": 8,
                "size": 16,
                "color": "black",
            },
            {
                "type": "text",
                "value": value,
                "x": 8,
                "y": 32,
                "size": 28,
                "color": "black",
            },
        ]
