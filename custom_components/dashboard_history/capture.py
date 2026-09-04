"""Recording dashboard states as they change.

Home Assistant fires `lovelace_updated` when a dashboard is saved. We do
not read the storage file in response — the event arrives before that
file is written. We ask the in-memory objects instead, which removes the
race completely.

Nothing in here may raise into Home Assistant: a failed recording is an
inconvenience, a failed save is not.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .analyze import change_message
from .const import EVENT_HISTORY_UPDATED, EVENT_LOVELACE_UPDATED, RECONCILE_DELAY
from .keys import deletions_to_record, is_safe_key

try:  # The authoritative source; the literal below is only a fallback.
    from homeassistant.components.frontend import EVENT_PANELS_UPDATED
except ImportError:  # pragma: no cover - layout differs across releases
    EVENT_PANELS_UPDATED = "panels_updated"
from .snapshot import (
    async_get_all_configs,
    async_get_all_meta,
    async_known_keys,
    dashboard_key,
)
from .store import HistoryStore
from .yaml_io import dump, load

_LOGGER = logging.getLogger(__name__)


class HistoryCapture:
    """Listens for dashboard saves and records them."""

    def __init__(self, hass: HomeAssistant, store: HistoryStore) -> None:
        self._hass = hass
        self._store = store
        self._unsubscribe: list = []
        self._pending = None
        # Two locks, one job each, and the split is not a refinement -
        # a single lock over both halves loses states.
        #
        # `_writing` fixes the ordering. Two saves in quick succession
        # both read, then both write, and whoever writes second builds
        # its message against a HEAD that is already the newer state: the
        # older state arrives last and is described by comparison with
        # its own successor. Measured: seven saves came out as the chain
        # 1,2,3,4,6,5,7, one of them claiming "changed outside Home
        # Assistant" about a save Home Assistant had just made itself. So
        # the HEAD lookup, the message and the commit are one section.
        #
        # `_reading` keeps that section from swallowing what it is meant
        # to protect. Measured with both halves under one lock: a
        # reconciliation over a grown repository held it for 16.6 s, a
        # save waited 7.2 s for it, and by the time it could look, the
        # dashboard had been deleted - so it wrote nothing and that state
        # is gone for good. Reading is therefore locked on its own,
        # touches no git, and finishes in milliseconds; a caller that
        # waits for `_writing` waits with the state already in its hands.
        # A slow write delays the history. A slow read destroys it.
        self._reading = asyncio.Lock()
        self._writing = asyncio.Lock()

    async def async_start(self) -> None:
        """Listen for saves, reconcile once, then listen for panels too.

        The save listener comes first, and that order is the point. It
        came after the pass for a long time, and the startup pass over
        every dashboard takes about twenty seconds on the test bench - a
        save made in that window was neither in the pass, which had
        already read the configurations, nor heard by a listener that did
        not exist yet. Measured on 2026-09-04: the check that drops a card
        ran while the pass was still writing, and the history never saw
        the drop. A save heard now waits for the write lock behind the
        pass and is recorded right after it.

        The panel listener comes after, deliberately: Home Assistant
        fires `panels_updated` in a burst while it starts, and heard
        before the pass that burst would queue a second full pass behind
        the first, for nothing.
        """
        self._unsubscribe = [
            self._hass.bus.async_listen(EVENT_LOVELACE_UPDATED, self._handle_event),
        ]
        await self.async_capture(reason="startup")
        # Home Assistant announces a *saved* dashboard, but says nothing
        # when one is created, renamed or deleted. All three do move a
        # panel, though, and that is announced - so this is what tells us
        # a dashboard is gone or has a new name.
        self._unsubscribe.append(
            self._hass.bus.async_listen(EVENT_PANELS_UPDATED, self._handle_panels)
        )

    async def async_stop(self) -> None:
        """Stop listening."""
        for unsubscribe in self._unsubscribe:
            unsubscribe()
        self._unsubscribe = []
        if self._pending is not None:
            self._pending()
            self._pending = None

    @callback
    def _handle_event(self, event: Event) -> None:
        """React to a save without blocking the event bus."""
        key = dashboard_key(event.data.get("url_path"))
        self._hass.async_create_task(self.async_capture(key=key, reason="save"))

    @callback
    def _handle_panels(self, event: Event) -> None:
        """A panel moved. Look at everything, shortly, and only once.

        This fires several times in a row while Home Assistant starts and
        whenever anything touches a panel, so the work is deferred and
        collapsed: a burst of events costs one reconciliation.
        """
        if self._pending is not None:
            self._pending()
        self._pending = async_call_later(
            self._hass, RECONCILE_DELAY, self._async_reconcile
        )

    async def _async_reconcile(self, _now) -> None:
        """Compare everything against the history."""
        self._pending = None
        await self.async_capture(reason="reconcile")

    async def async_capture(
        self, key: str | None = None, reason: str = "save", announce: bool = True
    ) -> list[str]:
        """Record the current state of one or all dashboards.

        Returns the revisions that were created. An unchanged dashboard
        produces none.

        `announce=False` records without telling anybody. It exists for
        the snapshot taken immediately *before* a restore: the panel
        waits for `EVENT_HISTORY_UPDATED` to know its page is stale, and
        firing it there would send it to reload a history whose newest
        entry is the state about to be overwritten - a page half a
        restore old, which then looks correct and is not.

        Reading and writing are locked *separately*, and that split is
        the whole design. See `_reading` and `_writing`.
        """
        async with self._reading:
            read = await self._async_read(key)
        if read is None:
            return []
        async with self._writing:
            return await self._async_write(*read, key, reason, announce)

    async def _async_read(self, key: str | None):
        """Ask Home Assistant what is there. Fast, and never touches git.

        Answers None when the configurations could not be read at all -
        which is different from reading them and finding nothing, and
        must not be turned into "every dashboard was deleted".
        """
        try:
            configs = await async_get_all_configs(self._hass)
        except Exception:  # noqa: BLE001 - never let a recording break a save
            _LOGGER.exception("Could not read dashboard configurations")
            return None

        if key is not None:
            configs = {k: v for k, v in configs.items() if k == key}

        # A key decides a file name and a tag namespace, so one that is
        # not a single path segment is turned away rather than written
        # somewhere else. Logged by name at warning level: this is a
        # dashboard whose history simply will not exist, and silence
        # there would be the worst of the three possible answers.
        for name in sorted(k for k in configs if not is_safe_key(k)):
            _LOGGER.warning(
                "Not recording dashboard %r: its url_path is not a single "
                "path segment, so it has no place in the history",
                name,
            )
        configs = {k: v for k, v in configs.items() if is_safe_key(k)}

        try:
            metas = await async_get_all_meta(self._hass)
        except Exception:  # noqa: BLE001 - metadata is a bonus, not the point
            _LOGGER.exception("Could not read dashboard metadata")
            metas = {}

        known = await async_known_keys(self._hass) if key is None else None
        return configs, metas, known

    async def _async_write(
        self,
        configs: dict[str, dict],
        metas: dict[str, dict],
        known: set[str] | None,
        key: str | None,
        reason: str,
        announce: bool,
    ) -> list[str]:
        """Write what was read. All the git work, one caller at a time."""
        revisions: list[str] = []
        touched: list[str] = []
        if key is None:
            try:
                for name, revision in await self._async_record_deletions(known):
                    touched.append(name)
                    revisions.append(revision)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not record deleted dashboards")
        for name, config in sorted(configs.items()):
            try:
                revision = await self._hass.async_add_executor_job(
                    self._write_one, name, config, reason, metas.get(name)
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not record dashboard %s", name)
                continue
            if revision is not None:
                touched.append(name)
                revisions.append(revision)
        # One line per pass, at debug: which dashboards were looked at and
        # which were written. When a change does not show up in the
        # history, this is the line that says whether the recorder saw
        # the state at all - nothing else in the log does.
        _LOGGER.debug(
            "Recording (%s): looked at %s, wrote %s",
            reason,
            sorted(configs) if key is None else key,
            [f"{name}@{revision[:8]}" for name, revision in zip(touched, revisions)],
        )
        if revisions and announce:
            self._announce(touched, reason)
        return revisions

    def _announce(self, touched: list[str], reason: str) -> None:
        """Say that the history has grown, and which dashboards grew.

        Only when something was written. An unchanged dashboard produces
        no revision, and a page that refreshes for nothing teaches people
        to stop trusting that a refresh means anything.

        Swallowed like every other failure in here: a listener that is
        not there, or a bus that refuses, must not turn a recorded change
        into a lost one. The worst this costs is a panel that shows its
        age until somebody presses reload.
        """
        try:
            self._hass.bus.async_fire(
                EVENT_HISTORY_UPDATED,
                {"dashboards": sorted(set(touched)), "reason": reason},
            )
        except Exception:  # noqa: BLE001 - announcing is a courtesy, not the point
            _LOGGER.exception("Could not announce the recorded change")

    async def _async_record_deletions(
        self, known: set[str] | None
    ) -> list[tuple[str, str]]:
        """Record dashboards the history knows but Home Assistant does not.

        Answers with (dashboard, revision) pairs rather than bare
        revisions: the caller announces which dashboards changed, and a
        deleted one is exactly the case a panel most needs to hear about.

        Losing a whole dashboard is the heaviest loss this integration can
        witness, and Home Assistant announces it with no event at all - so
        it is noticed here, by comparison, rather than not at all. Without
        this it would be the only change that leaves no trace, and an
        invisible gap is worse than no history, because people trust it.

        A missing *configuration* is not enough to conclude a deletion: a
        dashboard that has never been saved has none either. Only one that
        Home Assistant no longer knows at all counts.

        `known` is read in the read phase, with the configurations, and
        handed in here: it is a question for Home Assistant, and every
        question for Home Assistant is asked while the answer is still
        current rather than after a wait for the write lock.
        """
        tracked = await self._hass.async_add_executor_job(
            self._store.list_dashboards
        )
        gone: list[tuple[str, str]] = []
        for name in deletions_to_record(tracked, known):
            # One dashboard at a time, like `_async_write` does for the
            # saves: a failure on the first must not leave the others
            # unrecorded, and the deletions are the one change this
            # integration exists to notice.
            try:
                revision = await self._hass.async_add_executor_job(
                    self._store.mark_deleted, name, f"{name}: dashboard deleted"
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Could not record the deletion of %s", name)
                continue
            if revision is not None:
                _LOGGER.info("Dashboard %s is gone; recorded its deletion", name)
                gone.append((name, revision))
        return gone

    def _write_one(
        self, name: str, config: dict, reason: str, meta: dict | None = None
    ) -> str | None:
        """Blocking part: build the message and write. Runs in an executor."""
        text = dump(config)
        known = self._has_history(name)
        previous = self._store.read_at(name, "HEAD") if known else None
        previous_meta = self._store.read_meta_at(name, "HEAD") if known else None
        message = change_message(
            name,
            load(previous) if previous is not None else None,
            config,
            reason,
            load(previous_meta) if previous_meta is not None else None,
            meta,
        )
        return self._store.write_snapshot(
            name, text, message, dump(meta) if meta else None
        )

    def _has_history(self, name: str) -> bool:
        return bool(self._store.list_changes(name, limit=1))

