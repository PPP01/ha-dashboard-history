"""What the history costs and holds, as five diagnostic entities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import report
from .const import DOMAIN, OPTION_DAILY_VERSIONS
from .coordinator import MeasurementCoordinator
from .store import Measurement


@dataclass(frozen=True, kw_only=True)
class Reading(SensorEntityDescription):
    """One number and the detail that belongs beside it.

    The detail travels as attributes rather than as more entities: five
    entities are a device page somebody reads, fifteen are one they skim
    past, and a median belongs to its count rather than beside it.
    """

    value: Callable[[Measurement], object]
    extra: Callable[[Measurement, str, bool], dict] = lambda m, s, d: {}


def _median(numbers: list[int]) -> int:
    if not numbers:
        return 0
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


READINGS: tuple[Reading, ...] = (
    Reading(
        key="last_capture",
        translation_key="last_capture",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda m: (
            datetime.fromtimestamp(m.newest, UTC) if m.newest else None
        ),
        extra=lambda m, secret, daily: {
            "dashboard": (
                report.dashboard_id(m.newest_key, secret) if m.newest_key else None
            )
        },
    ),
    Reading(
        key="size",
        translation_key="size",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        # What it costs, not what it contains - and `bytes_on_disk`
        # carries the platform fallback so that a second reader cannot
        # decide it differently.
        value=lambda m: m.bytes_on_disk,
        extra=lambda m, secret, daily: {
            "bytes_logical": m.bytes_logical,
            "bytes_allocated": m.bytes_allocated,
            "bytes_git": m.bytes_git_logical,
            "bytes_worktree": m.bytes_worktree_logical,
            "loose_objects": m.loose_objects,
            "packs": m.packs,
        },
    ),
    Reading(
        key="revisions",
        translation_key="revisions",
        # `measurement`, not `total_increasing`: `forget` takes states
        # away, and a counter declared to only ever rise would look to
        # Home Assistant like an overflow every time one runs.
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda m: m.revisions,
        extra=lambda m, secret, daily: {
            "busiest": max((d.revisions for d in m.dashboards), default=0),
            "median": _median([d.revisions for d in m.dashboards]),
            "oldest": (
                datetime.fromtimestamp(m.oldest, UTC).isoformat() if m.oldest else None
            ),
        },
    ),
    Reading(
        key="dashboards",
        translation_key="dashboards",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda m: m.live,
        extra=lambda m, secret, daily: {
            "gone": m.gone,
            "ever": len(m.dashboards),
            # The lookup table, and the reason it lives on an entity
            # rather than in the report: attributes stay on this
            # installation. Somebody asked about `a3f81c92` looks here
            # and knows which dashboard is meant. Every dashboard ever,
            # the deleted ones included - they have a row in the report
            # too, and those are the ones worth asking about.
            "ids": {report.dashboard_id(d.key, secret): d.key for d in m.dashboards},
        },
    ),
    Reading(
        key="versions",
        translation_key="versions",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda m: m.versions,
        extra=lambda m, secret, daily: {
            "daily_versions": daily,
            "most": max((d.versions for d in m.dashboards), default=0),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Put the five readings up."""
    coordinator: MeasurementCoordinator = hass.data[DOMAIN]["coordinator"]
    add(HistoryReading(coordinator, entry, reading) for reading in READINGS)


class HistoryReading(CoordinatorEntity[MeasurementCoordinator], SensorEntity):
    """One measured number, with its detail beside it."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: Reading

    def __init__(
        self,
        coordinator: MeasurementCoordinator,
        entry: ConfigEntry,
        reading: Reading,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = reading
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{reading.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Dashboard History",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        """The number, or None until the first measurement is in.

        None rather than "unavailable" on an empty history: zero states
        recorded is an answer, not a failure. Only a measurement that
        has not happened yet shows nothing.
        """
        if self.coordinator.data is None:
            return None
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return self.entity_description.extra(
            self.coordinator.data,
            self.coordinator.secret,
            self._entry.options.get(OPTION_DAILY_VERSIONS, True),
        )
