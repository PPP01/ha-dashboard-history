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


_LABEL_LIMIT = 48


def _shorten(text: str) -> str:
    """Collapse whitespace and cut to a length that fits a list."""
    text = " ".join(text.split())
    if len(text) <= _LABEL_LIMIT:
        return text
    return text[: _LABEL_LIMIT - 1].rstrip() + "\u2026"


def _first_line(card: dict) -> str | None:
    """The first meaningful line of a card's own text, if it has any."""
    for field in ("content", "text"):
        value = card.get(field)
        if isinstance(value, str):
            for line in value.splitlines():
                line = line.lstrip("#").strip()
                if line:
                    return line
    return None


def _first_entity(card: dict) -> str | None:
    """The first entity of a card that is defined by a list of them."""
    entities = card.get("entities")
    if not isinstance(entities, list) or not entities:
        return None
    first = entities[0]
    name = first.get("entity") if isinstance(first, dict) else first
    return str(name) if name else None


def _inner_card(card: dict) -> dict | None:
    """The card a wrapper wraps, if there is an obvious first one."""
    inner = card.get("card")
    if isinstance(inner, dict):
        return inner
    cards = card.get("cards")
    if isinstance(cards, list) and cards and isinstance(cards[0], dict):
        return cards[0]
    return None


def _weak_key(card: Any, depth: int = 0):
    """A content-based identity, good enough to recognise an edited card.

    All of this exists to prevent one specific failure: an edited card read
    as a deletion plus an addition. The interface would then offer to
    restore something that is not missing, and a false alarm of that kind
    destroys trust in exactly the message people open the tool for.

    Which is why it reaches well past entity, title and name. Counted on
    the installation this was built against, most cards carry none of the
    three: 62 headings, 76 entity lists without a title, and 261 wrappers
    whose only content is the card inside them. Identifying by the most
    stable field first is deliberate - an entity outlives a renamed title.
    """
    if not isinstance(card, dict):
        return None
    kind = card.get("type")
    for field in ("entity", "title", "name", "heading"):
        if card.get(field):
            return (kind, field, str(card[field]))
    entity = _first_entity(card)
    if entity is not None:
        return (kind, "entities", entity)
    line = _first_line(card)
    if line is not None:
        # The first line, not the whole text: editing the body below it
        # must not change what the card is.
        return (kind, "text", line)
    if depth < 3:
        inner = _inner_card(card)
        if inner is not None:
            key = _weak_key(inner, depth + 1)
            # Only when the card inside can be named at all. Otherwise two
            # different anonymous wrappers would look like the same card,
            # and a real deletion would be missed.
            if key is not None:
                return (kind, "inside", key)
    return None


def _describe(card: Any, depth: int = 0) -> str:
    """A short human-readable label for a card.

    The field order differs from _weak_key on purpose: identity wants the
    most stable field, a label wants the most human one.
    """
    if not isinstance(card, dict):
        return str(card)
    kind = str(card.get("type", "card"))
    for field in ("title", "name", "heading", "entity"):
        if card.get(field):
            return f"{kind}: {_shorten(str(card[field]))}"
    line = _first_line(card)
    if line is not None:
        return f"{kind}: {_shorten(line)}"
    entity = _first_entity(card)
    if entity is not None:
        rest = len(card["entities"]) - 1
        return f"{kind}: {_shorten(entity)}" + (f" +{rest}" if rest else "")
    if depth < 4:
        inner = _inner_card(card)
        if inner is not None:
            label = _describe(inner, depth + 1)
            # Nested wrappers hand the name up unchanged. A chain of four
            # container types tells nobody which card this was; the name of
            # the first thing inside that has one does.
            return label if depth else f"{kind} > {label}"
    return kind


def _match_cards(old_cards: list, new_cards: list):
    """Return (removed_indices, added_indices, edited_pairs, moved_pairs)."""
    unmatched_new = list(range(len(new_cards)))
    removed: list[int] = []
    edited: list[tuple[int, int]] = []
    exact: list[tuple[int, int]] = []

    # Pass one: exact content matches. Same card, possibly at a new index.
    pending: list[int] = []
    for old_index, card in enumerate(old_cards):
        match = next((j for j in unmatched_new if new_cards[j] == card), None)
        if match is None:
            pending.append(old_index)
            continue
        unmatched_new.remove(match)
        exact.append((old_index, match))

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

    return removed, unmatched_new, edited, _moved(exact, edited)


def _moved(
    exact: list[tuple[int, int]], edited: list[tuple[int, int]]
) -> list[tuple[int, int]]:
    """Which matched cards changed position *relative to each other*.

    A raw index comparison calls every card behind a deletion moved. On a
    large view that is twenty entries of noise wrapped around the single
    fact that matters, and it is not what anyone means by "moved" either.
    What people mean is a change in the order, so that is what is
    measured: a card's rank among the survivors, before against after.

    Edited cards take part in the ranking - they still hold a position -
    but are not reported here, because they are already reported as edited.
    """
    pairs = sorted(exact + edited)
    old_rank = {old: rank for rank, (old, _) in enumerate(pairs)}
    new_rank = {
        new: rank for rank, (_, new) in enumerate(sorted(pairs, key=lambda p: p[1]))
    }
    return [(old, new) for old, new in exact if old_rank[old] != new_rank[new]]


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
