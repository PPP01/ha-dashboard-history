"""The `data` block of a diagnostics download.

Fifteen lines, and that is the design: everything worth testing lives in
`report.py`, which imports no Home Assistant and is therefore reachable
from plain `pytest`.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import report
from .const import DOMAIN, OPTION_DAILY_VERSIONS
from .coordinator import MeasurementCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Measure again, then report what the sensors now show.

    `async_refresh` and not `async_request_refresh`: the debounced form
    would only add delay here. A diagnostics download is a rare,
    deliberate act, and a directory walk for it is affordable.

    Reading `coordinator.data` afterwards is what makes the promise true
    that the sensors show what the file says - the entities are written
    from this same refresh. Measuring separately would leave the two
    disagreeing by one interval.
    """
    coordinator: MeasurementCoordinator = hass.data[DOMAIN]["coordinator"]
    await coordinator.async_refresh()

    # None where no measurement has ever succeeded - a download in the
    # first seconds after a start, or a store that cannot be read at
    # all. `report.build` turns that into empty totals rather than into
    # zeros, because zeros are what a real but empty history looks like.
    return report.build(
        coordinator.data,
        coordinator.secret,
        daily_versions=entry.options.get(OPTION_DAILY_VERSIONS, True),
        # The coordinator's own timestamp. `DataUpdateCoordinator` has
        # no `last_update_time` - checked against 2026.8.3 - and it
        # belongs to the numbers in `coordinator.data`, which a failed
        # refresh leaves untouched. So a stale report is dated to when
        # its numbers were taken, not to when somebody asked for them.
        measured_at=coordinator.measured_at,
        # Stale when this refresh did not succeed, however good the
        # numbers underneath still are. A file that carries an obviously
        # old measuring time is usable; one that hides its age is worse
        # than none.
        stale=not coordinator.last_update_success,
    )
