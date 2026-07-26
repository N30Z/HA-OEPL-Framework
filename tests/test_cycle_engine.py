from datetime import timedelta

import pytest
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.oepl_framework.const import OEPL_DOMAIN, OEPL_EVENT
from custom_components.oepl_framework.cycle_engine import (
    TagCycleConfig,
    TagCycleEngine,
    build_default_action_registry,
)
from custom_components.oepl_framework.led_controller import (
    BatteryStatusLedEffect,
    LedEffectRegistry,
)
from custom_components.oepl_framework.plugin_manager import PluginManager
from custom_components.oepl_framework.tag_registry import TagDefinitionRegistry


@pytest.fixture
def drawcustom_calls(hass):
    calls = []

    async def _handle(call):
        calls.append(dict(call.data))

    hass.services.async_register(OEPL_DOMAIN, "drawcustom", _handle)
    hass.services.async_register(OEPL_DOMAIN, "setled", _handle)
    return calls


@pytest.fixture
async def plugin_manager(hass):
    manager = PluginManager(hass)
    await manager.async_load()
    return manager


@pytest.fixture
async def tag_definition(hass):
    registry = TagDefinitionRegistry(hass)
    await registry.async_load()
    return registry.get("el026h3bra")


def _make_engine(hass, plugin_manager, tag_definition, config, device_id="device_1"):
    led_registry = LedEffectRegistry()
    led_registry.register(BatteryStatusLedEffect(duration_seconds=1))
    action_registry = build_default_action_registry(led_registry)
    return TagCycleEngine(
        hass,
        device_id,
        "AA:BB:CC:DD:EE:FF",
        tag_definition,
        plugin_manager,
        config,
        action_registry,
    )


async def test_next_previous_page_wraparound(
    hass, plugin_manager, tag_definition, drawcustom_calls
):
    config = TagCycleConfig(
        page_sequence=[
            {"plugin_id": "demo_plugin", "page_id": "clock", "options": {}},
            {"plugin_id": "demo_plugin", "page_id": "sensor", "options": {}},
        ],
        physical_buttons_enabled=False,
    )
    engine = _make_engine(hass, plugin_manager, tag_definition, config)
    await engine.async_setup()

    assert engine.current_page["page_id"] == "clock"
    await engine.async_next_page()
    assert engine.current_page["page_id"] == "sensor"
    await engine.async_next_page()
    assert engine.current_page["page_id"] == "clock"  # wrapped around
    await engine.async_previous_page()
    assert engine.current_page["page_id"] == "sensor"

    await hass.async_block_till_done()
    assert len(drawcustom_calls) == 3
    await engine.async_unload()


async def test_set_page_by_id(hass, plugin_manager, tag_definition, drawcustom_calls):
    config = TagCycleConfig(
        page_sequence=[
            {"plugin_id": "demo_plugin", "page_id": "clock", "options": {}},
            {"plugin_id": "demo_plugin", "page_id": "sensor", "options": {}},
        ],
        physical_buttons_enabled=False,
    )
    engine = _make_engine(hass, plugin_manager, tag_definition, config)
    await engine.async_setup()

    await engine.async_set_page("sensor")
    assert engine.current_page["page_id"] == "sensor"
    await engine.async_unload()


async def test_auto_cycle_timer_advances_page(
    hass, plugin_manager, tag_definition, drawcustom_calls
):
    config = TagCycleConfig(
        page_sequence=[
            {"plugin_id": "demo_plugin", "page_id": "clock", "options": {}},
            {"plugin_id": "demo_plugin", "page_id": "sensor", "options": {}},
        ],
        auto_cycle_enabled=True,
        cycle_interval_seconds=30,
        physical_buttons_enabled=False,
    )
    engine = _make_engine(hass, plugin_manager, tag_definition, config)
    await engine.async_setup()

    assert engine.current_page["page_id"] == "clock"

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()

    assert engine.current_page["page_id"] == "sensor"
    await engine.async_unload()


