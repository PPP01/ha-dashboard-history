"""Every operation the integration offers, in one place.

The services and the panel are both thin skins over this module. The panel
is the layer most likely to break, and letting it grow logic of its own
would put the important part exactly there. So it gets none.

Nothing here writes without an explicit `confirm`; without it each
restoring operation answers with a preview and changes nothing.
"""

from __future__ import annotations

import difflib
import logging

from homeassistant.core import HomeAssistant

from .analyze import find_removed
from .keys import is_absent, is_live
from .restore import reinsert
from .snapshot import (
    async_create_dashboard,
    async_get_all_meta,
    async_get_config,
    async_known_keys,
    async_save_config,
)
from .store import HistoryStore
from .yaml_io import dump, load

_LOGGER = logging.getLogger(__name__)


def _diff(old: dict, new: dict, name: str) -> str:
    """A unified diff between two configurations, empty when equal."""
    return "".join(
        difflib.unified_diff(
            dump(old).splitlines(keepends=True),
            dump(new).splitlines(keepends=True),
            fromfile=f"live/{name}",
            tofile=f"restored/{name}",
        )
    )


async def _state_at(
    hass: HomeAssistant, store: HistoryStore, key: str, revision: str
) -> tuple[str | None, str | None, str | None]:
    """The dashboard text at a revision, or a message saying why not.

    The two failures are told apart on purpose. "Unknown revision" is a
    statement about the input; "did not exist" is a statement about the
    dashboard's history. Reporting the second when the first is true sends
    people looking for a fault in their dashboard instead of in what they
    typed - and an abbreviated hash, which is what `git log --oneline`
    prints, used to land exactly there.
    """
    full = await hass.async_add_executor_job(store.resolve, revision)
    if full is None:
        return None, None, f"unknown revision: {revision}"
    text = await hass.async_add_executor_job(store.read_at, key, full)
    if text is None:
        return full, None, f"{key} did not exist at {full[:10]}"
    return full, text, None


async def async_dashboards(hass: HomeAssistant, store: HistoryStore) -> dict:
    """Every dashboard the panel can offer, live ones and deleted ones.

    A deleted dashboard is listed too, and marked as such. That is not a
    courtesy: it is the one somebody opens this tool to find.
    """
    tracked = set(await hass.async_add_executor_job(store.list_dashboards))
    ever = await hass.async_add_executor_job(store.list_all_dashboards)
    known = await async_known_keys(hass)
    meta = await async_get_all_meta(hass)

    dashboards = []
    for key in ever:
        exists = is_live(key, tracked, known)
        info = meta.get(key)
        if info is None:
            # Gone, so Home Assistant can say nothing about it. Its own last
            # recorded name is better than falling back to the bare key.
            text = await hass.async_add_executor_job(store.last_known_meta, key)
            info = (load(text) if text else None) or {}
        dashboards.append(
            {
                "key": key,
                "title": info.get("title") or key,
                "icon": info.get("icon"),
                "exists": exists,
            }
        )
    return {"dashboards": dashboards}


async def async_history(
    hass: HomeAssistant, store: HistoryStore, key: str, limit: int = 50
) -> dict:
    """The recorded states of one dashboard, newest first."""
    changes = await hass.async_add_executor_job(store.list_changes, key, limit)
    return {
        "changes": [
            {"revision": c.revision, "timestamp": c.timestamp, "message": c.message}
            for c in changes
        ]
    }


async def async_deleted_since(
    hass: HomeAssistant, store: HistoryStore, key: str, revision: str
) -> dict:
    """What was present at a revision and is gone now."""
    _, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"items": [], "error": error}
    current = await async_get_config(hass, key) or {}
    items = find_removed(load(text) or {}, current)
    return {
        "items": [
            {
                "position": position,
                "kind": item.kind,
                "label": item.label,
                "view": item.view_path,
            }
            for position, item in enumerate(items)
        ]
    }


async def async_restore_deleted(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    position: int,
    confirm: bool = False,
) -> dict:
    """Put one disappeared card or view back."""
    _, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"applied": False, "error": error}
    current = await async_get_config(hass, key) or {}
    items = find_removed(load(text) or {}, current)
    if not items:
        return {"applied": False, "error": "nothing is missing since that revision"}
    if not 0 <= position < len(items):
        return {
            "applied": False,
            "error": f"position {position} out of range (0..{len(items) - 1})",
        }
    try:
        restored = reinsert(current, items[position])
    except LookupError as err:
        # The place it belonged to is gone. Every other failure here answers
        # with a message rather than an exception; this one should too, or
        # the caller is handed a bare traceback.
        return {"applied": False, "error": str(err)}
    diff = _diff(current, restored, key)
    if not confirm:
        return {"applied": False, "preview": diff}
    await async_save_config(hass, key, restored)
    return {"applied": True, "preview": diff, "restored": items[position].label}


async def async_restore_state(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
) -> dict:
    """Set a dashboard back to an earlier state, creating it if it is gone."""
    full, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"applied": False, "error": error}
    target = load(text) or {}

    # A dashboard that is gone entirely is restored, not refused. It is the
    # heaviest loss this tool can witness; refusing exactly there while
    # offering everything for a single card made no sense.
    known = await async_known_keys(hass)
    missing = is_absent(key, known)
    current = {} if missing else (await async_get_config(hass, key) or {})
    diff = _diff(current, target, key)
    if not diff and not missing:
        return {"applied": False, "preview": "", "note": "already identical"}
    if not confirm:
        return {"applied": False, "preview": diff, "creates_dashboard": missing}

    created = False
    note: str | None = None
    if missing:
        meta_text = await hass.async_add_executor_job(store.read_meta_at, key, full)
        if meta_text is None:
            # Nothing recorded at that exact point; the last name it had is
            # still much better than falling back to the bare key.
            meta_text = await hass.async_add_executor_job(store.last_known_meta, key)
        meta = (load(meta_text) if meta_text else None) or {}
        note = await async_create_dashboard(hass, key, meta)
        created = True
    await async_save_config(hass, key, target)
    result = {"applied": True, "preview": diff, "created": created}
    if note:
        result["note"] = note
    return result


async def async_create_version(
    hass: HomeAssistant,
    store: HistoryStore,
    name: str,
    title: str,
    description: str = "",
    revision: str | None = None,
) -> dict:
    """Mark a point in the history with a name, title and description."""
    if revision:
        resolved = await hass.async_add_executor_job(store.resolve, revision)
        if resolved is None:
            return {"created": None, "error": f"unknown revision: {revision}"}
        revision = resolved
    await hass.async_add_executor_job(
        store.create_version, name, title, description, revision
    )
    return {"created": name}


async def async_versions(hass: HomeAssistant, store: HistoryStore) -> dict:
    """Every named point in the history."""
    found = await hass.async_add_executor_job(store.list_versions)
    return {
        "versions": [
            {
                "name": v.name,
                "revision": v.revision,
                "title": v.title,
                "description": v.description,
            }
            for v in found
        ]
    }
