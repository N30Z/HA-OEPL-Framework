# Writing a plugin

A plugin is a small Python package with a `plugin.json` manifest and a
class implementing `OeplPlugin`. Both bundled and custom-installed
plugins are loaded as subpackages of this integration, so plugin code can
import the API directly from `custom_components.oepl_framework`.

## File layout

```
my_plugin/
├── plugin.json
├── __init__.py      # can be empty
└── plugin.py         # or whatever module your entry_point points at
```

## `plugin.json`

```json
{
  "id": "my_plugin",
  "name": "My Plugin",
  "version": "1.0.0",
  "min_framework_version": "0.1.0",
  "entry_point": "plugin:MyPlugin",
  "pages": [
    { "id": "main", "name": "Main Page" }
  ],
  "description": "What this plugin does.",
  "author": "you",
  "homepage": "https://github.com/you/my_plugin"
}
```

- `id` must match `^[a-z0-9_]+$` and is also the folder name once installed.
- `entry_point` is `"<module>:<ClassName>"`, relative to your plugin's own
  package (so `"plugin:MyPlugin"` means `plugin.py`'s `MyPlugin` class).
- `pages` here is informational for the manifest/registry; the
  authoritative list at runtime is whatever `get_pages()` returns (it can
  be dynamic, e.g. one page per configured sensor).

## The `OeplPlugin` interface

```python
from custom_components.oepl_framework.plugin_api import (
    OeplPlugin, PageContext, PageDescriptor,
)


class MyPlugin(OeplPlugin):
    id = "my_plugin"
    version = "1.0.0"

    async def async_setup(self) -> None:
        """Called once when the plugin is enabled. Register listeners here."""

    def get_pages(self) -> list[PageDescriptor]:
        return [PageDescriptor("main", "Main Page")]

    async def async_render_page(self, page_id: str, ctx: PageContext) -> list[dict]:
        width = ctx.tag_definition.display.width
        height = ctx.tag_definition.display.height
        return [
            {
                "type": "text",
                "value": "Hello from my plugin!",
                "x": 8, "y": 8, "size": 24, "color": "black",
            }
        ]

    async def async_unload(self) -> None:
        """Called on disable/removal. Clean up listeners here."""
```

`async_render_page` must return a list of
[`drawcustom` element dicts](https://github.com/OpenEPaperLink/Home_Assistant_Integration/blob/main/docs/drawcustom/supported_types.md)
(text, rectangle, line, icon, qrcode, plot, ...) — this list is passed
**unmodified** as the `payload` of the `open_epaper_link.drawcustom`
service call, so you write directly against OEPL's own drawing vocabulary.
`ctx.tag_definition.display.{width,height,colors}` tells you what the
target tag can actually show.

## `PageContext`

| Field | Meaning |
|---|---|
| `tag_id` | The tag's MAC (OEPL's device identifier). |
| `tag_definition` | Full hardware capability profile (resolution, colors, buttons, LED). |
| `hass` | The `HomeAssistant` instance — read any entity state you need. |
| `options` | Per-tag-per-page options set by the user in the options flow (e.g. which entity to show). |

## Pushing an update outside the normal cycle

If your plugin's data changes (e.g. a sensor updated) and you don't want
to wait for the next scheduled cycle tick, call:

```python
await self.runtime.async_request_page_refresh(ctx.tag_id)
```

This re-renders and pushes the tag's *currently active* page — it's a
no-op if that page doesn't belong to your plugin.

## Installing a custom plugin

Two ways, both via the integration's options flow, both under **Manage
plugins**:

- **Add custom plugin repository**: enter the GitHub `owner`/`repo`/`ref`
  (branch, tag, or commit) directly and confirm you trust the repository.
- **Discover plugins**: enter a GitHub owner once; the framework lists
  every public repo under that owner whose name starts with
  `HAOEPL-Plugin_` (the recommended naming convention for standalone OEPL
  Page Framework plugin repos, e.g. `HAOEPL-Plugin_AWSH`,
  `HAOEPL-Plugin_Bambulab`) and lets you install any of them with one
  click, instead of adding each one by hand. The owner is remembered for
  next time.

Either way, this downloads the repo's tarball, validates `plugin.json`,
and imports the plugin — the same trust model as HACS custom repositories:
you are explicitly opting in to running third-party code.

Naming your own plugin repos `HAOEPL-Plugin_<Something>` is recommended
so they're picked up by discovery automatically; it is not required for
"Add custom plugin repository", which works with any repo name.

## Bundled reference plugins

Two plugins ship with the framework itself as working examples:

- [`demo_plugin`](../custom_components/oepl_framework/plugins/builtin/demo_plugin/)
  — a minimal clock/sensor page, the smallest possible complete plugin.
- [`debug_plugin`](../custom_components/oepl_framework/plugins/builtin/debug_plugin/)
  — a diagnostics page (tag MAC, signal strength, battery, the linked OEPL
  Access Point's name/IP, and this Home Assistant instance's own local
  IP), useful when setting up or troubleshooting a tag. It demonstrates
  reading beyond `ctx` — the device/entity registries and local network
  info — via the shared helpers in
  [`diagnostics.py`](../custom_components/oepl_framework/diagnostics.py)
  (`async_get_tag_battery_percent`, `async_get_tag_signal_strength`,
  `async_get_ap_info_for_tag`, `get_local_ha_ip`), which your own plugin
  can reuse instead of re-implementing the same registry lookups.

## Real-world examples (planned, not part of this repo)

Separate plugin repositories, following the `HAOEPL-Plugin_*` naming
convention above so they're picked up by "Discover plugins" automatically:

- `HAOEPL-Plugin_AWSH` — porting
  [N30Z/Awsh_homeassistent](https://github.com/N30Z/Awsh_homeassistent)'s
  German waste-collection schedule + multi-layout e-paper rendering; the
  intended reference for a non-trivial plugin (per-sensor dynamic pages,
  external API data, multiple layout options).
- `HAOEPL-Plugin_Bambulab` — a planned Bambu Lab 3D-printer status plugin.

Neither is built as part of this framework PR.
