from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType

from custom_components.hacs_ai_export.const import DOMAIN, NAME


async def test_config_flow_creates_single_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == NAME
    assert result["data"] == {}

    result_second = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    assert result_second["type"] is FlowResultType.ABORT
    assert result_second["reason"] == "already_configured"
