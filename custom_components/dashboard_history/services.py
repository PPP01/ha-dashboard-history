"""Services: every operation, usable from Developer Tools.

A thin skin over `operations`. The panel wears the same skin over the same
module, so neither can drift from the other.

Nothing writes without `confirm: true`. Every restoring service returns a
preview otherwise.

Every service requires an administrator, exactly like the WebSocket
commands and the panel. Found on 2026-09-03: Home Assistant's
`call_service` checks no permissions of its own, so a plain
`async_register` let any signed-in user - one who may not edit a
dashboard in the frontend - restore one, read its whole configuration
from the preview, or forget a history for good. Registered as admin
services, a call from a user who is not one is refused with
`Unauthorized`; a call without a user, from an automation, still runs.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.service import async_register_admin_service

from . import operations
from .const import DOMAIN
from .snapshot import async_get_all_configs

_LOGGER = logging.getLogger(__name__)

DASHBOARD = vol.Schema({vol.Required("dashboard"): cv.string})


async def async_register(hass: HomeAssistant) -> None:
    """Register every service."""
    store = hass.data[DOMAIN]["store"]

    async def debug_snapshot(call: ServiceCall) -> dict:
        """Report what the integration can currently see.

        Kept permanently. On any later hunt for a fault this answers the
        first question - whether the dashboards are visible at all. In
        this table with the others so that every rule the table applies -
        admin only, response only - reaches it without a second place to
        remember.
        """
        configs = await async_get_all_configs(hass)
        return {
            "count": len(configs),
            "dashboards": {
                key: {"views": len(config.get("views") or [])}
                for key, config in sorted(configs.items())
            },
        }

    async def history(call: ServiceCall) -> dict:
        return await operations.async_history(
            hass, store, call.data["dashboard"], call.data.get("limit", 50)
        )

    async def search(call: ServiceCall) -> dict:
        return await operations.async_search(
            hass, store, call.data["dashboard"], call.data["text"],
            call.data.get("limit", 50),
        )

    async def deleted_since(call: ServiceCall) -> dict:
        return await operations.async_deleted_since(
            hass, store, call.data["dashboard"], call.data["revision"]
        )

    async def restore_deleted(call: ServiceCall) -> dict:
        return await operations.async_restore_deleted(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            call.data["position"],
            bool(call.data.get("confirm")),
        )

    async def restore_state(call: ServiceCall) -> dict:
        return await operations.async_restore_state(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            call.data.get("confirm", False),
            call.data.get("keep_as_version"),
        )

    async def undo_change(call: ServiceCall) -> dict:
        return await operations.async_undo_change(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            bool(call.data.get("confirm")),
        )

    async def describe(call: ServiceCall) -> dict:
        return await operations.async_describe(
            hass, store, call.data["revision"], call.data.get("text", "")
        )

    async def explain(call: ServiceCall) -> dict:
        return await operations.async_explain(
            hass, store, call.data["dashboard"], call.data["revision"]
        )

    async def forget(call: ServiceCall) -> dict:
        return await operations.async_forget(
            hass, store, call.data["dashboard"], bool(call.data.get("confirm"))
        )

    async def next_versions(call: ServiceCall) -> dict:
        return await operations.async_next_versions(
            hass, store, call.data["dashboard"]
        )

    async def create_version(call: ServiceCall) -> dict:
        return await operations.async_create_version(
            hass,
            store,
            call.data["dashboard"],
            call.data.get("level", "patch"),
            call.data["title"],
            call.data.get("description", ""),
            call.data.get("revision"),
        )

    async def versions(call: ServiceCall) -> dict:
        return await operations.async_versions(
            hass, store, call.data.get("dashboard")
        )

    registrations = [
        ("debug_snapshot", debug_snapshot, vol.Schema({})),
        ("history", history, DASHBOARD.extend({vol.Optional("limit", default=50): int})),
        ("search", search, DASHBOARD.extend({
            vol.Required("text"): cv.string,
            vol.Optional("limit", default=50): int,
        })),
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
            vol.Optional("keep_as_version"): vol.Any(None, dict),
        })),
        ("undo_change", undo_change, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Optional("confirm", default=False): bool,
        })),
        ("describe", describe, vol.Schema({
            vol.Required("revision"): cv.string,
            vol.Optional("text", default=""): cv.string,
        })),
        ("explain", explain, DASHBOARD.extend({vol.Required("revision"): cv.string})),
        ("forget", forget, DASHBOARD.extend({
            vol.Optional("confirm", default=False): bool,
        })),
        ("next_versions", next_versions, DASHBOARD),
        ("create_version", create_version, DASHBOARD.extend({
            vol.Optional("level", default="patch"): cv.string,
            vol.Required("title"): cv.string,
            vol.Optional("description", default=""): cv.string,
            vol.Optional("revision"): cv.string,
        })),
        ("versions", versions, vol.Schema({vol.Optional("dashboard"): cv.string})),
    ]
    for name, handler, schema in registrations:
        async_register_admin_service(
            hass, DOMAIN, name, handler, schema=schema,
            supports_response=SupportsResponse.ONLY,
        )
