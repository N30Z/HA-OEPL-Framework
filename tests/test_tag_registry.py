from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oepl_framework.const import OEPL_DOMAIN
from custom_components.oepl_framework.tag_registry import (
    TagDefinitionRegistry,
    TagRegistry,
    _extract_oepl_identifier,
)


async def test_load_bundled_definitions(hass):
    registry = TagDefinitionRegistry(hass)
    await registry.async_load()

    definition = registry.get("el026h3bra")
    assert definition is not None
    assert definition.display.width == 360
    assert definition.display.height == 184
    assert definition.buttons.count == 2
    assert definition.status_led.controllable is True
    assert set(definition.status_led.colors) == {
        "red",
        "green",
        "blue",
        "yellow",
        "cyan",
        "magenta",
        "white",
    }


async def test_match_device_model_exact_and_alias(hass):
    registry = TagDefinitionRegistry(hass)
    await registry.async_load()

    assert registry.match_device_model("EL026H3BRA") is not None
    assert registry.match_device_model("el026h3bra") is not None
    assert registry.match_device_model("Solum Newton 2.6") is not None
    # Confirmed on real hardware: this is the exact device.model string
    # OpenEPaperLink reports for the EL026H3BRA.
    assert registry.match_device_model('M3 2.6"') is not None
    assert registry.match_device_model("Unknown Tag XYZ") is None
    assert registry.match_device_model(None) is None


async def test_buttons_trigger_types_capped_at_count(hass):
    registry = TagDefinitionRegistry(hass)
    await registry.async_load()
    definition = registry.get("el026h3bra")
    assert definition.buttons.trigger_types == ["BUTTON1", "BUTTON2"]


async def test_tag_registry_matches_known_device(hass):
    definition_registry = TagDefinitionRegistry(hass)
    await definition_registry.async_load()

    config_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    config_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(OEPL_DOMAIN, "AA:BB:CC:DD:EE:FF")},
        model="EL026H3BRA",
        name="Kitchen Tag",
    )

    tag_registry = TagRegistry(hass, definition_registry)
    tag_registry.async_scan()

    matched = tag_registry.matched
    assert device.id in matched
    matched_tag = matched[device.id]
    assert matched_tag.tag_mac == "AA:BB:CC:DD:EE:FF"
    assert matched_tag.tag_definition.hardware_id == "el026h3bra"
    assert tag_registry.unmatched == {}


async def test_tag_registry_unmatched_device(hass):
    definition_registry = TagDefinitionRegistry(hass)
    await definition_registry.async_load()

    config_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    config_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(OEPL_DOMAIN, "11:22:33:44:55:66")},
        model="Some Unknown Tag",
    )

    tag_registry = TagRegistry(hass, definition_registry)
    tag_registry.async_scan()

    assert tag_registry.matched == {}
    assert tag_registry.unmatched[device.id] == "Some Unknown Tag"


async def test_tag_registry_excludes_hub_like_device_from_unmatched(hass):
    # Regression test: the OEPL Access Point is also an `open_epaper_link`
    # device with a model that never matches a tag definition, but it
    # shouldn't clutter the "unmatched tags" listing users see in the
    # options flow. It's identified heuristically by having a
    # configuration_url set (the standard HA convention for hub/gateway
    # devices), same as real APs reported by users.
    definition_registry = TagDefinitionRegistry(hass)
    await definition_registry.async_load()

    config_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    config_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(OEPL_DOMAIN, "AP-11:22:33:44:55:66")},
        model="Yellow AP",
        configuration_url="http://192.168.1.50",
    )

    tag_registry = TagRegistry(hass, definition_registry)
    tag_registry.async_scan()

    assert tag_registry.matched == {}
    assert tag_registry.unmatched == {}


async def test_tag_registry_override_takes_priority(hass):
    definition_registry = TagDefinitionRegistry(hass)
    await definition_registry.async_load()

    config_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    config_entry.add_to_hass(hass)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(OEPL_DOMAIN, "22:33:44:55:66:77")},
        model="Totally Unknown Model",
    )

    tag_registry = TagRegistry(hass, definition_registry)
    tag_registry.set_override(device.id, "el026h3bra")
    tag_registry.async_scan()

    assert tag_registry.matched[device.id].tag_definition.hardware_id == "el026h3bra"


def test_extract_oepl_identifier_ignores_malformed_tuples():
    # Regression test: a real HA instance can contain devices (from any
    # integration) with an identifier tuple that isn't a clean 2-tuple;
    # async_scan() must not crash while looking for the OEPL one.
    identifiers = {("some_other_domain",), (OEPL_DOMAIN, "AA:BB:CC:DD:EE:FF")}
    assert _extract_oepl_identifier(identifiers) == "AA:BB:CC:DD:EE:FF"


def test_extract_oepl_identifier_returns_none_when_absent():
    identifiers = {("some_other_domain", "abc")}
    assert _extract_oepl_identifier(identifiers) is None
