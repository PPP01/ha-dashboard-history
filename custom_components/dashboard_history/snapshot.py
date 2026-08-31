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
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store

from .const import DEFAULT_DASHBOARD_KEY
from .keys import storage_keys

_LOGGER = logging.getLogger(__name__)

LOVELACE_DATA_KEY = "lovelace"

# Where Home Assistant keeps its registered WebSocket commands, and the one
# whose handler holds the dashboard collection. Both as literals: importing
# websocket_api here to read one constant would add a dependency for a
# string, and a wrong import breaks setup while a wrong string only makes
# the lookup come up empty.
WEBSOCKET_DOMAIN = "websocket_api"
_DASHBOARD_LIST_COMMAND = "lovelace/dashboards/list"

# The value LovelaceConfig.mode returns for a storage dashboard. Compared
# as a literal on purpose: only ConfigNotFound's import path is verified
# against a running installation, and a wrong import would break setup.
MODE_STORAGE = "storage"



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


async def async_known_keys(hass: HomeAssistant) -> set[str] | None:
    """The keys of every dashboard Home Assistant currently knows of.

    Deliberately separate from async_get_all_configs. A dashboard that
    has never been saved has no configuration but exists perfectly well,
    and so does one whose configuration failed to load. Concluding
    "deleted" from a missing configuration would invent an event that
    never happened - the kind of false alarm this integration exists to
    avoid.

    Returns None when the question cannot be answered at all. That is not
    the same as "none of them", and callers must not read it that way.
    """
    dashboards = _lovelace_dashboards(hass)
    if dashboards is None:
        return None
    return {dashboard_key(url_path) for url_path in dashboards}


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

    for key, storage_key in storage_keys(
        registry.get("items"), DEFAULT_DASHBOARD_KEY
    ):
        raw = await Store(hass, 1, storage_key).async_load()
        if isinstance(raw, dict) and isinstance(raw.get("config"), dict):
            result[key] = raw["config"]
    return result


_META_FIELDS = ("title", "icon", "show_in_sidebar", "require_admin")


async def async_get_all_meta(hass: HomeAssistant) -> dict[str, dict]:
    """What each dashboard *is*, as opposed to what is on it.

    Title, icon and visibility live in Home Assistant's dashboard
    registry, not in the configuration. Bringing a deleted dashboard back
    without them would return the cards under a wrong name.
    """
    dashboards = _lovelace_dashboards(hass)
    if dashboards is None:
        return {}
    result: dict[str, dict] = {}
    for url_path, dashboard in dashboards.items():
        item = getattr(dashboard, "config", None)
        if not isinstance(item, dict):
            # The default dashboard has no registry entry of its own.
            continue
        result[dashboard_key(url_path)] = {
            field: item[field] for field in _META_FIELDS if field in item
        }
    return result


def _usable_collection(candidate):
    """A dashboard collection only counts if it can create an item."""
    return candidate if hasattr(candidate, "async_create_item") else None


def _dashboards_collection(hass: HomeAssistant):
    """Home Assistant's *own* dashboard collection, or None.

    Its own, emphatically. A second `DashboardsCollection` over the same
    store is easy to build and looks like it works, and that was the shape
    of the worst defect this project has had: Home Assistant reads a
    dashboard list from one place and applies changes to another.
    `lovelace/dashboards/list` is overridden to answer from
    `LovelaceData.dashboards`, while update and delete go to the
    collection. An entry that reached only the first looks perfectly
    healthy and cannot be renamed - and worse, Home Assistant's collection
    writes its whole in-memory state back to the store on the next create
    or delete, dropping the entry from disk without a word.

    So there is one acceptable object: the instance Home Assistant itself
    holds. On 2026.8.3 it is not on `LovelaceData` - it is a local
    variable in `lovelace.async_setup`. But the object that registers the
    dashboard WebSocket commands keeps it, and the list handler is
    registered as a plain bound method, because only an `admin_only`
    collection wraps that one in a decorator. That makes it reachable
    through the command registry.

    Private, and therefore checked rather than assumed at every step:
    every lookup below tolerates a shape that is no longer there.
    """
    data = hass.data.get(LOVELACE_DATA_KEY)
    for name in ("dashboards_collection", "dashboard_collection", "collection"):
        found = _usable_collection(getattr(data, name, None))
        if found is not None:
            return found

    entry = (hass.data.get(WEBSOCKET_DOMAIN) or {}).get(_DASHBOARD_LIST_COMMAND)
    handler = entry[0] if isinstance(entry, tuple) and entry else entry
    return _usable_collection(getattr(getattr(handler, "__self__", None),
                                      "storage_collection", None))


async def async_create_dashboard(
    hass: HomeAssistant, key: str, meta: dict
) -> str | None:
    """Recreate a deleted dashboard. Returns a caveat, or None if there is none.

    Through Home Assistant's own collection, and through nothing else.
    Its listener then registers the panel, builds the dashboard object and
    saves the store, so the entry is in step everywhere at once - the
    sidebar, the settings dialog, and the file on disk.

    There used to be a fallback here that wrote the entry through a
    collection of its own and imitated the listener. It was reported as a
    partial success with a note about restarting. That was wrong twice
    over: renaming or deleting the dashboard failed with "Unable to find
    dashboard_id", and Home Assistant's collection later dropped the entry
    from disk on its next save, so the dashboard was gone at the following
    restart. A half-restored dashboard that looks healthy is worse than an
    honest refusal, so the refusal is what happens now.

    Returns None - there is nothing left to say when this succeeds. The
    return type is kept so callers need no change if a future version has
    something to report again.
    """
    item = {
        "url_path": key,
        "title": meta.get("title") or key,
        "show_in_sidebar": meta.get("show_in_sidebar", True),
        "require_admin": meta.get("require_admin", False),
    }
    if meta.get("icon"):
        item["icon"] = meta["icon"]

    live = _dashboards_collection(hass)
    if live is None:
        # Not reachable means this Home Assistant has moved. Refusing is
        # the right answer: the alternative writes something that looks
        # like a dashboard and is not one. The message says what a person
        # can do instead, because they can - creating the dashboard by hand
        # and restoring again writes the configuration into it.
        raise HomeAssistantError(
            f"Cannot recreate the dashboard {key}: Home Assistant's dashboard "
            "collection could not be reached, so the entry cannot be "
            "registered in a way it would keep. Create a dashboard with the "
            f"URL {key} under Settings > Dashboards, then run this restore "
            "again to put its cards back."
        )

    # Logged at info on purpose: after a Home Assistant update, which path
    # ran is the first question anybody will ask.
    _LOGGER.info("Recreating dashboard %s through Home Assistant's collection", key)
    await live.async_create_item(item)
    return None


async def async_save_config(hass: HomeAssistant, key: str, config: dict) -> None:
    """Write a configuration back into a live dashboard.

    Goes through the same Lovelace object the interface uses, so Home
    Assistant fires its own events and every other listener sees the
    change - including our own recording.
    """
    dashboards = _lovelace_dashboards(hass)
    if dashboards is None:
        raise HomeAssistantError("Lovelace data is not available")
    for url_path, dashboard in dashboards.items():
        if dashboard_key(url_path) == key:
            await dashboard.async_save(config)
            return
    raise HomeAssistantError(f"unknown dashboard: {key}")
