"""The Dashboard History integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from .const import DOMAIN
from .snapshot import async_get_all_configs

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set the integration up.

    Nothing here may raise: a broken history is an inconvenience, a broken
    Home Assistant start is not.
    """
    hass.data.setdefault(DOMAIN, {})

    async def _debug_snapshot(call: ServiceCall) -> dict:
        """Report what the integration can currently see.

        Kept permanently. On any later hunt for a fault this answers the
        first question - whether the dashboards are visible at all.
        """
        configs = await async_get_all_configs(hass)
        return {
            "count": len(configs),
            "dashboards": {
                key: {"views": len(config.get("views") or [])}
                for key, config in sorted(configs.items())
            },
        }

    hass.services.async_register(
        DOMAIN,
        "debug_snapshot",
        _debug_snapshot,
        supports_response=SupportsResponse.ONLY,
    )

    _LOGGER.debug("Dashboard History set up")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear the integration down."""
    hass.data.pop(DOMAIN, None)
    return True
