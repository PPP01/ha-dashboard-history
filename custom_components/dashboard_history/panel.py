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
_PARTS_URL = f"/{DOMAIN}/panel"
_SOURCE = Path(__file__).parent / "panel.js"
_PARTS = Path(__file__).parent / "panel"


def _fingerprint() -> str:
    """A short digest of every file the panel is built from.

    Every file, not only the entry point. The parts are fetched with the
    entry point's own query string, so digesting `panel.js` alone would
    serve a stale part whenever only a part changed - the same
    intermittent cache failure the hand-maintained version number caused,
    one level down and considerably harder to spot.

    The file name goes into the digest as well, so that renaming a part
    changes the fingerprint even when its contents do not.
    """
    digest = hashlib.sha256()
    for path in [_SOURCE, *sorted(_PARTS.glob("*.js"))]:
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]


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
    """Make panel.js and its parts reachable, on whichever API this has."""
    paths = [(_MODULE_URL, str(_SOURCE)), (_PARTS_URL, str(_PARTS))]
    register_many = getattr(hass.http, "async_register_static_paths", None)
    if register_many is not None:
        from homeassistant.components.http import StaticPathConfig  # noqa: PLC0415

        await register_many(
            [StaticPathConfig(url, source, False) for url, source in paths]
        )
        return
    # Older releases only had the singular, synchronous form.
    for url, source in paths:
        hass.http.register_static_path(url, source, False)


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
