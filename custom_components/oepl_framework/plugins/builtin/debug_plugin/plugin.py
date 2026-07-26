"""Bundled debug plugin: a single diagnostics page for a tag.

Shows the tag's MAC, radio signal strength, battery level, the OEPL
Access Point it's linked to (name/address/IP), and this Home Assistant
instance's local IP — useful when setting up a new tag or troubleshooting
connectivity. Field availability depends on how OEPL exposes a given
tag/AP; missing values show as "n/a" rather than crashing the render.
"""

from __future__ import annotations

from typing import Any

from homeassistant.helpers import device_registry as dr

from custom_components.oepl_framework.const import OEPL_DOMAIN
from custom_components.oepl_framework.diagnostics import (
    ApInfo,
    async_get_ap_info_for_tag,
    async_get_tag_battery_percent,
    async_get_tag_signal_strength,
    get_local_ha_ip,
)
from custom_components.oepl_framework.plugin_api import OeplPlugin, PageContext, PageDescriptor


class DebugPlugin(OeplPlugin):
    id = "debug_plugin"
    version = "1.0.0"

    def get_pages(self) -> list[PageDescriptor]:
        return [PageDescriptor("debug", "Debug Info", icon="mdi:bug-outline")]

    async def async_render_page(self, page_id: str, ctx: PageContext) -> list[dict[str, Any]]:
        if page_id != "debug":
            raise ValueError(f"Unknown page_id: {page_id}")

        hass = ctx.hass
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(identifiers={(OEPL_DOMAIN, ctx.tag_id)})
        device_id = device.id if device else None

        if device_id:
            battery = await async_get_tag_battery_percent(hass, device_id)
            signal = await async_get_tag_signal_strength(hass, device_id)
            ap_info = await async_get_ap_info_for_tag(hass, device_id)
        else:
            battery = signal = None
            ap_info = ApInfo()

        ha_ip = await hass.async_add_executor_job(get_local_ha_ip)

        lines = [
            ("Tag MAC", ctx.tag_id),
            ("Signal", signal or "n/a"),
            ("Battery", f"{battery}%" if battery is not None else "n/a"),
            ("AP", ap_info.name or ap_info.address or "n/a"),
            ("AP IP", ap_info.ip_address or "n/a"),
            ("HA IP", ha_ip or "n/a"),
        ]

        return self._build_elements(ctx, lines)

    def _build_elements(
        self, ctx: PageContext, lines: list[tuple[str, str]]
    ) -> list[dict[str, Any]]:
        height = ctx.tag_definition.display.height
        font_size = 14
        line_height = max(font_size + 6, height // (len(lines) + 1))

        elements: list[dict[str, Any]] = [
            {
                "type": "text",
                "value": "Debug Info",
                "x": 4,
                "y": 2,
                "size": font_size + 2,
                "color": "black",
            }
        ]
        y = line_height
        for label, value in lines:
            elements.append(
                {
                    "type": "text",
                    "value": f"{label}: {value}",
                    "x": 4,
                    "y": min(y, max(0, height - font_size)),
                    "size": font_size,
                    "color": "black",
                }
            )
            y += line_height
        return elements
