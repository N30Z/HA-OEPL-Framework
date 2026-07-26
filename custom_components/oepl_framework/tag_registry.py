"""Tag hardware capability definitions (JSON-backed) and runtime tag discovery.

Adding support for a new OEPL tag model only requires dropping a new
``*.json`` file into ``tag_definitions/`` — no Python changes needed.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import OEPL_DOMAIN, OEPL_TAG_DISCOVERED_SIGNAL

_LOGGER = logging.getLogger(__name__)

TAG_DEFINITIONS_DIR = Path(__file__).parent / "tag_definitions"


@dataclass(frozen=True)
class DisplayInfo:
    """The e-paper panel's rendering capabilities."""

    width: int
    height: int
    color_mode: str
    colors: list[str]
    rotation_default: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DisplayInfo:
        return cls(
            width=data["width"],
            height=data["height"],
            color_mode=data["color_mode"],
            colors=list(data["colors"]),
            rotation_default=data.get("rotation_default", 0),
        )


@dataclass(frozen=True)
class ButtonMapping:
    """One physical button on the tag."""

    id: str
    trigger_type: str
    label: str
    default_action: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ButtonMapping:
        return cls(
            id=data["id"],
            trigger_type=data["trigger_type"],
            label=data.get("label", data["id"]),
            default_action=data.get("default_action", "next_page"),
        )


@dataclass(frozen=True)
class ButtonsInfo:
    count: int
    mapping: list[ButtonMapping] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ButtonsInfo:
        return cls(
            count=data.get("count", 0),
            mapping=[ButtonMapping.from_dict(m) for m in data.get("mapping", [])],
        )

    @property
    def trigger_types(self) -> list[str]:
        """OEPL device-trigger ``type`` values, capped at the declared count."""
        return [m.trigger_type for m in self.mapping[: self.count]]


@dataclass(frozen=True)
class StatusLedInfo:
    """The tag's optional RGB status LED, separate from the e-paper display."""

    present: bool = False
    controllable: bool = False
    control_service: str | None = None
    colors: list[str] = field(default_factory=list)
    color_rgb_map: dict[str, list[int]] = field(default_factory=dict)
    verified: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> StatusLedInfo:
        if not data:
            return cls()
        return cls(
            present=data.get("present", False),
            controllable=data.get("controllable", False),
            control_service=data.get("control_service"),
            colors=list(data.get("colors", [])),
            color_rgb_map={
                str(k): list(v) for k, v in data.get("color_rgb_map", {}).items()
            },
            verified=data.get("verified", False),
        )

    def rgb_for(self, color: str) -> list[int] | None:
        return self.color_rgb_map.get(color)


@dataclass(frozen=True)
class TagDefinition:
    """Full capability profile for one tag hardware model."""

    schema_version: int
    hardware_id: str
    model: str
    model_aliases: list[str]
    oepl_hw_type: int | None
    manufacturer: str
    display: DisplayInfo
    buttons: ButtonsInfo
    status_led: StatusLedInfo
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TagDefinition:
        return cls(
            schema_version=data.get("schema_version", 1),
            hardware_id=data["hardware_id"],
            model=data["model"],
            model_aliases=list(data.get("model_aliases", [])),
            oepl_hw_type=data.get("oepl_hw_type"),
            manufacturer=data.get("manufacturer", ""),
            display=DisplayInfo.from_dict(data["display"]),
            buttons=ButtonsInfo.from_dict(data.get("buttons", {})),
            status_led=StatusLedInfo.from_dict(data.get("features", {}).get("status_led")),
            metadata=data.get("metadata", {}),
        )

    def matches_model_string(self, model: str | None) -> bool:
        """Case-insensitive match against ``model`` or any declared alias."""
        if not model:
            return False
        candidates = {self.model.lower(), *(a.lower() for a in self.model_aliases)}
        return model.strip().lower() in candidates


