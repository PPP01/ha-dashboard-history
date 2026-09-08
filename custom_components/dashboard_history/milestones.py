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
from .store import Change, HistoryStore, Version

_LOGGER = logging.getLogger(__name__)

# How far back a day mark looks for the end of the previous day. Two
# would be enough for one save at a time; a burst of saves needs room,
# because every one of them is announced and each announcement looks at
# the newest entries as they are *now*, not as they were when it fired.
#
# Measured on 2026-09-05, since it is not free: dulwich counts
# `max_entries` in matching commits, so a wider window walks further
# past other dashboards' commits. On a repository of 965 commits over
# eight dashboards, one read of a regularly saved dashboard cost 15 ms
# at two entries and 101 ms at twenty - flat in the size of the history,
# because the walk stops as soon as it has its matches. A rarely saved
# dashboard cost 490 ms either way; there the walk runs to the end of
# the history whatever the window is. It is paid in an executor after
# the save has been announced, so it delays no save - it holds a thread
# and the lock below for about a tenth of a second.
_RECENT = 20


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

        One tag scan per dashboard, deliberately, and not one grouped
        scan for the whole pass. The grouped form is cheaper and was
        considered: measured on 2026-09-05 over twelve dashboards
        carrying 3600 tags between them - a year of daily versions - the
        twelve narrowed scans this pass makes cost 1530 ms against
        545 ms for a single `list_versions(None)` sorted by key. It is
        still the wrong shape. Since the marker is armed before the
        recorder (`async_arm`), day marks are being made while this pass
        walks, so a tag list read once at the top is stale by the time
        the later dashboards are reached - and a stale list says "no
        version yet" about a dashboard that has just been given one,
        which is exactly the collision `_async_floor_for` takes the
        marking lock to avoid. Reading each dashboard's tags freshly,
        under that lock, is what makes the check mean anything.

        The second-per-start this costs is paid in an executor, beside
        an opening pass of about twenty seconds, and it grows with the
        number of dashboards rather than with the history. The scan
        itself no longer grows with the tags of *other* dashboards -
        `store._each_tag` narrows before it loads an object, which is
        where the real cost used to be.
        """
        try:
            live = await self._hass.async_add_executor_job(
                self._store.list_dashboards
            )
        except Exception:  # noqa: BLE001 - a missing mark, never a broken start
            _LOGGER.exception("Could not list the dashboards to give a version to")
            return []
        made: list[str] = []
        for key in live:
            name = await self._async_floor_for(key)
            if name is not None:
                made.append(name)
        if made:
            _LOGGER.info("Made a first version: %s", ", ".join(made))
        return made

    async def _async_floor_for(self, key: str) -> str | None:
        """One dashboard's floor, or None if it needs none or cannot get one.

        One dashboard at a time, each in its own guard: the same shape
        `capture._async_write` uses, and for the same reason - a failure
        on the first must not cost the rest.

        Under the same lock a day mark takes, and for the same reason it
        takes it. Since the marker is armed before the recorder starts
        (`async_arm`), the opening pass's announcements raise day marks
        while this pass is still walking, and on a dashboard with no
        version yet both of them compute `v1.0.0`. The store refuses the
        second with a `ValueError`, which arrives here as a refusal and
        would log a warning about a dashboard that is in perfect order.
        Serialised, the loser instead sees the version the winner made
        and returns None, which is the truth: it needs no floor any more.
        """
        try:
            async with self._marking:
                found = await self._async_versions(key)
                if versioning.latest(key, [v.name for v in found]) is not None:
                    return None
                # The whole history of this one dashboard, to reach its
                # oldest entry - the design record calls the floor "the
                # state to come back to before anything happened", and on a
                # dashboard that was created while Home Assistant was
                # running, its newest state is not that. It is what is on
                # the screen right now, and a floor you can "go back to"
                # without anything changing is not an offer.
                #
                # The full walk is affordable precisely because it happens
                # once: the check above returns before it on every later
                # start, so no dashboard pays for this twice.
                recorded = await self._hass.async_add_executor_job(
                    self._store.list_changes, key, None
                )
                if not recorded:
                    # Nothing recorded yet. Nothing to mark, and nothing wrong:
                    # a dashboard that has never been saved has no state.
                    return None
                made = await self._async_make(key, "major", recorded[-1])
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

    async def _async_versions(self, key: str) -> list[Version]:
        """Every tag a dashboard carries, read in an executor.

        Handed over whole rather than answered here. Both callers ask a
        question of it that `versions.py` settles - "is there a number
        yet" for the floor, "at what level, and is this day already
        marked" for the day mark - and those are the questions that go
        quietly wrong, so they live where plain pytest reaches them.
        """
        return await self._hass.async_add_executor_job(
            self._store.list_versions, key
        )

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

        That operation reads the dashboard's tags again to work the
        number out, so a version costs one scan more than the caller has
        already paid for. Left alone on purpose. It is the fence's own
        reading, and letting a caller hand its list down would let a
        caller hand down a stale one and get a name that already exists
        - the numbering is the one calculation here that goes quietly
        wrong. It is also only paid when a version is actually made:
        never on the floor pass of a dashboard that already has one,
        and on the pass that does make one it sits beside a full walk of
        that dashboard's history, which measured three times as long.
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

        Armed *before* the recorder starts, and that order is the whole
        reason this is a call of its own. `capture.async_opening_pass()`
        announces what it records, so a marker armed after it never
        hears a word of that - and what it records is precisely the
        changes made while nobody was watching. Home Assistant is down
        overnight, a storage file is edited by hand or comes back from a
        backup, Home Assistant starts on Tuesday: the pass commits
        Monday's change and announces it to
        an empty room. Monday is then never marked and never can be -
        Tuesday's later saves look back over a window holding nothing but
        Tuesday. The same goes for a save made *during* the pass, a
        window the recorder deliberately opens its save listener before
        (`capture.async_start`, which now does nothing else).

        The order used to be the other way round, and the reason it gave
        has since been doubled elsewhere: `candidates` counts up from the
        highest version there is, so a day mark on a dashboard with no
        version at all would once have been numbered `v0.0.1`. It is not
        any more. `_async_mark_day` asks `versions.automatic_level`,
        which answers `major` exactly when there is no number yet, so
        such a dashboard gets `v1.0.0` whether a floor was laid first or
        not.

        What the new order does bring is a floor pass and a day mark in
        flight at the same time - the first time those two can overlap -
        both able to work out the same name for the same dashboard, with
        the loser refused by `store.create_version`. `_async_floor_for`
        takes `self._marking` for that reason. Whichever gets there first
        makes the version and the other reads it and stands down, and
        either outcome is right: what a day mark puts on the last state
        of the previous day is what a floor is anyway.

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
            # mark in flight does not outlive the instance whose lock it
            # holds. Without that, a reload leaves the old task running
            # against the old lock while the new instance holds a new
            # one - and two versions land on one state, which is the
            # very thing the lock is here to prevent.
            #
            # It holds for the coroutine, not for the thread underneath
            # it: cancelled while the tag is being written in an
            # executor, the future is dropped and the thread finishes
            # the write regardless. What is left is a much narrower
            # window than the one this closes, and only on a reload
            # during a mark.
            self._entry.async_create_background_task(
                self._hass,
                self._async_mark_day(key),
                name=f"dashboard_history mark day {key}",
            )

    async def _async_mark_day(self, key: str) -> None:
        """Mark the state that was there before this new day started."""
        try:
            # Asked before the lock, not behind it: with the switch off
            # there is nothing to serialise, and every save would
            # otherwise queue one task behind another to learn that.
            # Read off the entry each time, so a change takes effect at
            # the next save rather than at the next restart.
            if not self._entry.options.get(OPTION_DAILY_VERSIONS, True):
                return
            async with self._marking:
                newest = await self._hass.async_add_executor_job(
                    self._store.list_changes, key, _RECENT
                )
                if len(newest) < 2:
                    # The first state this dashboard ever had. There is
                    # nothing before it, so there is no day to close.
                    return
                # The last state of the day before, found by walking
                # back over the window rather than by taking the second
                # entry. The reason it has to be a walk lives with the
                # calculation, in `versions.end_of_previous_day`.
                zone = dt_util.DEFAULT_TIME_ZONE
                at = versioning.end_of_previous_day(
                    [c.timestamp for c in newest], zone
                )
                if at is None:
                    # Either no day ended here - the ordinary case, and
                    # by far the most common - or more than `_RECENT`
                    # saves landed since one did, and that state is out
                    # of reach for good. The second is worth a line:
                    # without one, the only way anybody would ever
                    # notice is a missing mark found weeks later.
                    if len(newest) >= _RECENT:
                        _LOGGER.debug(
                            "No day ended within the last %s states of %s; "
                            "if one did, it is out of this window",
                            _RECENT,
                            key,
                        )
                    return
                previous = newest[at]
                found = await self._async_versions(key)
                # Already marked, by a person or by an earlier run of
                # this. Without the check a dashboard saved twice across
                # one midnight would collect a second tag on the same
                # state, and the numbering would count on regardless.
                if any(v.revision == previous.revision for v in found):
                    return
                title = versioning.day_title(previous.timestamp, zone)
                # And at most one automatic version per day, which is a
                # wider rule than the one above and catches what it
                # cannot see. The floor sits on a dashboard's oldest
                # state; on an installation set up today that state is
                # also today's, so the first day mark would land on a
                # *different* revision of the same day and the simple
                # mode - which shows nothing but titles - would offer
                # two rows both reading `5 September 2026`, each with
                # its own button. Indistinguishable for exactly the
                # person that mode exists for.
                if title in versioning.automatic_days(
                    (v.title, v.description) for v in found
                ):
                    return
                # And not where the state being marked is the one the
                # highest numbered version already holds. The two above look
                # at revisions and at days; this one looks at what is
                # actually on the dashboard, which is what a version is
                # for. A day mark is worked out from the calendar, so a
                # dashboard that is changed and changed back - a card
                # moved out and moved home again, a routine that rewrites
                # the same file every night - ends every day on the state
                # it started from, and collects one version per day all
                # holding the same thing. The panel cannot even offer a
                # button on those rows: going back to them would change
                # nothing, so it says "same state as now" instead
                # (`simple.js`). A list of dated rows that do nothing is
                # exactly the wall the simple mode exists to avoid.
                #
                # Compared against the *highest numbered* version, not
                # against every version there is. That is the one the rest
                # of this reckons from - `candidates` counts up from it,
                # and the simple mode's sentence names it - so it is the
                # one a new mark would be redundant beside. It also keeps
                # a rollback honest: after going back to an old state the
                # newest version holds something else, so the day that
                # move belongs to still gets its mark, even though an
                # older version holds that content too. Against all of
                # them, that mark would be dropped and the day it
                # happened would show nothing.
                top = versioning.highest(key, found)
                if top is not None and await self._hass.async_add_executor_job(
                    self._store.same_state, key, previous.revision, top.revision
                ):
                    # Worth a line, at debug. This is the one reason a day
                    # can go unmarked that is invisible from the outside:
                    # the change is in the history, the day ended, and
                    # there is still no new version. Without it the only
                    # way to tell this rule from a fault is to read it.
                    _LOGGER.debug(
                        "No day mark for %s: %s already holds that state",
                        key,
                        top.name,
                    )
                    return
                # Major when there is no number yet: a dashboard created
                # while Home Assistant was running never had a floor
                # laid, and `candidates` would otherwise start it at
                # v0.0.1 and strand it on that track for good. What is
                # being marked - the last state of the day before - is
                # exactly what a floor is anyway.
                level = versioning.automatic_level(key, [v.name for v in found])
                name = await self._async_make(key, level, previous)
                if name is not None:
                    _LOGGER.info("Marked the end of a day with %s", name)
        except Exception:  # noqa: BLE001 - a missing mark, never a lost save
            _LOGGER.exception("Could not make the daily version of %s", key)
