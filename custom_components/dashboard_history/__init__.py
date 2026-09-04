"""The Dashboard History integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import panel, websocket_api
from .capture import HistoryCapture
from .milestones import Milestones
from .const import DOMAIN, REPO_DIRNAME
from .services import async_register
from .store import HistoryStore

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set the integration up.

    Nothing here may raise: a broken history is an inconvenience, a broken
    Home Assistant start is not.
    """
    store = HistoryStore(Path(hass.config.path(REPO_DIRNAME)))
    capture = HistoryCapture(hass, store)
    milestones = Milestones(hass, store, entry)
    hass.data[DOMAIN] = {
        "store": store,
        "capture": capture,
        "milestones": milestones,
    }

    # Registered before the recording starts, on purpose: if the repository
    # cannot be created, an interface that answers with the reason is more
    # use than one that is not there at all.
    await async_register(hass)
    websocket_api.async_register(hass)
    await panel.async_register(hass)

    # Guarded, because the hard rule says so: a repository that cannot be
    # created - a read-only configuration folder, a full disk - costs the
    # history, and nothing else. It must not cost the start.
    try:
        await hass.async_add_executor_job(store.ensure)
        await capture.async_start()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")

    # Its own guard, separate from the recorder's: a repository that
    # could not be created leaves nothing to mark, but a recorder that
    # started perfectly well must not lose its versions because one
    # dashboard's tag failed.
    try:
        await milestones.async_lay_the_floor()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not make its first versions")

    # Only now, and see `async_arm` for why: before the floor is laid,
    # the first automatic version of a dashboard would be numbered
    # v0.0.1 instead of v1.0.1.
    milestones.async_arm()

    _LOGGER.debug("Dashboard History set up")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear the integration down."""
    panel.async_unregister(hass)
    data = hass.data.pop(DOMAIN, None)
    if data and (milestones := data.get("milestones")) is not None:
        milestones.async_disarm()
    if data and (capture := data.get("capture")) is not None:
        await capture.async_stop()
    return True
