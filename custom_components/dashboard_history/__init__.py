"""The Dashboard History integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import panel, websocket_api
from .capture import HistoryCapture
from .const import DOMAIN, EVENT_HISTORY_UPDATED, REPO_DIRNAME
from .coordinator import MeasurementCoordinator
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
    coordinator = MeasurementCoordinator(hass, store)
    hass.data[DOMAIN] = {
        "store": store,
        "capture": capture,
        "milestones": milestones,
        "coordinator": coordinator,
    }

    # Registered before the recording starts, on purpose: if the repository
    # cannot be created, an interface that answers with the reason is more
    # use than one that is not there at all.
    await async_register(hass)
    websocket_api.async_register(hass)
    await panel.async_register(hass)

    async def _remeasure(_event) -> None:
        await coordinator.async_request_refresh()

    # Through `entry.async_on_unload`, so that unloading drops it. A
    # listener remembered in a second place is a listener forgotten in
    # one of them, and after a reload it would measure against a store
    # nobody uses any more.
    entry.async_on_unload(hass.bus.async_listen(EVENT_HISTORY_UPDATED, _remeasure))

    # Armed before the recorder rather than after it, and `async_arm`
    # carries the whole reason: the opening pass announces what it
    # records, so a marker armed after it is deaf to all of it. Nothing
    # it can hear exists until the repository does, so arming ahead of
    # `store.ensure` costs nothing and is outside the guard for the same
    # reason - subscribing to a bus cannot fail in a way that matters
    # here.
    milestones.async_arm()

    # Guarded, because the hard rule says so: a repository that cannot be
    # created - a read-only configuration folder, a full disk - costs the
    # history, and nothing else. It must not cost the start.
    try:
        await hass.async_add_executor_job(store.ensure)
        # Subscribing only, and that is the whole of what is awaited
        # here: it closes the window the opening pass opens, and it
        # costs nothing.
        capture.async_start()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")

    # The slow half, off the start. Measured on the test bench on
    # 2026-09-07 over 45 dashboards and 4454 commits: the opening pass
    # took 6.2 s of a 7.3 s setup, and Home Assistant said so in the log
    # - "Waiting for integrations to complete setup: dashboard_history".
    # The hard rule is that nothing here blocks the start, and awaiting
    # this broke it: a history is worth waiting for, a start is not.
    #
    # A background task of the config entry rather than a loose one, so
    # that unloading the entry cancels it. Half a recorded pass is not a
    # problem - the next start records what this one did not reach, and
    # `write_snapshot` compares against HEAD rather than against the
    # working tree exactly so that an interrupted run repairs itself.
    entry.async_create_background_task(
        hass, _async_open(hass, capture, milestones, coordinator), f"{DOMAIN} opening pass"
    )

    _LOGGER.debug("Dashboard History set up")
    return True


async def _async_open(
    hass: HomeAssistant,
    capture: HistoryCapture,
    milestones: Milestones,
    coordinator: MeasurementCoordinator,
) -> None:
    """The opening pass and the first versions, off the start.

    Each half keeps the guard it had when this ran inside
    `async_setup_entry`, and for the same reasons. `CancelledError` is
    not among what they catch - it inherits from `BaseException`, so an
    entry unloaded mid-pass ends the task rather than being logged as a
    failure of it.
    """
    try:
        await capture.async_opening_pass()
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

    # Last, and deliberately: the first measurement of an empty history
    # is an honest zero, but a measurement taken after the opening pass
    # is the one somebody wants to see on the integration page.
    await coordinator.async_refresh()

    _LOGGER.debug("Dashboard History finished its opening pass")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear the integration down."""
    panel.async_unregister(hass)
    data = hass.data.pop(DOMAIN, None)
    if data and (milestones := data.get("milestones")) is not None:
        milestones.async_disarm()
    if data and (capture := data.get("capture")) is not None:
        await capture.async_stop()
    return True
