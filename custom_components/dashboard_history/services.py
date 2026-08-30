"""Services: the whole feature, usable from Developer Tools.

The interface comes later. Everything it will need has to work here
first — that way the interface cannot quietly grow logic of its own.

Nothing writes without `confirm: true`. Every restoring service returns a
preview otherwise.
"""

from __future__ import annotations

import difflib
import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from .analyze import find_removed
from .const import DOMAIN
from .restore import reinsert
from .snapshot import async_get_config, async_save_config
from .yaml_io import dump, load

_LOGGER = logging.getLogger(__name__)

DASHBOARD = vol.Schema({vol.Required("dashboard"): cv.string})


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


async def async_register(hass: HomeAssistant) -> None:
    """Register every service."""
    data = hass.data[DOMAIN]
    store = data["store"]

    async def history(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        limit = call.data.get("limit", 50)
        changes = await hass.async_add_executor_job(store.list_changes, key, limit)
        return {
            "changes": [
                {"revision": c.revision, "timestamp": c.timestamp, "message": c.message}
                for c in changes
            ]
        }

    async def deleted_since(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        revision = call.data["revision"]
        text = await hass.async_add_executor_job(store.read_at, key, revision)
        if text is None:
            return {"items": [], "error": f"{key} does not exist at {revision}"}
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

    async def restore_deleted(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        revision = call.data["revision"]
        position = call.data["position"]
        text = await hass.async_add_executor_job(store.read_at, key, revision)
        if text is None:
            return {"applied": False, "error": f"{key} does not exist at {revision}"}
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
            # The place it belonged to is gone. Every other failure here
            # answers with a message rather than an exception; this one
            # should too, or the developer tools show a bare traceback.
            return {"applied": False, "error": str(err)}
        diff = _diff(current, restored, key)
        if not call.data.get("confirm"):
            return {"applied": False, "preview": diff}
        await async_save_config(hass, key, restored)
        return {"applied": True, "preview": diff, "restored": items[position].label}

    async def restore_state(call: ServiceCall) -> dict:
        key = call.data["dashboard"]
        revision = call.data["revision"]
        text = await hass.async_add_executor_job(store.read_at, key, revision)
        if text is None:
            return {"applied": False, "error": f"{key} does not exist at {revision}"}
        target = load(text) or {}
        current = await async_get_config(hass, key) or {}
        diff = _diff(current, target, key)
        if not diff:
            return {"applied": False, "preview": "", "note": "already identical"}
        if not call.data.get("confirm"):
            return {"applied": False, "preview": diff}
        await async_save_config(hass, key, target)
        return {"applied": True, "preview": diff}

    async def create_version(call: ServiceCall) -> dict:
        await hass.async_add_executor_job(
            store.create_version,
            call.data["name"],
            call.data["title"],
            call.data.get("description", ""),
            call.data.get("revision"),
        )
        return {"created": call.data["name"]}

    async def versions(call: ServiceCall) -> dict:
        found = await hass.async_add_executor_job(store.list_versions)
        return {
            "versions": [
                {"name": v.name, "revision": v.revision,
                 "title": v.title, "description": v.description}
                for v in found
            ]
        }

    registrations = [
        ("history", history, DASHBOARD.extend({vol.Optional("limit", default=50): int})),
        ("deleted_since", deleted_since,
         DASHBOARD.extend({vol.Required("revision"): cv.string})),
        ("restore_deleted", restore_deleted, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Required("position"): int,
            vol.Optional("confirm", default=False): bool,
        })),
        ("restore_state", restore_state, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Optional("confirm", default=False): bool,
        })),
        ("create_version", create_version, vol.Schema({
            vol.Required("name"): cv.string,
            vol.Required("title"): cv.string,
            vol.Optional("description", default=""): cv.string,
            vol.Optional("revision"): cv.string,
        })),
        ("versions", versions, vol.Schema({})),
    ]
    for name, handler, schema in registrations:
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema,
            supports_response=SupportsResponse.ONLY,
        )
