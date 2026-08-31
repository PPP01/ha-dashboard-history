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


def _dashboards_collection(hass: HomeAssistant):
    """Home Assistant's live dashboard collection, if it can be reached.

    Creating through the live collection is much the better path: Home
    Assistant's own listener then registers the panel and builds the
    dashboard object, and nothing here has to imitate it.
    """
    data = hass.data.get(LOVELACE_DATA_KEY)
    for name in ("dashboards_collection", "dashboard_collection", "collection"):
        candidate = getattr(data, name, None)
        if candidate is not None and hasattr(candidate, "async_create_item"):
            return candidate
    return None


async def async_create_dashboard(hass: HomeAssistant, key: str, meta: dict) -> bool:
    """Recreate a deleted dashboard. Returns whether it is usable at once.

    Two steps, graded differently on purpose. Writing the registry entry
    **must** succeed - without it the dashboard does not exist and the
    restore has failed, so a failure here is raised. Making it appear
    without a restart is the bonus: it needs objects Home Assistant
    promises nobody, so it is attempted and its failure is only reported.
    A dashboard that comes back after a restart is a restored dashboard.
    """
    from homeassistant.components.lovelace.dashboard import (  # noqa: PLC0415
        DashboardsCollection,
    )

    item = {
        "url_path": key,
        "title": meta.get("title") or key,
        "show_in_sidebar": meta.get("show_in_sidebar", True),
        "require_admin": meta.get("require_admin", False),
    }
    if meta.get("icon"):
        item["icon"] = meta["icon"]

    live = _dashboards_collection(hass)
    if live is not None:
        # Home Assistant's own listener now registers the panel and builds
        # the dashboard object; nothing here has to imitate it.
        _LOGGER.info("Recreating dashboard %s through the live collection", key)
        await live.async_create_item(item)
        return True

    # No reachable collection: write the entry through one of our own, then
    # imitate what Home Assistant's listener would have done. Logged at info
    # on purpose - after a Home Assistant update, which path ran is the
    # first question anybody will ask.
    _LOGGER.info(
        "Recreating dashboard %s through a collection of our own; "
        "no live collection was reachable",
        key,
    )
    collection = DashboardsCollection(hass)
    await collection.async_load()
    created = await collection.async_create_item(item)
    return await _async_make_live(hass, key, created or item)


async def _async_make_live(hass: HomeAssistant, key: str, item: dict) -> bool:
    """Best effort: make a recreated dashboard usable without a restart."""
    try:
        from homeassistant.components.frontend import (  # noqa: PLC0415
            async_register_built_in_panel,
        )
        from homeassistant.components.lovelace.dashboard import (  # noqa: PLC0415
            LovelaceStorage,
        )

        dashboards = _lovelace_dashboards(hass)
        if dashboards is None:
            return False
        dashboards[item["url_path"]] = LovelaceStorage(hass, item)
        kwargs: dict = {
            "frontend_url_path": item["url_path"],
            "require_admin": item.get("require_admin", False),
            "config": {"mode": MODE_STORAGE},
            "update": False,
        }
        if item.get("show_in_sidebar", True):
            kwargs["sidebar_title"] = item.get("title") or key
            kwargs["sidebar_icon"] = item.get("icon")
        async_register_built_in_panel(hass, LOVELACE_DATA_KEY, **kwargs)
    except Exception:  # noqa: BLE001 - the durable part already succeeded
        _LOGGER.exception(
            "Dashboard %s was restored but needs a restart to appear", key
        )
        return False
    return True


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
