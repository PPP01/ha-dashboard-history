"""The Dashboard History integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import panel, websocket_api
from .capture import HistoryCapture
from .const import DOMAIN, REPO_DIRNAME
from .milestones import Milestones
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

    # Armed before the recorder rather than after it, and `async_arm`
    # carries the whole reason: `capture.async_start()` announces its
    # opening pass before it returns, so a marker armed afterwards is
    # deaf to everything that pass recorded. Nothing it can hear exists
    # until the repository does, so arming ahead of `store.ensure` costs
    # nothing and is outside the guard for the same reason - subscribing
    # to a bus cannot fail in a way that matters here.
    milestones.async_arm()

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
    #
    # After the recorder, and that way round for good: a floor marks a
    # *recorded* state, and on a first start there is nothing in the
    # repository at all until the opening pass has written it. It may now
    # run beside a day mark raised by that same pass - `_async_floor_for`
    # takes the marking lock so the two cannot both claim one name.
    try:
        await milestones.async_lay_the_floor()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not make its first versions")

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
