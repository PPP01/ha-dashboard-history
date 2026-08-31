"""Recording dashboard states as they change.

Home Assistant fires `lovelace_updated` when a dashboard is saved. We do
not read the storage file in response — the event arrives before that
file is written. We ask the in-memory objects instead, which removes the
race completely.

Nothing in here may raise into Home Assistant: a failed recording is an
inconvenience, a failed save is not.
"""

from __future__ import annotations

import logging

from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later

from .analyze import change_message
from .const import EVENT_LOVELACE_UPDATED, RECONCILE_DELAY
from .keys import deletions_to_record

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

    async def async_start(self) -> None:
        """Reconcile once, then listen."""
        await self.async_capture(reason="startup")
        self._unsubscribe = [
            self._hass.bus.async_listen(EVENT_LOVELACE_UPDATED, self._handle_event),
            # Home Assistant announces a *saved* dashboard, but says nothing
            # when one is created, renamed or deleted. All three do move a
            # panel, though, and that is announced - so this is what tells us
            # a dashboard is gone or has a new name.
            self._hass.bus.async_listen(EVENT_PANELS_UPDATED, self._handle_panels),
        ]

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

    async def async_capture(self, key: str | None = None, reason: str = "save") -> list[str]:
        """Record the current state of one or all dashboards.

        Returns the revisions that were created. An unchanged dashboard
        produces none.
        """
        try:
            configs = await async_get_all_configs(self._hass)
        except Exception:  # noqa: BLE001 - never let a recording break a save
            _LOGGER.exception("Could not read dashboard configurations")
            return []

        if key is not None:
            configs = {k: v for k, v in configs.items() if k == key}

        try:
            metas = await async_get_all_meta(self._hass)
        except Exception:  # noqa: BLE001 - metadata is a bonus, not the point
            _LOGGER.exception("Could not read dashboard metadata")
            metas = {}

        revisions: list[str] = []
        if key is None:
            try:
                revisions.extend(await self._async_record_deletions())
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
                revisions.append(revision)
        return revisions

    async def _async_record_deletions(self) -> list[str]:
        """Record dashboards the history knows but Home Assistant does not.

        Losing a whole dashboard is the heaviest loss this integration can
        witness, and Home Assistant announces it with no event at all - so
        it is noticed here, by comparison, rather than not at all. Without
        this it would be the only change that leaves no trace, and an
        invisible gap is worse than no history, because people trust it.

        A missing *configuration* is not enough to conclude a deletion: a
        dashboard that has never been saved has none either. Only one that
        Home Assistant no longer knows at all counts.
        """
        known = await async_known_keys(self._hass)
        tracked = await self._hass.async_add_executor_job(
            self._store.list_dashboards
        )
        revisions: list[str] = []
        for name in deletions_to_record(tracked, known):
            revision = await self._hass.async_add_executor_job(
                self._store.mark_deleted, name, f"{name}: dashboard deleted"
            )
            if revision is not None:
                _LOGGER.info("Dashboard %s is gone; recorded its deletion", name)
                revisions.append(revision)
        return revisions

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