async def test_auto_cycle_switch_toggle(hass, plugin_manager, tag_definition, drawcustom_calls):
    config = TagCycleConfig(
        page_sequence=[
            {"plugin_id": "demo_plugin", "page_id": "clock", "options": {}},
            {"plugin_id": "demo_plugin", "page_id": "sensor", "options": {}},
        ],
        auto_cycle_enabled=False,
        cycle_interval_seconds=30,
        physical_buttons_enabled=False,
    )
    engine = _make_engine(hass, plugin_manager, tag_definition, config)
    await engine.async_setup()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()
    assert engine.current_page["page_id"] == "clock"  # timer wasn't running

    await engine.async_set_auto_cycle_enabled(True)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=61))
    await hass.async_block_till_done()
    assert engine.current_page["page_id"] == "sensor"

    await engine.async_unload()


async def test_physical_button_next_page(hass, plugin_manager, tag_definition, drawcustom_calls):
    config = TagCycleConfig(
        page_sequence=[
            {"plugin_id": "demo_plugin", "page_id": "clock", "options": {}},
            {"plugin_id": "demo_plugin", "page_id": "sensor", "options": {}},
        ],
        physical_buttons_enabled=True,
    )
    engine = _make_engine(hass, plugin_manager, tag_definition, config)
    await engine.async_setup()

    # BUTTON1's default_action for el026h3bra is "next_page".
    hass.bus.async_fire(OEPL_EVENT, {"device_id": "device_1", "type": "BUTTON1"})
    await hass.async_block_till_done()

    assert engine.current_page["page_id"] == "sensor"
    await engine.async_unload()


async def test_physical_button_ignores_other_devices_and_unknown_types(
    hass, plugin_manager, tag_definition, drawcustom_calls
):
    config = TagCycleConfig(
        page_sequence=[
            {"plugin_id": "demo_plugin", "page_id": "clock", "options": {}},
            {"plugin_id": "demo_plugin", "page_id": "sensor", "options": {}},
        ],
        physical_buttons_enabled=True,
    )
    engine = _make_engine(hass, plugin_manager, tag_definition, config)
    await engine.async_setup()

    hass.bus.async_fire(OEPL_EVENT, {"device_id": "some_other_device", "type": "BUTTON1"})
    hass.bus.async_fire(OEPL_EVENT, {"device_id": "device_1", "type": "GPIO"})
    await hass.async_block_till_done()

    assert engine.current_page["page_id"] == "clock"
    await engine.async_unload()


async def test_show_battery_led_action_flashes_led_then_turns_off(
    hass, plugin_manager, tag_definition, drawcustom_calls
):
    config_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    config_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(OEPL_DOMAIN, "AA:BB:CC:DD:EE:FF")},
        model="EL026H3BRA",
    )

    entity_registry = er.async_get(hass)
    entity_entry = entity_registry.async_get_or_create(
        "sensor",
        "open_epaper_link",
        "battery_unique_id",
        device_id=device.id,
        original_device_class="battery",
    )
    hass.states.async_set(entity_entry.entity_id, "15")

    config = TagCycleConfig(page_sequence=[], physical_buttons_enabled=True)
    engine = _make_engine(hass, plugin_manager, tag_definition, config, device_id=device.id)
    await engine.async_setup()

    # BUTTON2's default_action for el026h3bra is "show_battery_led".
    hass.bus.async_fire(OEPL_EVENT, {"device_id": device.id, "type": "BUTTON2"})
    await hass.async_block_till_done()

    assert len(drawcustom_calls) == 1
    assert drawcustom_calls[0]["mode"] == "flash"
    assert drawcustom_calls[0]["color1"] == [255, 0, 0]  # 15% battery -> red

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=2))
    await hass.async_block_till_done()

    assert len(drawcustom_calls) == 2
    assert drawcustom_calls[1]["mode"] == "off"

    await engine.async_unload()


async def test_show_battery_led_noop_without_battery_sensor(
    hass, plugin_manager, tag_definition, drawcustom_calls
):
    config = TagCycleConfig(page_sequence=[], physical_buttons_enabled=True)
    engine = _make_engine(hass, plugin_manager, tag_definition, config)
    await engine.async_setup()

    hass.bus.async_fire(OEPL_EVENT, {"device_id": "device_1", "type": "BUTTON2"})
    await hass.async_block_till_done()

    assert drawcustom_calls == []
    await engine.async_unload()
