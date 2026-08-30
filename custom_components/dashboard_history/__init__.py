"""The Dashboard History integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse

from .capture import HistoryCapture
from .const import DOMAIN, REPO_DIRNAME
from .services import async_register
from .snapshot import async_get_all_configs
from .store import HistoryStore

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set the integration up.

    Nothing here may raise: a broken history is an inconvenience, a broken
    Home Assistant start is not.
    """
    store = HistoryStore(Path(hass.config.path(REPO_DIRNAME)))
    capture = HistoryCapture(hass, store)
    hass.data[DOMAIN] = {"store": store, "capture": capture}

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

    # Registered before the recording starts, on purpose: if the repository
    # cannot be created, a service that answers with the reason is more use
    # than a service that is not there at all.
    await async_register(hass)

    # Guarded, because the hard rule says so: a repository that cannot be
    # created - a read-only configuration folder, a full disk - costs the
    # history, and nothing else. It must not cost the start.
    try:
        await hass.async_add_executor_job(store.ensure)
        await capture.async_start()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")

    _LOGGER.debug("Dashboard History set up")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear the integration down."""
    data = hass.data.pop(DOMAIN, None)
    if data and (capture := data.get("capture")) is not None:
        await capture.async_stop()
    return True
