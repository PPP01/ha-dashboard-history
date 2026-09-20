"""One measurement, shared by the sensors and the report."""

from __future__ import annotations

import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.debounce import Debouncer
from homeassistant.helpers.update_coordinator import (
    REQUEST_REFRESH_DEFAULT_COOLDOWN,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import report
from .const import DATA_REPORT_SECRET, DOMAIN, MEASURE_INTERVAL
from .store import HistoryStore, Measurement

_LOGGER = logging.getLogger(__name__)


class MeasurementCoordinator(DataUpdateCoordinator[Measurement]):
    """Takes the measurement, on a timer and on every recorded change."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, store: HistoryStore
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=MEASURE_INTERVAL,
            # The debouncer this coordinator would build for itself has
            # `immediate=True` and `background=False`, and both are
            # wrong here - checked against Home Assistant 2026.8.3 on
            # 2026-09-20, not assumed.
            #
            # `immediate=True` means the *first* call is not debounced
            # at all: with no timer running, `Debouncer.async_call`
            # executes the job inline and awaits it. Cold, that is a
            # 6.98 s measurement. `background=False` means the job
            # becomes a tracked task, and `async_block_till_done` waits
            # for tracked tasks while Home Assistant comes up. Together
            # they put seven seconds back onto a start that the opening
            # pass was moved off on 2026-09-07 for six.
            #
            # Stated here rather than at the one caller that happened to
            # notice: every later `async_request_refresh` - from a
            # service, from the panel, from initiative C - inherits it
            # instead of having to remember the same wrapper.
            request_refresh_debouncer=Debouncer(
                hass,
                _LOGGER,
                cooldown=REQUEST_REFRESH_DEFAULT_COOLDOWN,
                immediate=False,
                background=True,
            ),
        )

        self._store = store
        # Resolved once, here, and not in the property getter of an
        # entity. `_report_secret` *writes* on first call, and
        # `extra_state_attributes` runs at every state write of every
        # reading - a config entry being written from inside a getter
        # is a side effect nobody reading that property would expect.
        self.secret = _report_secret(hass, entry)
        # When the measurement in `self.data` was taken. Carried here
        # because `DataUpdateCoordinator` has no such field: checked
        # against Home Assistant 2026.8.3 on 2026-09-19, there is no
        # `last_update_time`, and the report has to be able to say how
        # old its numbers are.
        #
        # None until the first success, and deliberately *not* touched
        # when a refresh fails: the timestamp belongs to the numbers in
        # `self.data`, which a failed refresh leaves alone. Moving it
        # would date old numbers to now.
        self.measured_at: float | None = None

    async def _async_update_data(self) -> Measurement:
        """Measure, off the event loop.

        A directory walk over hundreds of loose objects is blocking work
        and belongs in an executor - the hard rule, and this is the only
        place in this initiative that touches the disk at all.

        An unreadable store raises out of `measure` and arrives here as
        `UpdateFailed`, which is what keeps the last good numbers in
        `self.data` and lets the report call itself stale.
        """
        try:
            found = await self.hass.async_add_executor_job(self._store.measure)
        except OSError as error:
            raise UpdateFailed(f"could not measure the history: {error}") from error
        self.measured_at = time.time()
        return found


def _report_secret(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """The installation's own secret, made on first need.

    On first need rather than in the config flow, so that an
    installation set up before this existed needs no migration and
    `VERSION` stays at 1. Writing it fires no reload: no update listener
    is attached to this entry, and `config_flow.py` says why.

    First need is setting the entry up, which is earlier than either
    reader: the id mapping hangs off an entity attribute and is there
    long before anybody downloads a report. Private, because the one
    caller is the coordinator above - it holds the answer as
    `self.secret`, and both readers take it from there.
    """
    existing = entry.data.get(DATA_REPORT_SECRET)
    if existing:
        return existing
    made = report.new_secret()
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, DATA_REPORT_SECRET: made}
    )
    return made
