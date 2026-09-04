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
    from .analyze import RemovedItem, UndoPlan, UndoStep


def _find_view(views: list, item: RemovedItem | UndoStep) -> dict | None:
    """Locate the view an item belongs to, by path or by position.

    Both kinds of instruction carry the same two fields, so both take
    this route: a `RemovedItem` from `find_removed`, an `UndoStep` from
    `plan_undo`.
    """
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


def _anchor_holds(view: dict, item: RemovedItem) -> bool:
    """Whether the section at that index is still the one the card left.

    Only cards that sat in a section carry an anchor, so everything else
    passes straight through. Measured on 2026-09-04: without this, a card
    whose section had been pushed along by a new neighbour was filed in
    that neighbour instead - no error, no mention in the preview.
    """
    if item.anchor is None:
        return True
    count, title = item.anchor
    sections = view.get("sections") or []
    if len(sections) != count:
        return False
    index = item.location[1]
    if not isinstance(index, int) or not 0 <= index < len(sections):
        return False
    section = sections[index]
    return isinstance(section, dict) and section.get("title") == title


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

    if not _anchor_holds(view, item):
        raise LookupError(
            "the section this card sat in is not the one standing at that "
            "place now, so putting it back would file it in a stranger"
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


def _cards_for(views: list, step: UndoStep) -> list:
    """The card list a step points at, or a refusal."""
    view = _find_view(views, step)
    if view is None:
        raise LookupError(
            f"the view {step.label} belonged to no longer exists "
            f"(path={step.view_path!r}, index={step.view_index})"
        )
    cards = _cards_at(view, step.location)
    if cards is None:
        raise LookupError(
            f"the card list {step.label} belonged to no longer exists "
            f"(location={step.location!r})"
        )
    return cards


def _standing_there(items: list, step: UndoStep) -> None:
    """Refuse unless the expected thing is still at that index."""
    if step.index >= len(items) or items[step.index] != step.expect:
        raise LookupError(
            f"{step.label} is no longer where the undo was planned for it"
        )


def apply_undo(config: dict, plan: UndoPlan) -> dict:
    """Return a new configuration with an undo plan applied.

    The order is not a detail. Removals first, highest index first, so
    an earlier removal never shifts a later one. Insertions last, lowest
    index first, so each one lands at the index it was given. Any other
    order silently writes to the wrong place.

    There is no replacement step, deliberately: a card is put back by
    being removed where it sits today and inserted where it came from.
    An edit can move a card as well, and a replacement written in place
    would then land on its neighbour - the reasoning and the measurement
    are in `plan_undo`, which is where that is decided.

    Every removal checks that the thing it was planned for is still
    standing there. The plan was made against a state read a moment
    earlier, and a moment is enough for somebody to press save - so this
    refuses rather than overwrites. `LookupError` carries a sentence a
    person can read; the caller turns it into an answer.

    The configuration handed in is never modified.
    """
    if plan.blocked is not None:
        raise LookupError(plan.blocked)
    result = copy.deepcopy(config)
    views = result.setdefault("views", [])

    # Cards before views: a card step finds its view by path, but falls
    # back to the index, and removing a view first would move it.
    removals = [step for step in plan.steps if step.action == "remove"]
    for step in sorted(
        (step for step in removals if step.kind == "card"), key=lambda s: -s.index
    ):
        cards = _cards_for(views, step)
        _standing_there(cards, step)
        del cards[step.index]
    for step in sorted(
        (step for step in removals if step.kind == "view"), key=lambda s: -s.index
    ):
        # Located, not indexed. `_views_by_key` skips anything that is not
        # a dict, so its position and the position in `views` are the same
        # only until somebody writes a stray list entry - and a wrong index
        # here deletes the wrong view.
        view = _find_view(views, step)
        if view is None or view != step.expect:
            raise LookupError(
                f"{step.label} is no longer where the undo was planned for it"
            )
        del views[views.index(view)]

    for step in sorted(
        (step for step in plan.steps if step.action == "insert"),
        key=lambda s: s.index,
    ):
        if step.kind == "view":
            views.insert(min(step.index, len(views)), copy.deepcopy(step.payload))
            continue
        cards = _cards_for(views, step)
        # If the list has shrunk since, append rather than fail - the same
        # trade `reinsert` makes, and for the same reason. What this undo
        # proves is that the change's own cards are untouched, never that
        # their neighbourhood is; `equals_state_before` in the caller is
        # what tells the truth about the whole state.
        cards.insert(min(step.index, len(cards)), copy.deepcopy(step.payload))
    return result
