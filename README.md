# OEPL Page Framework

A Home Assistant integration that turns [OpenEPaperLink](https://github.com/OpenEPaperLink/Home_Assistant_Integration)
e-paper tags into a **plugin-driven, multi-page display**.

- **Pages come from plugins.** A plugin is a small Python package that
  renders one or more "pages" (e.g. a clock, a sensor dashboard, a waste
  collection schedule). Install plugins from a curated list, or point at
  any GitHub repository — a "mini HACS" just for OEPL pages.
- **You decide which pages show on which tag**, and in what order.
- **Three ways to switch pages**, freely combinable per tag: an automatic
  time-based cycle, an HA `select`/`button` entity, or the tag's own
  physical buttons (if it has any).
- **New tag hardware is described in JSON**, not code. Drop in a new
  `tag_definitions/*.json` file and the framework "unlocks" the matching
  capabilities (resolution, button count, status-LED colors) for that
  model automatically.
- **Battery-status LED effect built in.** Press a button (HA-side or
  physical, depending on the tag) to flash the tag's RGB status LED green,
  yellow or red based on its current battery level, for ~5 seconds. More
  LED effects can be added the same way.

This integration does **not** talk to tags directly — it builds entirely
on top of the [OpenEPaperLink](https://github.com/OpenEPaperLink/Home_Assistant_Integration)
integration, which must already be installed and configured.

## Installation (HACS)

1. In HACS, add this repository as a custom repository (category:
   Integration), or install it directly if it has been added to the
   default HACS store.
2. Install "OEPL Page Framework" and restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration** and search
   for "OEPL Page Framework". Setup will fail with a clear message if
   OpenEPaperLink isn't installed/configured yet.

## Getting started

1. After setup, open the integration's **Configure** options.
2. **Manage tags** → pick a discovered tag → choose which plugin pages to
   show, whether to auto-cycle (and how often), and whether the tag's
   physical buttons should control page/LED actions.
3. **Manage plugins** → two bundled plugins are enabled by default: a
   demo clock/sensor page, and a **Debug Info** page (tag MAC, signal
   strength, battery, the OEPL Access Point's name/IP, and this Home
   Assistant instance's local IP — handy when setting up a new tag).
   Add more via a custom GitHub repository URL, or via **Discover
   plugins**, which lists any public repo under a GitHub owner named
   `HAOEPL-Plugin_*` (e.g. `HAOEPL-Plugin_AWSH`) so you don't have to add
   your own plugins one by one.
4. If a tag doesn't show up under "Manage tags", use **Rescan for tags**
   after confirming it's visible in the OpenEPaperLink integration itself.

## Supported tags

Tag capabilities are defined in
[`custom_components/oepl_framework/tag_definitions/`](custom_components/oepl_framework/tag_definitions/).
See [`docs/tag-definition-schema.md`](docs/tag-definition-schema.md) for
the schema and how to add a new tag model.

Currently bundled: **EL026H3BRA** (360×184, 2 buttons, 7-color status LED).

## Writing a plugin

See [`docs/plugin-api.md`](docs/plugin-api.md). The bundled
[`demo_plugin`](custom_components/oepl_framework/plugins/builtin/demo_plugin/)
is a minimal, working reference implementation.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for how the plugin
manager, tag registry and page-cycle engine fit together, and what still
needs to be verified against real hardware.

## Publishing to the HACS default store (optional, not done yet)

This repo currently ships as a HACS **custom repository** only. To submit it
to the official HACS default store later, two repo-owner actions are still
needed (see `.github/workflows/hacs.yml`, which skips these checks for now):

1. Add GitHub repository topics (Settings → General → Topics), e.g.
   `home-assistant`, `hacs-integration`.
2. Submit brand assets via a PR to
   [home-assistant/brands](https://github.com/home-assistant/brands).

## Development

```bash
pip install -r requirements_test.txt
ruff check custom_components tests
pytest
```
