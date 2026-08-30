"""Putting removed items back into a live configuration.

Restoring a disappearance is additive: nothing is overwritten, so there
is no merge and no ambiguity. That is the whole reason this integration
restricts itself to disappearances rather than trying to undo edits.

The configuration handed in is never modified. The caller still needs the
old state to render a preview against.
"""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only needed for the annotations, and `from __future__ import
    # annotations` keeps those lazy. A real import would have to be
    # relative inside the integration and absolute in the tests, which
    # load this module flat - it cannot be both.
    from .analyze import RemovedItem


def _find_view(views: list, item: RemovedItem) -> dict | None:
    """Locate the view an item belongs to, by path or by position."""
    if item.view_path is not None:
        for view in views:
            if isinstance(view, dict) and view.get("path") == item.view_path:
                return view
        return None
    if 0 <= item.view_index < len(views):
        candidate = views[item.view_index]
        return candidate if isinstance(candidate, dict) else None
    return None


def _cards_at(view: dict, location: tuple) -> list | None:
    """Walk to the card list a location points at."""
    current = view
    for step in location:
        if isinstance(step, int):
            if not isinstance(current, list) or step >= len(current):
                return None
            current = current[step]
        else:
            if not isinstance(current, dict) or step not in current:
                return None
            current = current[step]
    return current if isinstance(current, list) else None


def reinsert(config: dict, item: RemovedItem) -> dict:
    """Return a new configuration with `item` put back.

    Raises LookupError when the place it belonged to no longer exists —
    guessing a different place would be worse than refusing.
    """
    result = copy.deepcopy(config)
    views = result.setdefault("views", [])

    if item.kind == "view":
        views.insert(min(item.index, len(views)), copy.deepcopy(item.payload))
        return result

    view = _find_view(views, item)
    if view is None:
        raise LookupError(
            f"the view this card belonged to no longer exists "
            f"(path={item.view_path!r}, index={item.view_index})"
        )

    cards = _cards_at(view, item.location)
    if cards is None:
        raise LookupError(
            f"the card list this card belonged to no longer exists "
            f"(location={item.location!r})"
        )

    # If the list has shrunk since, append rather than fail: getting the
    # card back matters more than getting its exact old position back.
    cards.insert(min(item.index, len(cards)), copy.deepcopy(item.payload))
    return result
