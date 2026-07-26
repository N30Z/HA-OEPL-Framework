"""Constants for the OEPL Page Framework integration."""

DOMAIN = "oepl_framework"

# The OpenEPaperLink integration this framework builds on top of.
OEPL_DOMAIN = "open_epaper_link"
OEPL_EVENT = "open_epaper_link_event"
OEPL_TAG_DISCOVERED_SIGNAL = "open_epaper_link_tag_discovered"

OEPL_SERVICE_DRAWCUSTOM = "drawcustom"
OEPL_SERVICE_SETLED = "setled"

PLATFORMS = ["select", "button", "switch"]

# Config entry options keys
OPT_TAGS = "tags"
OPT_PAGE_SEQUENCE = "page_sequence"
OPT_AUTO_CYCLE_ENABLED = "auto_cycle_enabled"
OPT_CYCLE_INTERVAL_SECONDS = "cycle_interval_seconds"
OPT_PHYSICAL_BUTTONS_ENABLED = "physical_buttons_enabled"
OPT_BUTTON_TRIGGER_TYPES = "button_trigger_types"
OPT_BUTTON_ACTION_MAP = "button_action_map"
OPT_LED_THRESHOLDS = "led_thresholds"

DEFAULT_CYCLE_INTERVAL_SECONDS = 30
DEFAULT_LED_THRESHOLDS = {"green": 60, "yellow": 20}
DEFAULT_LED_EFFECT_DURATION_SECONDS = 5

# Known OEPL device-trigger "type" values for physical buttons, in priority order.
OEPL_BUTTON_TRIGGER_TYPES = [f"BUTTON{i}" for i in range(1, 11)]

ACTION_NEXT_PAGE = "next_page"
ACTION_PREVIOUS_PAGE = "previous_page"
ACTION_SHOW_BATTERY_LED = "show_battery_led"

STORAGE_VERSION = 1
STORAGE_KEY_PLUGINS = f"{DOMAIN}_plugins"

# Plugin auto-discovery by GitHub naming convention, e.g. repos named
# "HAOEPL-Plugin_AWSH" under a given owner.
OPT_PLUGIN_DISCOVERY_OWNER = "plugin_discovery_owner"
PLUGIN_REPO_PREFIX = "HAOEPL-Plugin_"
