"""Classifying what changed between two dashboard configurations.

Lovelace cards carry no identifier — a card is defined by its position in
a list. Matching them between two states therefore has to work from their
content, and that shapes everything here.

The order matters: an exact content match wins first (that card is
unchanged, possibly moved), then a weak match on type plus the most
identifying field (that card was edited). Only what is left over counts
as removed. Without that ordering an edited card would look like a
deletion plus an addition, and the interface would offer to restore
something that is still there.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RemovedItem:
    """Something that was present before and is gone now."""

    kind: str  # "card" or "view"
    view_path: str | None
    view_index: int  # position of the view in the old configuration
    location: tuple  # path to the card list inside the view
    index: int  # position in the card list, or of the view itself
    payload: dict
    label: str


@dataclass(frozen=True)
class Summary:
    """How many cards were added, removed, edited and moved."""

    added: int = 0
    removed: int = 0
    edited: int = 0
    moved: int = 0


def card_containers(view: dict) -> Iterator[tuple[tuple, list]]:
    """Yield every card list in a view, with the path that locates it.

    Views come in two shapes: the classic one with a flat `cards` list,
    and the sections layout where each section holds its own list.
    """
    if isinstance(view.get("cards"), list):
        yield ("cards",), view["cards"]
    for index, section in enumerate(view.get("sections") or []):
        if isinstance(section, dict) and isinstance(section.get("cards"), list):
            yield ("sections", index, "cards"), section["cards"]


def _weak_key(card: Any):
    """A content-based identity, good enough to recognise an edited card."""
    if not isinstance(card, dict):
        return None
    for field in ("entity", "title", "name"):
        if field in card:
            return (card.get("type"), field, str(card[field]))
    return None


def _describe(card: Any) -> str:
    """A short human-readable label for a card."""
    if not isinstance(card, dict):
        return str(card)
    for field in ("title", "name", "entity"):
        if card.get(field):
            return f"{card.get('type', 'card')}: {card[field]}"
    return str(card.get("type", "card"))


def _match_cards(old_cards: list, new_cards: list):
    """Return (removed_indices, added_indices, edited_pairs, moved_pairs)."""
    unmatched_new = list(range(len(new_cards)))
    removed: list[int] = []
    edited: list[tuple[int, int]] = []
    moved: list[tuple[int, int]] = []

    # Pass one: exact content matches. Same card, possibly at a new index.
    pending: list[int] = []
    for old_index, card in enumerate(old_cards):
        match = next((j for j in unmatched_new if new_cards[j] == card), None)
        if match is None:
            pending.append(old_index)
            continue
        unmatched_new.remove(match)
        if match != old_index:
            moved.append((old_index, match))

    # Pass two: weak matches among what is left. Same card, edited.
    for old_index in pending:
        key = _weak_key(old_cards[old_index])
        match = (
            next((j for j in unmatched_new if _weak_key(new_cards[j]) == key), None)
            if key is not None
            else None
        )
        if match is None:
            removed.append(old_index)
        else:
            unmatched_new.remove(match)
            edited.append((old_index, match))

    return removed, unmatched_new, edited, moved


def _views_by_key(config: dict) -> list[tuple[Any, dict]]:
    """Views paired with the key that identifies them across states."""
    result = []
    for index, view in enumerate(config.get("views") or []):
        if not isinstance(view, dict):
            continue
        result.append((view.get("path") or ("#", index), view))
    return result


def find_removed(old: dict, new: dict) -> list[RemovedItem]:
    """Everything that disappeared between two states.

    Only disappearances are reported. Restoring them is additive — nothing
    is overwritten — and therefore always well defined, which is not true
    for undoing an edit.
    """
    new_views = dict(_views_by_key(new))
    items: list[RemovedItem] = []

    for view_index, (key, old_view) in enumerate(_views_by_key(old)):
        new_view = new_views.get(key)
        if new_view is None:
            items.append(
                RemovedItem(
                    kind="view",
                    view_path=old_view.get("path"),
                    view_index=view_index,
                    location=(),
                    index=view_index,
                    payload=old_view,
                    label=f"view: {old_view.get('title') or old_view.get('path') or key}",
                )
            )
            continue

        new_containers = dict(card_containers(new_view))
        for location, old_cards in card_containers(old_view):
            new_cards = new_containers.get(location, [])
            removed, _, _, _ = _match_cards(old_cards, new_cards)
            for index in removed:
                items.append(
                    RemovedItem(
                        kind="card",
                        view_path=old_view.get("path"),
                        view_index=view_index,
                        location=location,
                        index=index,
                        payload=old_cards[index],
                        label=_describe(old_cards[index]),
                    )
                )
    return items


def summarize(old: dict, new: dict) -> Summary:
    """Count what changed, for the history display."""
    new_views = dict(_views_by_key(new))
    added = removed = edited = moved = 0

    for key, old_view in _views_by_key(old):
        new_view = new_views.get(key)
        if new_view is None:
            removed += sum(len(cards) for _, cards in card_containers(old_view))
            continue
        new_containers = dict(card_containers(new_view))
        for location, old_cards in card_containers(old_view):
            r, a, e, m = _match_cards(old_cards, new_containers.get(location, []))
            removed += len(r)
            added += len(a)
            edited += len(e)
            # One entry per moved card already, so a swap contributes
            # two. Multiplying would count each of them twice.
            moved += len(m)

    old_keys = {key for key, _ in _views_by_key(old)}
    for key, new_view in _views_by_key(new):
        if key not in old_keys:
            added += sum(len(cards) for _, cards in card_containers(new_view))

    return Summary(added=added, removed=removed, edited=edited, moved=moved)
