"""Config flow: a single confirmation, there is nothing to configure yet."""

from __future__ import annotations

from homeassistant.config_entries import ConfigFlow

from .const import DOMAIN


class DashboardHistoryConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set the integration up from the user interface."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the single setup step."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is None:
            return self.async_show_form(step_id="user")
        return self.async_create_entry(title="Dashboard History", data={})
