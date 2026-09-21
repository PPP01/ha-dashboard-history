"""The Dashboard History integration."""

from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import panel, websocket_api
from .capture import HistoryCapture
from .const import DOMAIN, EVENT_HISTORY_UPDATED, PLATFORMS, REPO_DIRNAME
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
    coordinator = MeasurementCoordinator(hass, entry, store)
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

    # The platform goes up, the first refresh is not waited for. The
    # reason is two screens further down in this file: the opening pass
    # was moved into a background task on 2026-09-07 because it cost
    # 6.2 s of a 7.3 s setup and Home Assistant said so in the log.
    # Sensors that read `unknown` for a minute are harmless; a start
    # that waits for a directory walk is not.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

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
        hass,
        _async_open(hass, entry, store, capture, milestones, coordinator),
        f"{DOMAIN} opening pass",
    )

    _LOGGER.debug("Dashboard History set up")
    return True


async def _async_open(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: HistoryStore,
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
    # First, and off the awaited start for the same reason the opening
    # pass below is: `garbage_collect` alone measured 4.5-6.6 s on the
    # test bench, and the object-lock sweep folded into this call costs
    # time proportional to the whole history's size - nothing may add
    # that to `async_setup_entry`. Safe to run on every call to
    # `_async_open`, including every reload, without a gate of its own:
    # `repair_pending_forget` blocks on the same lock a live write would
    # already be holding, rather than racing it (decision 21, correction
    # 4). Ahead of the opening pass on purpose, though not for
    # correctness - every write in store.py refuses on its own while a
    # checkpoint is pending - only so a crashed forget does not turn the
    # opening pass into a wall of refused writes in the log before it
    # gets repaired.
    try:
        await hass.async_add_executor_job(store.repair_pending_forget)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not repair an interrupted forget")

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

    # And only now does the recorder's event start a measurement. The
    # opening pass fires `EVENT_HISTORY_UPDATED` for every dashboard it
    # records, and a listener armed before it would measure a history
    # that is still being written - twice, once at the first event and
    # once when the debouncer's cooldown runs out - only for the line
    # above to replace both answers a moment later. Two cold
    # measurements of a half-written repository, about seven seconds of
    # executor and disk work, thrown away on arrival.
    #
    # `entry.async_on_unload` all the same: it holds whatever is
    # registered by the time the entry unloads, and a listener
    # remembered in a second place is a listener forgotten in one of
    # them.
    #
    # A plain listener, and no wrapper around it. What used to make this
    # a `@callback` starting its own background task now sits where it
    # belongs, on the coordinator's debouncer: with `immediate=False`
    # this call only arms a timer and returns, and with
    # `background=True` the measurement it eventually starts is
    # untracked. See `coordinator.py`.
    async def _remeasure(_event) -> None:
        await coordinator.async_request_refresh()

    entry.async_on_unload(hass.bus.async_listen(EVENT_HISTORY_UPDATED, _remeasure))

    _LOGGER.debug("Dashboard History finished its opening pass")


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear the integration down.

    The platform goes first and the runtime data only if it went: the
    entities read from `hass.data`, so emptying it before they are gone
    leaves them reading into nothing. This is the first entity platform
    of this integration, which is why there was no unload for one until
    now - without it, a reload leaves entities and an event listener
    hanging on a store nobody uses any more.

    The listener itself needs nothing here. It was registered through
    `entry.async_on_unload`, so Home Assistant drops it at exactly this
    point, and a second place to remember it is a second place to forget
    it.
    """
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    panel.async_unregister(hass)
    data = hass.data.pop(DOMAIN, None)
    if data and (milestones := data.get("milestones")) is not None:
        milestones.async_disarm()
    if data and (capture := data.get("capture")) is not None:
        await capture.async_stop()
    return True
