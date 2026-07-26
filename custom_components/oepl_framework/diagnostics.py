"""Shared helpers for reading tag/AP/network diagnostic info.

Used by the built-in debug plugin and the battery-status LED effect.
Field availability depends on how OpenEPaperLink exposes a given tag/AP
(AP-gateway vs. BLE-only mode) — see docs/architecture.md for what still
needs confirming against a live setup.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass

from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import OEPL_DOMAIN


def _find_entity_state(
    hass: HomeAssistant, device_id: str, *, domain: str, device_class: str
) -> State | None:
    entity_registry = er.async_get(hass)
    for entity in er.async_entries_for_device(entity_registry, device_id):
        if entity.domain != domain:
            continue
        is_match = (
            entity.original_device_class == device_class
            or entity.device_class == device_class
        )
        if not is_match:
            continue
        state = hass.states.get(entity.entity_id)
        if state is not None:
            return state
    return None


async def async_get_tag_battery_percent(hass: HomeAssistant, device_id: str) -> int | None:
    """Best-effort lookup of a tag's battery percentage.

    Matches any ``sensor`` entity on the device with device_class
    ``battery`` — this is the standard HA convention and is expected to
    match OEPL's battery sensor, but should be confirmed against a live
    OEPL setup (see docs/architecture.md verification notes).
    """
    state = _find_entity_state(hass, device_id, domain="sensor", device_class="battery")
    if state is None:
        return None
    try:
        return int(float(state.state))
    except (TypeError, ValueError):
        return None


async def async_get_tag_signal_strength(hass: HomeAssistant, device_id: str) -> str | None:
    """Best-effort lookup of a tag's radio signal strength, formatted with unit.

    Matches any ``sensor`` entity on the device with device_class
    ``signal_strength`` (e.g. RSSI) — the standard HA convention.
    """
    state = _find_entity_state(hass, device_id, domain="sensor", device_class="signal_strength")
    if state is None:
        return None
    unit = state.attributes.get("unit_of_measurement", "")
    return f"{state.state} {unit}".strip()


@dataclass(frozen=True)
class ApInfo:
    """Best-effort info about the OEPL Access Point a tag is linked to."""

    name: str | None = None
    address: str | None = None
    ip_address: str | None = None


async def async_get_ap_info_for_tag(hass: HomeAssistant, device_id: str) -> ApInfo:
    """Best-effort lookup of the OEPL Access Point a tag is linked to.

    Uses the device registry's ``via_device`` relationship — the standard
    HA convention for "this device talks through that hub device" — which
    is expected to match how OEPL links a tag to its AP, but has not been
    confirmed against a live setup. Returns an empty :class:`ApInfo` if no
    such relationship is found (e.g. the tag's own device, not its AP).
    """
    device_registry = dr.async_get(hass)
    tag_device = device_registry.async_get(device_id)
    if tag_device is None or tag_device.via_device_id is None:
        return ApInfo()

    ap_device = device_registry.async_get(tag_device.via_device_id)
    if ap_device is None:
        return ApInfo()

    address = next(
        (ident for domain, ident in ap_device.identifiers if domain == OEPL_DOMAIN),
        None,
    )
    ip_address = None
    if ap_device.configuration_url:
        ip_address = ap_device.configuration_url.split("://", 1)[-1].split("/", 1)[0]

    return ApInfo(
        name=ap_device.name_by_user or ap_device.name,
        address=address,
        ip_address=ip_address,
    )


def get_local_ha_ip() -> str | None:
    """Best-effort outbound local IP address of this Home Assistant host.

    Uses a UDP "connect" (no packets are actually sent, it's purely a
    kernel-side route lookup) to ask the OS which local interface/address
    would be used to reach the network — a common dependency-free trick.
    This does blocking socket I/O, so it must be called via
    ``hass.async_add_executor_job``, never directly on the event loop.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("10.255.255.255", 1))
            return sock.getsockname()[0]
        except OSError:
            return None
