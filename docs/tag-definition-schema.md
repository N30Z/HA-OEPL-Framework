# Tag definition schema

Every file in `custom_components/oepl_framework/tag_definitions/*.json`
describes one tag hardware model. Adding a new supported tag is just
adding a new file here — no Python changes needed.

```json
{
  "schema_version": 1,
  "hardware_id": "el026h3bra",
  "model": "EL026H3BRA",
  "model_aliases": ["EL026H3BRA", "Newton 2.6", "Solum Newton 2.6"],
  "oepl_hw_type": null,
  "manufacturer": "Solum",
  "display": {
    "width": 360,
    "height": 184,
    "color_mode": "bwry",
    "colors": ["black", "white", "red", "yellow"],
    "rotation_default": 0
  },
  "buttons": {
    "count": 2,
    "mapping": [
      { "id": "button_1", "trigger_type": "BUTTON1", "label": "Button 1", "default_action": "next_page" },
      { "id": "button_2", "trigger_type": "BUTTON2", "label": "Button 2", "default_action": "show_battery_led" }
    ]
  },
  "features": {
    "status_led": {
      "present": true,
      "controllable": true,
      "control_service": "open_epaper_link.setled",
      "colors": ["red", "green", "blue", "yellow", "cyan", "magenta", "white"],
      "color_rgb_map": {
        "red": [255, 0, 0], "green": [0, 255, 0], "blue": [0, 0, 255],
        "yellow": [255, 255, 0], "cyan": [0, 255, 255],
        "magenta": [255, 0, 255], "white": [255, 255, 255]
      },
      "verified": false
    }
  },
  "metadata": {
    "info_pages_marketing": 7,
    "notes": "free-form, not used by any logic"
  }
}
```

## Field reference

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | int | Bump if the schema evolves in a breaking way. |
| `hardware_id` | string (`^[a-z0-9_]+$`) | Internal key; should match the filename. |
| `model` | string | Canonical model name. |
| `model_aliases` | list[string] | Extra strings matched case-insensitively against the OEPL device's `model` field. Add whatever OEPL actually reports here once known. |
| `oepl_hw_type` | int \| null | OEPL's internal numeric hardware-type id, if/when known — the strongest possible match key. Leave `null` until confirmed. |
| `manufacturer` | string | Informational. |
| `display.width` / `.height` | int | Panel resolution in pixels. |
| `display.color_mode` | string | Informational label (e.g. `"bwry"` = black/white/red/yellow). |
| `display.colors` | list[string] | Colors plugins may use, in `drawcustom`'s own vocabulary (`black`, `white`, `red`, `yellow`, ...). |
| `display.rotation_default` | int | Default rotation (0/90/180/270) passed to `drawcustom`. |
| `buttons.count` | int | Number of physical buttons. Caps how many `buttons.mapping` entries are actually wired up. |
| `buttons.mapping[].trigger_type` | string | The OEPL device-trigger `type` value (`BUTTON1`..`BUTTON10`) fired in `open_epaper_link_event`. |
| `buttons.mapping[].default_action` | string | Action name run when this button is pressed and no per-tag override is configured (see `cycle_engine.ActionRegistry`). |
| `features.status_led.present` | bool | Whether the tag has an RGB status LED at all (separate from the e-paper display). |
| `features.status_led.controllable` | bool | Whether the framework should create LED entities/services for this model. Set `false` to opt a model out entirely, without touching any Python code. |
| `features.status_led.control_service` | string | The HA service used to drive it (currently always `open_epaper_link.setled`). |
| `features.status_led.colors` | list[string] | Named colors this LED can actually show. LED effects only use colors from this list. |
| `features.status_led.color_rgb_map` | dict[string, [r,g,b]] | RGB triplet for each named color. |
| `features.status_led.verified` | bool | Whether the above has been confirmed against real hardware. Keep `false` until you've tested it — greppable TODO marker. |
| `metadata` | dict | Free-form, informational only, never read by any logic (e.g. marketing spec sheet numbers). |

## Matching order

When a new OEPL tag device is discovered, `TagDefinitionRegistry` matches
it in this order:

1. A manual per-device override set by the user (for tags that couldn't
   auto-match).
2. `device.model` (from the HA device registry) against every
   definition's `model` / `model_aliases` (case-insensitive).
3. (Available but not yet wired into discovery by default) `oepl_hw_type`
   exact match, once that's populated for a given definition.

Unmatched tags show up under **Manage tags → unmatched** in the options
flow relevant screens with their reported `device.model`, so you can tell
what alias string to add.
