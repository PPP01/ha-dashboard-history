"""One measurement, shared by the sensors and the report."""

from __future__ import annotations

import logging
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MEASURE_INTERVAL
from .store import HistoryStore, Measurement

_LOGGER = logging.getLogger(__name__)


class MeasurementCoordinator(DataUpdateCoordinator[Measurement]):
    """Takes the measurement, on a timer and on every recorded change."""

    def __init__(self, hass: HomeAssistant, store: HistoryStore) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=MEASURE_INTERVAL,
        )

        self._store = store
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
