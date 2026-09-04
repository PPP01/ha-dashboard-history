"""Config flow: one confirmation, and one switch afterwards."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback

from .const import DOMAIN, OPTION_DAILY_VERSIONS


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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The one thing there is to configure."""
        return DashboardHistoryOptionsFlow()


class DashboardHistoryOptionsFlow(OptionsFlow):
    """Whether versions are made without being asked for.

    No `__init__`, and that is not an omission. Since Home Assistant
    2024.11 the base class takes no config entry and offers
    `self.config_entry` as a property that looks it up through `hass` -
    which is not available inside `__init__` at all. Measured against
    2026.8.3 on 2026-09-04, because every older example on the internet
    assigns it there.
    """

    async def async_step_init(self, user_input=None):
        """Show the switch, and remember what it was set to."""
        if user_input is not None:
            # No update listener behind this, deliberately. Reloading the
            # entry would stop and restart the recorder, and its opening
            # pass over every dashboard takes about twenty seconds - an
            # absurd price for a checkbox. `Milestones` holds the entry
            # and reads its options at every save instead, so this takes
            # effect at the next one.
            #
            # And note for the day a second option arrives: this
            # replaces the options wholesale rather than merging. With
            # one required field that carries a default it is the same
            # thing; with two it would silently drop whichever the form
            # did not show. Then this needs
            # `data={**self.config_entry.options, **user_input}`.
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        OPTION_DAILY_VERSIONS,
                        default=self.config_entry.options.get(
                            OPTION_DAILY_VERSIONS, True
                        ),
                    ): bool
                }
            ),
        )
