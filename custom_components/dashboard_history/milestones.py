"""Versions that appear without anybody having asked for one.

Decision 17 makes the simple mode show versions and nothing else, and a
mode that shows only versions is no use on a dashboard that has none.
The person it is built for is exactly the person who will never make
one, so two kinds appear by themselves:

* **A floor**, for every live dashboard that has a recorded state and no
  version at all. That is the state to come back to before anything has
  happened.
* **A day mark**, on the state that was there before the first change of
  a new day - by definition the last state of the day before.

Nothing in here may raise into Home Assistant. A version that could not
be made is a mark that is missing; a save that failed because of it
would be a state that is gone.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.util import dt as dt_util

from . import operations
from . import versions as versioning
from .const import EVENT_HISTORY_UPDATED, OPTION_DAILY_VERSIONS
from .store import Change, HistoryStore

_LOGGER = logging.getLogger(__name__)


class Milestones:
    """Makes the versions nobody asked for."""

    def __init__(
        self, hass: HomeAssistant, store: HistoryStore, entry: ConfigEntry
    ) -> None:
        self._hass = hass
        self._store = store
        # The entry itself, never a copy of its options: Home Assistant
        # replaces the options object when somebody changes them, so
        # holding the entry means a change takes effect at the next save
        # instead of at the next restart. No update listener, and
        # deliberately none - reloading would restart the recorder and
        # cost a full pass over every dashboard for the sake of a
        # checkbox.
        self._entry = entry
        self._unsubscribe = None
        # One day mark at a time. Two changes arriving close together
        # would otherwise both read the same predecessor, both find it
        # unmarked, and both tag it - two versions on one state, one
        # second apart, neither of them wrong on its own.
        self._marking = asyncio.Lock()

    # -- the floor -----------------------------------------------------

    async def async_lay_the_floor(self) -> list[str]:
        """Give every live dashboard without a version its `v1.0.0`.

        Written as a rule rather than as a one-off, so it is idempotent
        by construction: a dashboard that already has a version is
        skipped, a second start makes nothing, and one created later
        gets its floor at the next start. A flag in the config entry
        would have been the alternative, and it would drift away from
        what the repository actually holds.

        Live dashboards only, read from the tree at HEAD. A deleted one
        has left that tree; its newest entry is the deletion, and there
        is no state there to come back to - `async_create_version`
        refuses it, and not asking saves a warning per deleted dashboard
        on every single start.
        """
        made: list[str] = []
        try:
            live = await self._hass.async_add_executor_job(
                self._store.list_dashboards
            )
        except Exception:  # noqa: BLE001 - a missing mark, never a broken start
            _LOGGER.exception("Could not list the dashboards to give a version to")
            return made
        for key in live:
            name = await self._async_floor_for(key)
            if name is not None:
                made.append(name)
        if made:
            _LOGGER.info("Made a first version: %s", ", ".join(made))
        return made

    async def _async_floor_for(self, key: str) -> str | None:
        """One dashboard's floor, or None if it needs none and if it fails.

        One dashboard at a time, each in its own guard: the same shape
        `capture._async_write` uses, and for the same reason - a failure
        on the first must not cost the rest.
        """
        try:
            found = await self._hass.async_add_executor_job(
                self._store.list_versions, key
            )
            # A *numbered* version, not any tag at all. `list_versions`
            # deliberately carries hand-made and unreadable names too -
            # the design record wants those visible - and `candidates`
            # skips them when counting up. A dashboard whose only tag is
            # `heizung/wichtig` would otherwise be passed over here at
            # every start and take `v0.0.1` as its first number.
            if versioning.latest(key, [v.name for v in found]):
                return None
            newest = await self._hass.async_add_executor_job(
                self._store.list_changes, key, 1
            )
            if not newest:
                # Nothing recorded yet. Nothing to mark, and nothing wrong:
                # a dashboard that has never been saved has no state.
                return None
            made = await self._async_make(key, "major", newest[0])
            if made is None:
                # Unlike the day mark, this path only ever sees live
                # dashboards - `list_dashboards` reads the tree at HEAD -
                # so a refusal here is a real obstacle, and one that
                # comes back at every start. Worth saying out loud.
                _LOGGER.warning("Could not give %s a first version", key)
            return made
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Could not make the first version of %s", key)
            return None

    # -- making one ----------------------------------------------------

    async def _async_make(
        self, key: str, level: str, change: Change
    ) -> str | None:
        """Mark one recorded state, through the fence a person goes through.

        `operations.async_create_version` rather than the store directly:
        that is where the refusals live - an unknown revision, a state
        that is not in the tree, a name git cannot hold beside the others
        - and a second way in would be a second set of them to keep
        right.

        The time zone is read here, at every call. `DEFAULT_TIME_ZONE` is
        a module variable that Home Assistant fills in from the user's
        configuration while it starts; held on to, it would be whatever
        it was when this object was built.
        """
        zone = dt_util.DEFAULT_TIME_ZONE
        answer = await operations.async_create_version(
            self._hass,
            self._store,
            key,
            level=level,
            title=versioning.day_title(change.timestamp, zone),
            description=versioning.automatic_description(),
            revision=change.revision,
        )
        created = answer.get("created")
        if created is None:
            # An answer, not a crash - that operation reports every
            # refusal this way. Debug rather than warning: the ordinary
            # case here is a dashboard whose newest entry is its own
            # deletion, and that is not a fault.
            _LOGGER.debug("No automatic version for %s: %s", key, answer.get("error"))
            return None
        return created

    # -- the day mark --------------------------------------------------

    @callback
    def async_arm(self) -> None:
        """Start marking the end of a day when the history grows.

        Armed *after* the floor is laid, and that order is the whole
        reason this is a call of its own. `candidates` counts up from the
        highest version that exists, so on a dashboard with none the
        first automatic version would be `v0.0.1` rather than `v1.0.1`.
        The recorder's opening pass has already announced itself by the
        time `async_start` returns, so nothing it recorded can reach
        here - the first pass lays the floor, everything after it may
        raise day marks.

        `EVENT_HISTORY_UPDATED` rather than `lovelace_updated`: it is
        fired once the commit exists and it names the dashboards that
        actually changed. The snapshot taken just before a restore is
        recorded with `announce=False` and so never arrives here, which
        is right - the dialog in front of a restore asks about that state
        itself.
        """
        if self._unsubscribe is not None:
            return
        self._unsubscribe = self._hass.bus.async_listen(
            EVENT_HISTORY_UPDATED, self._handle_recorded
        )

    @callback
    def async_disarm(self) -> None:
        """Stop listening."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _handle_recorded(self, event: Event) -> None:
        """React without holding up the bus, or the recorder's write lock.

        The event is fired from inside the recorder's write section. Doing
        git work here would run it under a lock this module has no
        business holding - the same reason `capture._handle_event` hands
        its work to a task rather than doing it where it stands.
        """
        for key in event.data.get("dashboards") or []:
            # Bound to the config entry and not to `hass`: Home Assistant
            # cancels an entry's background tasks when it unloads, so a
            # mark in flight cannot outlive the instance whose lock it
            # holds. Without that, a reload leaves the old task running
            # against the old lock while the new instance holds a new
            # one - and two versions land on one state, which is the
            # very thing the lock is here to prevent.
            self._entry.async_create_background_task(
                self._hass,
                self._async_mark_day(key),
                name=f"dashboard_history mark day {key}",
            )

    async def _async_mark_day(self, key: str) -> None:
        """Mark the state that was there before this new day started."""
        try:
            async with self._marking:
                if not self._entry.options.get(OPTION_DAILY_VERSIONS, True):
                    return
                newest = await self._hass.async_add_executor_job(
                    self._store.list_changes, key, 2
                )
                if len(newest) < 2:
                    # The first state this dashboard ever had. There is
                    # nothing before it, so there is no day to close.
                    return
                current, previous = newest
                zone = dt_util.DEFAULT_TIME_ZONE
                if versioning.same_day(previous.timestamp, current.timestamp, zone):
                    return
                found = await self._hass.async_add_executor_job(
                    self._store.list_versions, key
                )
                # Already marked, by a person or by an earlier run of
                # this. Without the check a dashboard saved twice across
                # one midnight would collect a second tag on the same
                # state, and the numbering would count on regardless.
                if any(v.revision == previous.revision for v in found):
                    return
                # A dashboard created while Home Assistant was running
                # has never had a floor laid - `async_lay_the_floor` ran
                # at setup, and this one did not exist then. Its first
                # automatic version is therefore made at major level, so
                # that it is `v1.0.0` and not `v0.0.1`: `candidates`
                # counts up from the highest version there is, and with
                # none there is the patch candidate is v0.0.1. A later
                # start would then find a version, leave the dashboard
                # alone, and strand it on the v0.0.x track for good.
                # What is being marked is the last state of the day
                # before, which is exactly what a floor is anyway.
                # Measured the same way the floor measures it: what
                # decides the level is whether a readable number exists,
                # not whether some tag does. An unreadable one leaves
                # the counting at (0,0,0), so patch there would be
                # v0.0.1 and the floor would never come.
                level = (
                    "patch"
                    if versioning.latest(key, [v.name for v in found])
                    else "major"
                )
                name = await self._async_make(key, level, previous)
                if name is not None:
                    _LOGGER.info("Marked the end of a day with %s", name)
        except Exception:  # noqa: BLE001 - a missing mark, never a lost save
            _LOGGER.exception("Could not make the daily version of %s", key)
