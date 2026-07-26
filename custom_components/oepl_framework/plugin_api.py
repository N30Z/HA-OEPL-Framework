"""Public API surface that OEPL Page Framework plugins are written against.

Any plugin's entry-point class must subclass :class:`OeplPlugin`. Both bundled
(``plugins/builtin``) and installed custom plugins (``installed_plugins``) are
imported as subpackages of this integration, so plugin code can simply do::

    from custom_components.oepl_framework.plugin_api import (
        OeplPlugin, PageContext, PageDescriptor,
    )
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .tag_registry import TagDefinition


@dataclass(frozen=True)
class PageDescriptor:
    """A single page a plugin can render."""

    id: str
    name: str
    icon: str | None = None


@dataclass(frozen=True)
class PageContext:
    """Everything a plugin needs to render one page for one tag."""

    tag_id: str
    tag_definition: TagDefinition
    hass: HomeAssistant
    options: dict[str, Any] = field(default_factory=dict)


class PluginRuntime(Protocol):
    """Services the framework offers back to a running plugin instance."""

    hass: HomeAssistant

    async def async_request_page_refresh(self, tag_id: str) -> None:
        """Ask the framework to re-render+push the active page of a tag now.

        No-ops if the currently active page on that tag does not belong to
        this plugin.
        """

    def get_config_entry_options(self) -> dict[str, Any]:
        """Return the framework's current config-entry options dict."""


class OeplPlugin(ABC):
    """Base class every plugin's entry-point class must implement."""

    id: str
    version: str

    def __init__(self, runtime: PluginRuntime) -> None:
        self.runtime = runtime

    async def async_setup(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called once when the plugin is enabled. Register listeners here."""

    @abstractmethod
    def get_pages(self) -> list[PageDescriptor]:
        """Return the pages this plugin can render (static or computed)."""

    @abstractmethod
    async def async_render_page(
        self, page_id: str, ctx: PageContext
    ) -> list[dict[str, Any]]:
        """Render one page.

        Must return a list of drawcustom element dicts (each with at least a
        ``"type"`` key), already sized/positioned for
        ``ctx.tag_definition.display.width`` / ``.height``. The returned list
        is passed unmodified as the ``payload`` of the
        ``open_epaper_link.drawcustom`` service call.
        """

    async def async_unload(self) -> None:  # noqa: B027 - optional lifecycle hook
        """Called on disable/removal. Clean up any listeners here."""
