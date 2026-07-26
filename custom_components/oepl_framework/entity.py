"""Shared base entity for all framework entities.

Entities attach to the *existing* OEPL tag device (by reusing its device
identifiers) rather than creating a separate device, so they show up
alongside OEPL's own sensors/controls on the same device page.
"""

from __future__ import annotations

from homeassistant.helpers.entity import DeviceInfo, Entity

from .const import DOMAIN, OEPL_DOMAIN
from .tag_registry import MatchedTag


class OeplFrameworkTagEntity(Entity):
    """Base class for entities that belong to one matched tag."""

    _attr_has_entity_name = True

    def __init__(self, matched_tag: MatchedTag, entity_key: str) -> None:
        self._matched_tag = matched_tag
        self._attr_unique_id = f"{DOMAIN}_{matched_tag.tag_mac}_{entity_key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(OEPL_DOMAIN, matched_tag.tag_mac)},
        )

    @property
    def device_id(self) -> str:
        return self._matched_tag.device_id

    @property
    def tag_mac(self) -> str:
        return self._matched_tag.tag_mac
