from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hacs_ai_export.const import DOMAIN, SERVICE_GENERATE_CONTEXT


async def _create_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return hass.config_entries.async_entries(DOMAIN)[0]


async def test_service_is_registered_on_entry_setup_and_removed_on_unload(hass):
    entry = await _create_entry(hass)
    assert hass.services.has_service(DOMAIN, SERVICE_GENERATE_CONTEXT)

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service(DOMAIN, SERVICE_GENERATE_CONTEXT)
