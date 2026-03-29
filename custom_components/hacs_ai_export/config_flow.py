"""Config flow for HACS AI Export."""

from __future__ import annotations

from homeassistant import config_entries

from .const import DOMAIN, NAME


class HacsAiExportConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for HACS AI Export."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict | None = None,
    ) -> config_entries.ConfigFlowResult:
        """Create a single-instance config entry."""
        del user_input
        if self._async_current_entries():
            return self.async_abort(reason="already_configured")
        return self.async_create_entry(title=NAME, data={})
