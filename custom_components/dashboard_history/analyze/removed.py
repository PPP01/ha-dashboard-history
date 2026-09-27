"""What a change removed, for Put back."""

from __future__ import annotations

from .matching import (
    _section_anchor,
    match_cards,
)
from .model import (
    RemovedItem,
    Slot,
    _describe,
    _section_title,
    _view_name,
    _views_by_key,
)


def find_removed(old: dict, new: dict) -> list[RemovedItem]:
    """Everything that disappeared between two states.

    Only disappearances are reported. Restoring them is additive - nothing
    is overwritten - and therefore always well defined, which is not true
    for undoing an edit.

    A card that merely moved does not appear here. It is not missing, and
    putting it back would leave the dashboard holding it twice.
    """
    new_views = dict(_views_by_key(new))
    matching = match_cards(old, new)
    gone_by_view: dict[int, list[Slot]] = {}
    for slot in matching.loose_removed():
        gone_by_view.setdefault(slot.view_index, []).append(slot)
    # Cards that left their place for another list: no survivor a
    # section has to keep for its anchor to hold (spec L, 4a).
    away_by_view: dict[int, set] = {}
    departed_by_view: dict[int, set] = {}
    for was, now in matching.moved:
        if not matching.same_place(was, now):
            away_by_view.setdefault(was.view_index, set()).add((was.location, was.index))
            if now.view_key == was.view_key:
                departed_by_view.setdefault(was.view_index, set()).add((was.location, was.index))

    items: list[RemovedItem] = []
    for view_index, (key, old_view) in enumerate(_views_by_key(old)):
        # Resolved once per view, the same way `_explain` names the group
        # it heads its own diff with - so a caller that groups these items
        # by view can head each group the identical name.
        name = _view_name(old_view, key)
        if key not in new_views:
            items.append(
                RemovedItem(
                    kind="view",
                    view_path=old_view.get("path"),
                    view_index=view_index,
                    location=(),
                    index=view_index,
                    payload=old_view,
                    label=f"view: {name}",
                    view_title=name,
                )
            )
            continue
        gone = gone_by_view.get(view_index, [])
        left = {(slot.location, slot.index) for slot in gone} | away_by_view.get(view_index, set())
        # A section that went whole is one item, not one per card on it -
        # its cards are already out of `gone` (`loose_removed`).
        whole = {
            slot.index: slot.section
            for slot in matching.sections.removed
            if slot.view_key == key
        }
        for index, section in whole.items():
            items.append(
                RemovedItem(
                    kind="section",
                    view_path=old_view.get("path"),
                    view_index=view_index,
                    location=("sections",),
                    index=index,
                    payload=section,
                    label=_section_title(section, index),
                    neighbours=tuple(
                        other
                        for position, other in enumerate(old_view.get("sections") or [])
                        if position != index
                    ),
                    view_title=name,
                )
            )
        items += [
            RemovedItem(
                kind="card",
                view_path=old_view.get("path"),
                view_index=view_index,
                location=slot.location,
                index=slot.index,
                payload=slot.card,
                label=_describe(slot.card),
                anchor=_section_anchor(old_view, slot.location, slot.index, left, departed_by_view.get(view_index, set())),
                view_title=name,
            )
            for slot in gone
        ]
    return items
