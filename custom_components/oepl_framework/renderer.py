"""Pushes rendered pages and LED patterns to a tag via the OEPL integration.

This module is the framework's *only* point of contact with OEPL's actual
service calls (``drawcustom`` / ``setled``), so a future OEPL schema change
only needs to be adapted here.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .const import OEPL_DOMAIN, OEPL_SERVICE_DRAWCUSTOM, OEPL_SERVICE_SETLED

_LOGGER = logging.getLogger(__name__)


async def async_build_and_push(
    hass: HomeAssistant,
    device_id: str,
    elements: list[dict[str, Any]],
    *,
    background: str = "white",
    rotate: int = 0,
    dither: int = 2,
    ttl: int = 60,
) -> None:
    """Push a rendered page to a tag via ``open_epaper_link.drawcustom``."""
    await hass.services.async_call(
        OEPL_DOMAIN,
        OEPL_SERVICE_DRAWCUSTOM,
        {
            "payload": elements,
            "background": background,
            "rotate": rotate,
            "dither": dither,
            "ttl": ttl,
            "dry-run": False,
        },
        target={"device_id": device_id},
        blocking=False,
    )


async def async_flash_led(
    hass: HomeAssistant,
    device_id: str,
    color_rgb: list[int],
    *,
    brightness: int = 4,
    repeats: int = 2,
    flash_speed: float = 0.2,
    flash_count: int = 4,
    delay: float = 0.1,
) -> None:
    """Flash the tag's status LED once in a single color via ``setled``."""
    await hass.services.async_call(
        OEPL_DOMAIN,
        OEPL_SERVICE_SETLED,
        {
            "mode": "flash",
            "brightness": brightness,
            "repeats": repeats,
            "color1": list(color_rgb),
            "flashSpeed1": flash_speed,
            "flashCount1": flash_count,
            "delay1": delay,
        },
        target={"device_id": device_id},
        blocking=False,
    )


async def async_led_off(hass: HomeAssistant, device_id: str) -> None:
    """Explicitly stop any running LED pattern.

    Sent as a fail-safe follow-up after a timed effect, since ``setled``
    doesn't take an explicit duration — see docs/architecture.md.
    """
    await hass.services.async_call(
        OEPL_DOMAIN,
        OEPL_SERVICE_SETLED,
        {"mode": "off"},
        target={"device_id": device_id},
        blocking=False,
    )
