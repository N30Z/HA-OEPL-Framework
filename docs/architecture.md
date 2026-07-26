# Architecture

## Layering

```
plugins (bundled + custom)
        │  implement OeplPlugin (plugin_api.py)
        ▼
PluginManager  ──────────────► get_available_pages() / async_render_page()
        ▲
        │ used by
        │
TagCycleEngine (one per matched tag) ───► renderer.py ───► open_epaper_link.drawcustom
        │                                      │
        │ button/timer/HA-entity triggers      └────────► open_epaper_link.setled (LED)
        ▼
CycleEngineRegistry
        ▲
        │ config from entry.options["tags"][tag_mac]  (see const.py OPT_* keys)
        │
config_flow.py (OeplFrameworkOptionsFlow)

TagDefinitionRegistry (tag_definitions/*.json) ──► matches ──► TagRegistry
        (hardware capability data)                              (HA device registry scan)
```

`tag_sync.py::async_sync_tags()` is the single place that reconciles
"what tags does OEPL currently report" against "what does the user want
configured", both on integration setup and after any options-flow change
or manual rescan. It creates/updates one `TagCycleEngine` per matched tag
and adds framework entities (`select`/`button`/`switch`) the first time a
tag is seen.

## Why we don't depend on OEPL's internal `Hub`/`runtime_data` objects

OpenEPaperLink's Home Assistant integration exposes internal Python
objects (`Hub`, `OpenEPaperLinkBLERuntimeData`, ...) that are convenient
but are **not** a documented public API — they can change in any OEPL
release without notice. Instead, this framework only depends on:

1. The **HA device/entity registry** — `device.model`, `device.identifiers`,
   entity `device_class` — the stable, documented surface between any two
   custom components.
2. OEPL's **documented services** — `drawcustom`, `setled`, and friends.
3. The **event bus** — `open_epaper_link_event` (`data.device_id`,
   `data.type`) for physical button presses, and (best-effort, wrapped in
   `try/except`) the `open_epaper_link_tag_discovered` dispatcher signal as
   a fast-path hint to rescan sooner.

If any of these OEPL internals change, the framework degrades to relying
on periodic/manual rescans rather than breaking outright.

## The LED "duration" problem

`open_epaper_link.setled` has no explicit duration field — a pattern is
described by `repeats × (flash_count × flash_speed + delay)`. To reliably
get a ~5 second effect (e.g. the battery-status LED), `led_controller.py`
computes an approximate `repeats` value for the desired duration **and**
schedules an explicit follow-up `setled` call with `mode: "off"` via
`homeassistant.helpers.event.async_call_later`, rather than trusting the
pattern math to be exact.

## Known limitations of this MVP

- No drag-and-drop page reordering in the options flow; page order follows
  selection order. A companion Lovelace card is a natural follow-up.
- The `switch.<tag>_auto_cycle` runtime toggle is not itself persisted
  back into config-entry options (it always starts from the configured
  `auto_cycle_enabled` value on reload).
- Per-button custom action mapping (`button_action_map`) is stored in
  config but has no dedicated options-flow UI yet — it falls back to each
  tag definition's `default_action` per button.

## Verification checklist (needs a live OpenEPaperLink setup + the real tag)

- [ ] Confirm the exact `device.model` string OpenEPaperLink reports for
      the EL026H3BRA, and/or its numeric `hw_type` — fill into
      `tag_definitions/el026h3bra.json` (`model_aliases`, `oepl_hw_type`).
- [ ] Confirm whether the tag runs in AP-gateway mode (uses `setled`) or
      BLE-only mode (may expose a `light.<tag>_led` entity instead).
- [ ] Confirm `setled` actually drives this tag's RGB LED as expected; set
      `features.status_led.verified: true` once confirmed (or
      `controllable: false` if not supported).
- [ ] Confirm which sensor entity/device_class exposes battery percentage
      for OEPL tags, used by `led_controller.async_get_tag_battery_percent`.
- [ ] Confirm `BUTTON1`/`BUTTON2` map to the physically-expected buttons.
- [ ] Visually verify a real `drawcustom` payload on the 360×184 panel
      (dithering, "accent" color behavior).
