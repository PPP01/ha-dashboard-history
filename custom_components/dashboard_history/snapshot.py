"""Reading dashboard configurations straight from Home Assistant.

Home Assistant fires `lovelace_updated` *before* it writes the storage
file, so anything that reads the file has to wait and may silently read
the previous state. An integration runs inside Home Assistant and can ask
the Lovelace objects directly, which removes that race entirely.

The lookup is deliberately defensive: `hass.data["lovelace"]` has changed
shape across releases, so we accept both the dataclass and the plain dict
form, and fall back to reading the storage files if neither is present.
"""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lovelace.const import ConfigNotFound
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import DEFAULT_DASHBOARD_KEY

_LOGGER = logging.getLogger(__name__)

LOVELACE_DATA_KEY = "lovelace"

# The value LovelaceConfig.mode returns for a storage dashboard. Compared
# as a literal on purpose: only ConfigNotFound's import path is verified
# against a running installation, and a wrong import would break setup.
MODE_STORAGE = "storage"

# Home Assistant's own storage keys. The default dashboard is stored under
# a bare "lovelace"; every other dashboard under its *id*, which is not the
# same string as its url_path (id "energie_2" vs url_path "energie-2").
_STORAGE_KEY_DEFAULT = "lovelace"
_STORAGE_KEY_TEMPLATE = "lovelace.{}"


def dashboard_key(url_path: str | None) -> str:
    """Map a dashboard url_path to the key we store it under."""
    return url_path or DEFAULT_DASHBOARD_KEY


def _lovelace_dashboards(hass: HomeAssistant) -> dict[str | None, Any] | None:
    """Return Home Assistant's in-memory dashboard objects, or None."""
    data = hass.data.get(LOVELACE_DATA_KEY)
    if data is None:
        return None
    dashboards = getattr(data, "dashboards", None)
    if dashboards is None and isinstance(data, dict):
        dashboards = data.get("dashboards")
    return dashboards if isinstance(dashboards, dict) else None


async def async_get_all_configs(hass: HomeAssistant) -> dict[str, dict]:
    """Return every storage-mode dashboard configuration, keyed by our key."""
    dashboards = _lovelace_dashboards(hass)
    if dashboards is None:
        _LOGGER.warning(
            "Lovelace data not available in the expected shape; "
            "falling back to reading storage files"
        )
        return await _async_get_all_configs_from_storage(hass)

    result: dict[str, dict] = {}
    for url_path, dashboard in dashboards.items():
        if getattr(dashboard, "mode", MODE_STORAGE) != MODE_STORAGE:
            # A YAML dashboard already lives in a file the user versions
            # themselves, and it cannot be written back at all.
            continue
        try:
            config = await dashboard.async_load(False)
        except ConfigNotFound:
            # Entirely normal: a dashboard that has never been saved. The
            # default dashboard is usually in this state.
            _LOGGER.debug("Dashboard %s has no stored configuration", url_path)
            continue
        except Exception:  # noqa: BLE001 - a single bad dashboard must not stop the rest
            _LOGGER.exception("Could not load dashboard %s", url_path)
            continue
        if isinstance(config, dict):
            result[dashboard_key(url_path)] = config
    return result


async def async_get_config(hass: HomeAssistant, key: str) -> dict | None:
    """Return one dashboard configuration, or None if it does not exist."""
    return (await async_get_all_configs(hass)).get(key)


async def _async_get_all_configs_from_storage(hass: HomeAssistant) -> dict[str, dict]:
    """Fallback: read the storage files directly.

    Only used when the in-memory objects are not where we expect them. This
    path can read a state that is a fraction of a second old, which is why it
    is the fallback and not the default.
    """
    result: dict[str, dict] = {}
    store = Store(hass, 1, "lovelace_dashboards")
    registry = await store.async_load() or {}

    # (our key, Home Assistant's storage key) - the two differ, and mixing
    # them up would file the same dashboard under two different names.
    wanted = [(DEFAULT_DASHBOARD_KEY, _STORAGE_KEY_DEFAULT)]
    for item in registry.get("items", []):
        url_path = item.get("url_path")
        if url_path is None or "id" not in item:
            continue
        wanted.append((dashboard_key(url_path), _STORAGE_KEY_TEMPLATE.format(item["id"])))

    for key, storage_key in wanted:
        raw = await Store(hass, 1, storage_key).async_load()
        if isinstance(raw, dict) and isinstance(raw.get("config"), dict):
            result[key] = raw["config"]
    return result
