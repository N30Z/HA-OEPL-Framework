from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oepl_framework.const import DOMAIN, OEPL_DOMAIN


async def test_setup_flow_aborts_without_oepl(hass):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "abort"
    assert result["reason"] == "oepl_not_installed"


async def test_setup_flow_creates_entry_when_oepl_present(hass):
    oepl_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    oepl_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "form"
    assert result["step_id"] == "user"

    result2 = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result2["type"] == "create_entry"
    assert result2["title"] == "OEPL Page Framework"


async def test_setup_flow_single_instance(hass):
    oepl_entry = MockConfigEntry(domain=OEPL_DOMAIN)
    oepl_entry.add_to_hass(hass)

    existing = MockConfigEntry(domain=DOMAIN, unique_id=DOMAIN)
    existing.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
