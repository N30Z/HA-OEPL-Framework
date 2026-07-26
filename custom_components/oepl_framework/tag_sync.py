"""Reconciles discovered/matched tags against stored config.

Used both on integration setup and after a manual rescan / options-flow
change, so newly discovered tags and edited tag options always go through
the same code path.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, OPT_TAGS
from .cycle_engine import TagCycleConfig
from .runtime import FrameworkData
from .tag_registry import MatchedTag

_LOGGER = logging.getLogger(__name__)


async def async_sync_tags(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rescan for OEPL tags, then create/update engines + entities."""
    data: FrameworkData = hass.data[DOMAIN][entry.entry_id]
    data.tag_registry.async_scan()

    tags_options: dict[str, Any] = entry.options.get(OPT_TAGS, {})

    for matched_tag in data.tag_registry.matched.values():
        tag_config_data = tags_options.get(matched_tag.tag_mac, {})
        config = TagCycleConfig.from_dict(tag_config_data)

        def _on_page_changed(page_id: str, tag_mac: str = matched_tag.tag_mac) -> None:
            _LOGGER.debug("Tag %s now showing page %s", tag_mac, page_id)

        await data.cycle_engine_registry.async_create_or_update(
            matched_tag.device_id,
            matched_tag.tag_mac,
            matched_tag.tag_definition,
            config,
            _on_page_changed,
        )

        if matched_tag.device_id not in data.known_device_ids:
            data.known_device_ids.add(matched_tag.device_id)
            _async_add_entities_for_tag(data, matched_tag)


def _async_add_entities_for_tag(data: FrameworkData, matched_tag: MatchedTag) -> None:
    from .button import NextPageButton, PreviousPageButton, RefreshPageButton, ShowBatteryLedButton
    from .select import OeplFrameworkPageSelect
    from .switch import OeplFrameworkAutoCycleSwitch

    if (add_select := data.add_entities_callbacks.get("select")) is not None:
        add_select([OeplFrameworkPageSelect(matched_tag, data)])

    if (add_switch := data.add_entities_callbacks.get("switch")) is not None:
        add_switch([OeplFrameworkAutoCycleSwitch(matched_tag, data)])

    if (add_button := data.add_entities_callbacks.get("button")) is not None:
        entities = [
            NextPageButton(matched_tag, data),
            PreviousPageButton(matched_tag, data),
            RefreshPageButton(matched_tag, data),
        ]
        if matched_tag.tag_definition.status_led.controllable:
            entities.append(ShowBatteryLedButton(matched_tag, data))
        add_button(entities)
