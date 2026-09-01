"""Services: every operation, usable from Developer Tools.

A thin skin over `operations`. The panel wears the same skin over the same
module, so neither can drift from the other.

Nothing writes without `confirm: true`. Every restoring service returns a
preview otherwise.
"""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.helpers import config_validation as cv

from . import operations
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

DASHBOARD = vol.Schema({vol.Required("dashboard"): cv.string})


async def async_register(hass: HomeAssistant) -> None:
    """Register every service."""
    store = hass.data[DOMAIN]["store"]

    async def history(call: ServiceCall) -> dict:
        return await operations.async_history(
            hass, store, call.data["dashboard"], call.data.get("limit", 50)
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

    async def create_version(call: ServiceCall) -> dict:
        return await operations.async_create_version(
            hass,
            store,
            call.data["name"],
            call.data["title"],
            call.data.get("description", ""),
            call.data.get("revision"),
        )

    async def versions(call: ServiceCall) -> dict:
        return await operations.async_versions(hass, store)

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
        ("describe", describe, vol.Schema({
            vol.Required("revision"): cv.string,
            vol.Optional("text", default=""): cv.string,
        })),
        ("explain", explain, DASHBOARD.extend({vol.Required("revision"): cv.string})),
        ("forget", forget, DASHBOARD.extend({
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
