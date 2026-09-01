"""Registering the sidebar panel.

`panel_custom` is the supported way to put a page of one's own into Home
Assistant, which is why the panel uses it rather than any of the cleverer
routes. It is reachable at all times, not only while a dashboard is being
edited - that was the whole complaint this project started from.

Registration is best effort. A missing panel costs a view; the services
still do everything, and the recording carries on regardless.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    PANEL_COMPONENT,
    PANEL_ICON,
    PANEL_TITLE,
    PANEL_URL_PATH,
    PANEL_VERSION,
)

_LOGGER = logging.getLogger(__name__)

_MODULE_URL = f"/{DOMAIN}/panel.js"
_SOURCE = Path(__file__).parent / "panel.js"


def _fingerprint() -> str:
    """A short digest of panel.js, for the cache-busting query."""
    return hashlib.sha256(_SOURCE.read_bytes()).hexdigest()[:12]


async def _async_module_url(hass: HomeAssistant) -> str:
    """The module URL, with a version that changes when the file does.

    This used to be a hand-maintained constant, and that is a cache bug
    with a delay built into it: the browser keyed the module on
    `panel.js?v=0.1.0`, so a released update served the old panel to
    everyone until somebody remembered to bump the number. Home Assistant
    sets no Cache-Control on a static path, only ETag and Last-Modified,
    which makes the failure intermittent rather than obvious - the worst
    kind.

    A digest of the file changes exactly when the file does, and not
    otherwise, so caching keeps working across restarts.
    """
    try:
        return f"{_MODULE_URL}?v={await hass.async_add_executor_job(_fingerprint)}"
    except OSError:
        # Unreadable file: the static path will fail too, and the panel is
        # best effort. Fall back rather than take the setup down with it.
        _LOGGER.warning("Could not fingerprint panel.js; falling back to the version")
        return f"{_MODULE_URL}?v={PANEL_VERSION}"


async def _async_serve_module(hass: HomeAssistant) -> None:
    """Make panel.js reachable, on whichever API this Home Assistant has."""
    source = str(_SOURCE)
    register_many = getattr(hass.http, "async_register_static_paths", None)
    if register_many is not None:
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

        await register_many([StaticPathConfig(_MODULE_URL, source, False)])
        return
    # Older releases only had the singular, synchronous form.
    hass.http.register_static_path(_MODULE_URL, source, False)


async def async_register(hass: HomeAssistant) -> bool:
    """Put the panel in the sidebar. Returns whether it is there."""
    if PANEL_URL_PATH in hass.data.get("frontend_panels", {}):
        return True
    try:
        await _async_serve_module(hass)
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_URL_PATH,
            webcomponent_name=PANEL_COMPONENT,
            module_url=await _async_module_url(hass),
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            require_admin=True,
        )
    except Exception:  # noqa: BLE001 - a missing panel costs a view, nothing more
        _LOGGER.exception("Could not register the Dashboard History panel")
        return False
    return True


def async_unregister(hass: HomeAssistant) -> None:
    """Take the panel out of the sidebar again."""
    try:
        frontend.async_remove_panel(hass, PANEL_URL_PATH)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("Panel was not registered", exc_info=True)
