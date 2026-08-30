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

from .analyze import summarize
from .const import EVENT_LOVELACE_UPDATED
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
        self._unsubscribe = None

    async def async_start(self) -> None:
        """Reconcile once, then listen."""
        await self.async_capture(reason="startup")
        self._unsubscribe = self._hass.bus.async_listen(
            EVENT_LOVELACE_UPDATED, self._handle_event
        )

    async def async_stop(self) -> None:
        """Stop listening."""
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _handle_event(self, event: Event) -> None:
        """React to a save without blocking the event bus."""
        key = dashboard_key(event.data.get("url_path"))
        self._hass.async_create_task(self.async_capture(key=key, reason="save"))

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
        if known is None:
            # The question could not be answered. Saying nothing is right;
            # marking everything deleted would be catastrophic.
            return []
        tracked = await self._hass.async_add_executor_job(
            self._store.list_dashboards
        )
        revisions: list[str] = []
        for name in sorted(set(tracked) - known):
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
        previous = self._store.read_at(name, "HEAD") if self._has_history(name) else None
        message = self._build_message(name, config, previous, reason)
        return self._store.write_snapshot(
            name, text, message, dump(meta) if meta else None
        )

    def _has_history(self, name: str) -> bool:
        return bool(self._store.list_changes(name, limit=1))

    def _build_message(self, name: str, config: dict, previous: str | None, reason: str) -> str:
        """A readable one-line summary of what happened."""
        if previous is None:
            return f"{name}: first recorded state"
        if reason == "startup":
            # Something changed while we were not listening: a restored
            # backup, a hand-edited storage file, another tool. Recording it
            # as a normal save would hide that.
            return f"{name}: changed outside Home Assistant"
        old = load(previous) or {}
        s = summarize(old, config)
        parts = [
            f"{s.removed} removed" if s.removed else "",
            f"{s.added} added" if s.added else "",
            f"{s.edited} edited" if s.edited else "",
            f"{s.moved} moved" if s.moved else "",
        ]
        detail = ", ".join(p for p in parts if p) or "no card changes"
        return f"{name}: {detail}"
