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

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.util import dt as dt_util

from . import operations
from . import versions as versioning
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
            if await self._hass.async_add_executor_job(
                self._store.list_versions, key
            ):
                return None
            newest = await self._hass.async_add_executor_job(
                self._store.list_changes, key, 1
            )
            if not newest:
                # Nothing recorded yet. Nothing to mark, and nothing wrong:
                # a dashboard that has never been saved has no state.
                return None
            return await self._async_make(key, "major", newest[0])
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
