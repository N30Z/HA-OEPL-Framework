from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oepl_framework.const import OEPL_DOMAIN
from custom_components.oepl_framework.diagnostics import (
    async_get_ap_info_for_tag,
    async_get_tag_battery_percent,
    async_get_tag_signal_strength,
    get_local_ha_ip,
)
from custom_components.oepl_framework.plugin_api import PageContext
from custom_components.oepl_framework.plugin_manager import PluginManager
from custom_components.oepl_framework.tag_registry import TagDefinitionRegistry


async def _setup_tag_with_ap(hass, *, with_battery=True, with_signal=True, with_ap=True):
    config_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    config_entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)

    ap_device = None
    if with_ap:
        ap_device = device_registry.async_get_or_create(
            config_entry_id=config_entry.entry_id,
            identifiers={(OEPL_DOMAIN, "AP-11:22:33:44:55:66")},
            name="Living Room AP",
            configuration_url="http://192.168.1.50",
        )

    tag_device = device_registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(OEPL_DOMAIN, "AA:BB:CC:DD:EE:FF")},
        model="EL026H3BRA",
    )
    if ap_device is not None:
        tag_device = device_registry.async_update_device(
            tag_device.id, via_device_id=ap_device.id
        )

    entity_registry = er.async_get(hass)
    if with_battery:
        battery_entry = entity_registry.async_get_or_create(
            "sensor",
            "open_epaper_link",
            "battery_unique_id",
            device_id=tag_device.id,
            original_device_class="battery",
        )
        hass.states.async_set(battery_entry.entity_id, "42")
    if with_signal:
        signal_entry = entity_registry.async_get_or_create(
            "sensor",
            "open_epaper_link",
            "rssi_unique_id",
            device_id=tag_device.id,
            original_device_class="signal_strength",
        )
        hass.states.async_set(
            signal_entry.entity_id, "-67", {"unit_of_measurement": "dBm"}
        )

    return tag_device


async def test_get_tag_battery_percent(hass):
    tag_device = await _setup_tag_with_ap(hass, with_signal=False, with_ap=False)
    assert await async_get_tag_battery_percent(hass, tag_device.id) == 42


async def test_get_tag_signal_strength(hass):
    tag_device = await _setup_tag_with_ap(hass, with_battery=False, with_ap=False)
    assert await async_get_tag_signal_strength(hass, tag_device.id) == "-67 dBm"


async def test_get_ap_info_for_tag_via_device(hass):
    tag_device = await _setup_tag_with_ap(hass, with_battery=False, with_signal=False)
    ap_info = await async_get_ap_info_for_tag(hass, tag_device.id)
    assert ap_info.name == "Living Room AP"
    assert ap_info.address == "AP-11:22:33:44:55:66"
    assert ap_info.ip_address == "192.168.1.50"


async def test_get_ap_info_for_tag_without_via_device(hass):
    tag_device = await _setup_tag_with_ap(
        hass, with_battery=False, with_signal=False, with_ap=False
    )
    ap_info = await async_get_ap_info_for_tag(hass, tag_device.id)
    assert ap_info.name is None
    assert ap_info.address is None
    assert ap_info.ip_address is None


def test_get_local_ha_ip_success(monkeypatch):
    class _FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def connect(self, _address):
            pass

        def getsockname(self):
            return ("192.168.1.23", 12345)

    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: _FakeSocket())
    assert get_local_ha_ip() == "192.168.1.23"


def test_get_local_ha_ip_returns_none_on_error(monkeypatch):
    class _FailingSocket:
        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def connect(self, _address):
            raise OSError("network unreachable")

    monkeypatch.setattr("socket.socket", lambda *args, **kwargs: _FailingSocket())
    assert get_local_ha_ip() is None


async def test_debug_plugin_renders_all_fields(hass, monkeypatch):
    await _setup_tag_with_ap(hass)
    monkeypatch.setattr(
        "custom_components.oepl_framework.plugins.builtin.debug_plugin.plugin.get_local_ha_ip",
        lambda: "192.168.1.10",
    )

    manager = PluginManager(hass)
    await manager.async_load()

    definition_registry = TagDefinitionRegistry(hass)
    await definition_registry.async_load()
    tag_definition = definition_registry.get("el026h3bra")

    ctx = PageContext(
        tag_id="AA:BB:CC:DD:EE:FF",
        tag_definition=tag_definition,
        hass=hass,
        options={},
    )
    elements = await manager.async_render_page("debug_plugin", "debug", ctx)

    assert all("type" in element for element in elements)
    values = " ".join(element["value"] for element in elements)
    assert "AA:BB:CC:DD:EE:FF" in values
    assert "-67 dBm" in values
    assert "42%" in values
    assert "Living Room AP" in values
    assert "192.168.1.50" in values
    assert "192.168.1.10" in values


async def test_debug_plugin_handles_missing_data_gracefully(hass, monkeypatch):
    monkeypatch.setattr(
        "custom_components.oepl_framework.plugins.builtin.debug_plugin.plugin.get_local_ha_ip",
        lambda: None,
    )
    manager = PluginManager(hass)
    await manager.async_load()

    definition_registry = TagDefinitionRegistry(hass)
    await definition_registry.async_load()
    tag_definition = definition_registry.get("el026h3bra")

    ctx = PageContext(
        tag_id="00:00:00:00:00:00",
        tag_definition=tag_definition,
        hass=hass,
        options={},
    )
    elements = await manager.async_render_page("debug_plugin", "debug", ctx)

    assert all("type" in element for element in elements)
    values = " ".join(element["value"] for element in elements)
    assert "n/a" in values
