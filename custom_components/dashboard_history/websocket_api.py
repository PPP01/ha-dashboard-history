"""WebSocket commands, for the panel to build on.

The same thin skin the services wear, over the same `operations` module.
The panel is the layer most likely to break as Home Assistant moves; it
gets no logic of its own, so a broken panel costs a view and never a
feature.

Every command requires an administrator. Restoring a dashboard rewrites
what everyone in the house sees.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant

from . import operations
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

_DASHBOARD = {vol.Required("dashboard"): str}
_REVISION = {vol.Required("revision"): str}


def _command(
    name: str,
    schema: dict,
    run: Callable[..., Coroutine[Any, Any, dict]],
    args: Callable[[dict], dict],
):
    """Wrap one operation as a WebSocket command."""

    @websocket_api.require_admin
    @websocket_api.websocket_command({vol.Required("type"): name, **schema})
    @websocket_api.async_response
    async def handler(hass: HomeAssistant, connection, msg: dict) -> None:
        store = hass.data.get(DOMAIN, {}).get("store")
        if store is None:
            connection.send_error(msg["id"], "not_ready", "integration is not set up")
            return
        try:
            result = await run(hass, store, **args(msg))
        except Exception as err:  # noqa: BLE001 - a panel must not see a traceback
            _LOGGER.exception("WebSocket command %s failed", name)
            connection.send_error(msg["id"], "failed", str(err))
            return
        connection.send_result(msg["id"], result)

    return handler


_COMMANDS = (
    _command(
        f"{DOMAIN}/dashboards", {}, operations.async_dashboards, lambda msg: {}
    ),
    _command(
        f"{DOMAIN}/history",
        {
            **_DASHBOARD,
            # At least one: with zero there is no oldest entry to point
            # from, and the answer would claim there is nothing older.
            vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1)),
            vol.Optional("before"): vol.Any(None, str),
        },
        operations.async_history,
        lambda msg: {
            "key": msg["dashboard"],
            "limit": msg["limit"],
            "before": msg.get("before"),
        },
    ),
    _command(
        f"{DOMAIN}/deleted_since",
        {**_DASHBOARD, **_REVISION},
        operations.async_deleted_since,
        lambda msg: {"key": msg["dashboard"], "revision": msg["revision"]},
    ),
    _command(
        f"{DOMAIN}/restore_deleted",
        {
            **_DASHBOARD,
            **_REVISION,
            vol.Required("position"): int,
            vol.Optional("confirm", default=False): bool,
        },
        operations.async_restore_deleted,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "position": msg["position"],
            "confirm": msg["confirm"],
        },
    ),
    _command(
        f"{DOMAIN}/restore_state",
        {
            **_DASHBOARD,
            **_REVISION,
            vol.Optional("confirm", default=False): bool,
            # Only shaped here, never judged: an unknown level is
            # answered by operations with a sentence the panel can show,
            # and a schema that refused first would take that sentence
            # away. The same reason create_version takes free text.
            vol.Optional("keep_as_version"): vol.Any(
                None,
                vol.Schema(
                    {
                        vol.Optional("level", default="patch"): str,
                        vol.Required("title"): str,
                        vol.Optional("description", default=""): str,
                    }
                ),
            ),
        },
        operations.async_restore_state,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "confirm": msg["confirm"],
            "keep_as_version": msg.get("keep_as_version"),
        },
    ),
    _command(
        f"{DOMAIN}/undo_change",
        {**_DASHBOARD, **_REVISION, vol.Optional("confirm", default=False): bool},
        operations.async_undo_change,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "confirm": msg["confirm"],
        },
    ),
    _command(
        f"{DOMAIN}/describe",
        {**_REVISION, vol.Optional("text", default=""): str},
        operations.async_describe,
        lambda msg: {"revision": msg["revision"], "text": msg["text"]},
    ),
    _command(
        f"{DOMAIN}/explain",
        {**_DASHBOARD, **_REVISION},
        operations.async_explain,
        lambda msg: {"key": msg["dashboard"], "revision": msg["revision"]},
    ),
    _command(
        f"{DOMAIN}/forget",
        {**_DASHBOARD, vol.Optional("confirm", default=False): bool},
        operations.async_forget,
        lambda msg: {"key": msg["dashboard"], "confirm": msg["confirm"]},
    ),
    _command(
        f"{DOMAIN}/versions",
        {vol.Optional("dashboard"): vol.Any(str, None)},
        operations.async_versions,
        lambda msg: {"key": msg.get("dashboard")},
    ),
    _command(
        f"{DOMAIN}/next_versions",
        {**_DASHBOARD},
        operations.async_next_versions,
        lambda msg: {"key": msg["dashboard"]},
    ),
    _command(
        f"{DOMAIN}/create_version",
        {
            **_DASHBOARD,
            # Free text, not vol.In - see the note under services.py. A
            # schema that refuses first means operations never gets to
            # answer, and the sentence it would have answered with is the
            # one the panel shows a person.
            vol.Optional("level", default="patch"): str,
            vol.Required("title"): str,
            vol.Optional("description", default=""): str,
            vol.Optional("revision"): vol.Any(str, None),
        },
        operations.async_create_version,
        lambda msg: {
            "key": msg["dashboard"],
            "level": msg["level"],
            "title": msg["title"],
            "description": msg["description"],
            "revision": msg.get("revision"),
        },
    ),
)


def async_register(hass: HomeAssistant) -> None:
    """Register every WebSocket command."""
    for handler in _COMMANDS:
        websocket_api.async_register_command(hass, handler)