class TagDefinitionRegistry:
    """Loads and indexes all bundled ``tag_definitions/*.json`` files."""

    def __init__(self, hass: HomeAssistant) -> None:
        self._hass = hass
        self._definitions: dict[str, TagDefinition] = {}

    @property
    def definitions(self) -> dict[str, TagDefinition]:
        return dict(self._definitions)

    async def async_load(self) -> None:
        self._definitions = await self._hass.async_add_executor_job(self._load_sync)

    def _load_sync(self) -> dict[str, TagDefinition]:
        definitions: dict[str, TagDefinition] = {}
        if not TAG_DEFINITIONS_DIR.is_dir():
            return definitions
        for path in sorted(TAG_DEFINITIONS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                definition = TagDefinition.from_dict(data)
            except (OSError, ValueError, KeyError) as err:
                _LOGGER.error("Failed to load tag definition %s: %s", path, err)
                continue
            definitions[definition.hardware_id] = definition
        return definitions

    def get(self, hardware_id: str) -> TagDefinition | None:
        return self._definitions.get(hardware_id)

    def match_device_model(self, model: str | None) -> TagDefinition | None:
        """Find the tag definition whose model/aliases match ``model``."""
        for definition in self._definitions.values():
            if definition.matches_model_string(model):
                return definition
        return None

    def match_hw_type(self, hw_type: int | None) -> TagDefinition | None:
        if hw_type is None:
            return None
        for definition in self._definitions.values():
            if definition.oepl_hw_type == hw_type:
                return definition
        return None


@dataclass(frozen=True)
class MatchedTag:
    """A discovered OEPL tag device matched to a :class:`TagDefinition`."""

    device_id: str
    tag_mac: str
    name: str
    tag_definition: TagDefinition


class TagRegistry:
    """Discovers OEPL tag devices in the HA device registry and matches them
    against known :class:`TagDefinition`\\ s.

    Matching is based on the *device registry* (``device.model``), not OEPL's
    internal runtime objects, since the device/entity registry is the stable,
    documented integration surface between custom components.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        definition_registry: TagDefinitionRegistry,
        overrides: dict[str, str] | None = None,
    ) -> None:
        self._hass = hass
        self._definitions = definition_registry
        self._overrides = overrides or {}
        self._matched: dict[str, MatchedTag] = {}
        self._unmatched: dict[str, str | None] = {}
        self._unsub_dispatcher = None

    @property
    def matched(self) -> dict[str, MatchedTag]:
        return dict(self._matched)

    @property
    def unmatched(self) -> dict[str, str | None]:
        """device_id -> reported model string (possibly None) for OEPL
        devices that could not be matched to a known tag definition."""
        return dict(self._unmatched)

    def set_override(self, device_id: str, hardware_id: str) -> None:
        self._overrides[device_id] = hardware_id

    @callback
    def async_scan(self) -> None:
        """Re-scan the device registry for OEPL tag devices."""
        device_registry = dr.async_get(self._hass)
        matched: dict[str, MatchedTag] = {}
        unmatched: dict[str, str | None] = {}

        for device in device_registry.devices.values():
            tag_mac = _extract_oepl_identifier(device.identifiers)
            if tag_mac is None:
                continue

            definition = None
            override_id = self._overrides.get(device.id)
            if override_id:
                definition = self._definitions.get(override_id)
            if definition is None:
                definition = self._definitions.match_device_model(device.model)

            if definition is None:
                if device.configuration_url:
                    # Almost certainly the OEPL Access Point (or another
                    # hub/gateway device), not a battery tag: gateway
                    # devices conventionally get a configuration_url (their
                    # web UI) in HA, individual tags don't. Not a hard
                    # guarantee — see docs/architecture.md — so this only
                    # keeps it out of the "unmatched tags" listing; it was
                    # never going to become a matched tag either way.
                    continue
                unmatched[device.id] = device.model
                continue

            matched[device.id] = MatchedTag(
                device_id=device.id,
                tag_mac=tag_mac,
                name=device.name_by_user or device.name or tag_mac,
                tag_definition=definition,
            )

        self._matched = matched
        self._unmatched = unmatched

    def async_setup_discovery_listener(self, on_discovered) -> None:
        """Best-effort fast path: OEPL dispatches a signal on new tags.

        This is an internal implementation detail of another custom
        component (not a documented public contract), so failures to attach
        are logged and swallowed rather than raised — periodic/manual
        rescans remain the primary discovery mechanism.
        """
        try:
            from homeassistant.helpers.dispatcher import async_dispatcher_connect

            self._unsub_dispatcher = async_dispatcher_connect(
                self._hass, OEPL_TAG_DISCOVERED_SIGNAL, lambda *_: on_discovered()
            )
        except Exception:  # noqa: BLE001 - defensive, see docstring
            _LOGGER.debug(
                "Could not attach to %s dispatcher signal; relying on manual/periodic rescans",
                OEPL_TAG_DISCOVERED_SIGNAL,
            )

    def async_unload(self) -> None:
        if self._unsub_dispatcher:
            self._unsub_dispatcher()
            self._unsub_dispatcher = None


def _extract_oepl_identifier(identifiers: set[tuple[str, str]]) -> str | None:
    for identifier in identifiers:
        # HA guarantees 2-tuples here, but this scans *every* device in the
        # registry (not just OEPL's), so defend against any oddly-shaped
        # identifier another integration might register.
        if len(identifier) != 2:
            continue
        domain, ident = identifier
        if domain == OEPL_DOMAIN:
            return ident
    return None
