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

import json
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
    # What the section this card sat in looked like, when it sat in one:
    # how many sections the view had, and that section's title. A section
    # carries no path and no id, so its index is its only address - and
    # an address is exactly what stops being true when the neighbours
    # change. `restore` refuses rather than file the card in a stranger.
    anchor: tuple | None = None


@dataclass(frozen=True)
class Summary:
    """How many cards were added, removed, edited and moved.

    Whole views are counted apart from cards, and as one each - the same
    grain the explanation uses, where a view that appears or disappears
    is one line and not one per card on it.
    """

    added: int = 0
    removed: int = 0
    edited: int = 0
    moved: int = 0
    views_added: int = 0
    views_removed: int = 0


@dataclass(frozen=True)
class Entry:
    """One nameable thing that changed."""

    kind: str  # "removed", "added", "edited" or "moved"
    what: str  # "card" or "view"
    label: str
    text: str  # the finished sentence, ready to show


@dataclass(frozen=True)
class ViewChanges:
    """What changed in one view. `more` is what the cap left out."""

    view: str
    entries: list[Entry]
    more: int = 0


@dataclass(frozen=True)
class Explanation:
    """A diff in words. `note` carries what the groups cannot say."""

    groups: list[ViewChanges]
    note: str = ""


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


@dataclass(frozen=True)
class Slot:
    """One card at the place it sits in a dashboard.

    Matching used to happen inside a single card list, which is why a
    card that crossed any boundary - into another view, into another
    section - was unmatched on both sides at once and read as a deletion
    plus an addition. Carrying the place along with the card is what lets
    the passes below cross those boundaries deliberately rather than
    never.
    """

    view_key: Any
    view_index: int
    view: dict
    location: tuple
    index: int
    card: Any


@dataclass(frozen=True)
class Matching:
    """Every card of one dashboard, paired across two of its states."""

    removed: list
    added: list
    edited: list  # (old, new)
    moved: list  # (old, new)


@dataclass(frozen=True)
class UndoStep:
    """One mechanical edit, addressed the way `RemovedItem` is.

    `expect` is what has to sit at that place for the step to be
    applied. It travels with the step so the writing side can refuse
    rather than overwrite something it never looked at: the plan is made
    against a state read a moment earlier, and a moment is enough for
    somebody to press save.

    It answers one question and not the other: *is this still that
    card*, never *is this the right destination*. The destination lives
    on the old side of the change, and only an insertion carries it -
    which is why a card is put back by being removed and inserted rather
    than written over in place.
    """

    action: str  # "remove" | "insert"
    kind: str  # "card" | "view"
    view_path: str | None
    view_index: int
    location: tuple
    index: int
    expect: Any
    payload: Any
    label: str


@dataclass(frozen=True)
class UndoPlan:
    """Either a reason not to take a change back, or the steps that do.

    Never both. A half-applied undo leaves a state nobody asked for and
    which the row beside it no longer describes, so one unresolvable
    piece blocks the whole thing - decision 15.
    """

    blocked: str | None
    steps: tuple = ()


def _slots(config: dict, keys: set) -> list[Slot]:
    """Every card of the named views, in the order they are written."""
    found: list[Slot] = []
    for view_index, (key, view) in enumerate(_views_by_key(config)):
        if key not in keys:
            continue
        for location, cards in card_containers(view):
            for index, card in enumerate(cards):
                found.append(Slot(key, view_index, view, location, index, card))
    return found


def _similarity(old_card: Any, new_card: Any) -> float:
    """How alike two card configurations are, between 0 and 1.

    Top-level fields only, and deliberately so: this decides between
    candidates that already share a weak key, so it needs to separate
    "same card, one field edited" from "different card of the same type
    on the same entity". Counting fields does that, and a reader can work
    out the number by hand - which matters for a value that decides which
    card gets offered back.
    """
    if old_card == new_card:
        return 1.0
    if not isinstance(old_card, dict) or not isinstance(new_card, dict):
        return 0.0
    fields = set(old_card) | set(new_card)
    if not fields:
        return 1.0
    return sum(1 for f in fields if old_card.get(f) == new_card.get(f)) / len(fields)


def fingerprint(card: Any) -> str:
    """A card reduced to one string, equal exactly when the cards are.

    Two jobs, and the second is the heavier one. It makes the exact
    passes of `match_cards` linear instead of quadratic. And it is the
    *identity* an undo is addressed by: a card whose fingerprint occurs
    once in a dashboard can be pointed at without an `id` field, which
    is what decision 15 rests on. Anything that made two different cards
    share a fingerprint would make an undo overwrite the wrong one.

    `sort_keys` because two cards that differ only in the order their
    keys were written are the same card - YAML and the frontend do not
    agree on an order, and neither should this. `default=str` so a value
    no encoder expected cannot take the recording down; the worst it can
    do is make two cards look different that are not, which reads as an
    edit rather than as a crash.
    """
    try:
        return json.dumps(card, sort_keys=True, default=str)
    except (TypeError, ValueError):  # pragma: no cover - guarded, not expected
        return repr(card)


def _place(slot: Slot) -> tuple:
    """The card list a slot belongs to, across the whole dashboard."""
    return (slot.view_key, slot.location)


def match_cards(old: dict, new: dict) -> Matching:
    """Pair the cards of two states of one dashboard.

    Four passes, and their order carries the whole correctness.

    1. **Identical, in the same place.** The ordinary case.
    2. **Identical, anywhere on the dashboard.** What is left over is
       looked for everywhere else: a card found there moved, and a moved
       card is not missing. Offering it back would put a second copy on
       the dashboard.
    3. **Same weak key, in the same place, best match first.** Not the
       first match: with two cards of one type on one entity, taking the
       first married the *deleted* card to the survivor and then declared
       the survivor deleted - offering back a card still on the
       dashboard, while the one really gone was never offered. Pairing
       the most similar candidates first settles it.
    4. Whatever is left: gone on the old side, new on the new side.

    Pass 1 must run before pass 2, and that is not a detail. Delete a card
    from one view while an identical one sits untouched in another, and a
    global pass running first would marry the deleted card to the
    untouched one and swallow the deletion whole. Claiming every card at
    its own place first leaves the deletion where it belongs.

    Views that only one state has are left out entirely - a whole view
    appearing or disappearing is reported as one line, not as one per
    card on it.

    One gap, named rather than closed: a card that moved *and* changed in
    the same save is matched by neither pass 2 (no longer identical) nor
    pass 3 (no longer in the same place), so it still reads as a deletion
    plus an addition. Weak matching across views would close it and open
    a worse hole, because the same entity on two views is ordinary.
    """
    old_keys = {key for key, _ in _views_by_key(old)}
    new_keys = {key for key, _ in _views_by_key(new)}
    common = old_keys & new_keys
    old_open = _slots(old, common)
    new_open = _slots(new, common)

    taken_old: set[int] = set()
    taken_new: set[int] = set()
    in_place: list[tuple[int, int]] = []
    displaced: list[tuple[int, int]] = []
    edited: list[tuple[int, int]] = []

    def claim(pairs: list, i: int, j: int) -> None:
        taken_old.add(i)
        taken_new.add(j)
        pairs.append((i, j))

    # Passes 1 and 2 look for exact equality, so they are done through a
    # fingerprint rather than by comparing every old card against every
    # new one. That comparison is quadratic over the whole dashboard, and
    # measured before this: 0.9 ms at a hundred cards but 78 ms at twelve
    # hundred, on a path that runs at every save *and* every time a row
    # is expanded. Pass 3 stays quadratic and may: it only ever sees the
    # cards the first two passes could not place, which is one or two.
    here: dict[tuple, list[int]] = {}
    anywhere: dict[str, list[int]] = {}
    for j, new_slot in enumerate(new_open):
        mark = fingerprint(new_slot.card)
        here.setdefault((_place(new_slot), mark), []).append(j)
        anywhere.setdefault(mark, []).append(j)

    for pairs, buckets, at_place in (
        (in_place, here, True),
        (displaced, anywhere, False),
    ):
        for i, old_slot in enumerate(old_open):
            if i in taken_old:
                continue
            mark = fingerprint(old_slot.card)
            waiting = buckets.get((_place(old_slot), mark) if at_place else mark, ())
            match = next((j for j in waiting if j not in taken_new), None)
            if match is not None:
                claim(pairs, i, match)

    candidates: list[tuple[float, int, int]] = []
    for i, old_slot in enumerate(old_open):
        if i in taken_old:
            continue
        key = _weak_key(old_slot.card)
        if key is None:
            continue
        for j, new_slot in enumerate(new_open):
            if j in taken_new or _place(new_slot) != _place(old_slot):
                continue
            if _weak_key(new_slot.card) == key:
                candidates.append((_similarity(old_slot.card, new_slot.card), i, j))
    # Best first; ties settled by the order the cards are written in, so
    # the same pair of states always produces the same answer.
    for _score, i, j in sorted(candidates, key=lambda c: (-c[0], c[1], c[2])):
        if i not in taken_old and j not in taken_new:
            claim(edited, i, j)

    return Matching(
        removed=[slot for i, slot in enumerate(old_open) if i not in taken_old],
        added=[slot for j, slot in enumerate(new_open) if j not in taken_new],
        edited=[(old_open[i], new_open[j]) for i, j in edited],
        moved=[(old_open[i], new_open[j]) for i, j in displaced]
        + _reordered(old_open, new_open, in_place, edited),
    )


def _reordered(
    old_open: list[Slot],
    new_open: list[Slot],
    in_place: list[tuple[int, int]],
    edited: list[tuple[int, int]],
) -> list[tuple[Slot, Slot]]:
    """Which cards that stayed put changed position *relative to each other*.

    A raw index comparison calls every card behind a deletion moved. On a
    large view that is twenty entries of noise wrapped around the single
    fact that matters, and it is not what anyone means by "moved" either.
    What people mean is a change in the order, so that is what is
    measured: a card's rank among the survivors of its own card list,
    before against after.

    Edited cards take part in the ranking - they still hold a position -
    but are not reported here, because they are already reported as
    edited.
    """
    kept = set(in_place)
    grouped: dict[tuple, list[tuple[int, int]]] = {}
    for pair in in_place + edited:
        grouped.setdefault(_place(old_open[pair[0]]), []).append(pair)

    out: list[tuple[Slot, Slot]] = []
    for pairs in grouped.values():
        old_rank = {
            i: rank
            for rank, (i, _) in enumerate(sorted(pairs, key=lambda p: old_open[p[0]].index))
        }
        new_rank = {
            j: rank
            for rank, (_, j) in enumerate(sorted(pairs, key=lambda p: new_open[p[1]].index))
        }
        out += [
            (old_open[i], new_open[j])
            for i, j in pairs
            if (i, j) in kept and old_rank[i] != new_rank[j]
        ]
    return out


def _views_by_key(config: dict) -> list[tuple[Any, dict]]:
    """Views paired with the key that identifies them across states."""
    result = []
    for index, view in enumerate(config.get("views") or []):
        if not isinstance(view, dict):
            continue
        result.append((view.get("path") or ("#", index), view))
    return result


def _by_position(config: dict) -> dict:
    """Only the views keyed by where they sit, by that key."""
    return {
        key: view
        for key, view in _views_by_key(config)
        if isinstance(key, tuple) and key and key[0] == "#"
    }


def _positions_lie(one: dict, other: dict) -> bool:
    """Whether a position means a different view in the two states.

    A path is an identity; a position is an address. Delete the view in
    front of a pathless one, or drop a new one before it, and the same
    key names something else - measured on 2026-09-04 against a running
    Home Assistant, that wrote a card onto a view nobody had touched and,
    in one case, emptied the dashboard.

    Two things make a position trustworthy here, and nothing else does:
    the same set of positions in both states, and the same view standing
    at each of them. "The same view" is content or, for a view somebody
    edited, a title that is there and unchanged.

    Deliberately strict. A pathless view *added* since is refused too,
    though its neighbours may still line up - the identity chain of
    package 2 is what lifts that, and until it exists a refusal is the
    answer decision 4 asks for.
    """
    here, there = _by_position(one), _by_position(other)
    if set(here) != set(there):
        return True
    for key, view in here.items():
        standing = there[key]
        if view == standing:
            continue
        title = view.get("title")
        if title is not None and title == standing.get("title"):
            continue
        return True
    return False


def _section_marks(view: dict) -> list:
    """The titles of a view's sections, in order - all the identity there is."""
    return [
        section.get("title") if isinstance(section, dict) else None
        for section in view.get("sections") or []
    ]


def _sections_lie(one: dict, other: dict) -> bool:
    """Whether a section index means a different section in the two states.

    Same reasoning as `_positions_lie`, one level down and without the
    escape hatch: a view can have a path, a section never does. Any
    change to the run of sections - one added, one removed, one renamed,
    two swapped - makes every index below it point somewhere new.

    Sections without titles in a reordered view slip through this. The
    identity chain of package 2 is what closes that; a title is what
    there is to work with today.
    """
    here, there = dict(_views_by_key(one)), dict(_views_by_key(other))
    return any(
        _section_marks(here[key]) != _section_marks(there[key])
        for key in set(here) & set(there)
    )


def _section_anchor(view: dict, location: tuple) -> tuple | None:
    """How to recognise the section a card sat in, or None outside one."""
    if len(location) < 2 or location[0] != "sections":
        return None
    sections = view.get("sections") or []
    index = location[1]
    title = None
    if isinstance(index, int) and 0 <= index < len(sections):
        section = sections[index]
        if isinstance(section, dict):
            title = section.get("title")
    return (len(sections), title)


_POSITION_REFUSAL = (
    "a view without a URL path sits somewhere else now, so an exact undo "
    "cannot tell which view is which"
)

_SECTION_REFUSAL = (
    "the sections of this dashboard are arranged differently now, and a "
    "section has no path to recognise it by, so an exact undo cannot tell "
    "them apart"
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
    gone_by_view: dict[int, list[Slot]] = {}
    for slot in match_cards(old, new).removed:
        gone_by_view.setdefault(slot.view_index, []).append(slot)

    items: list[RemovedItem] = []
    for view_index, (key, old_view) in enumerate(_views_by_key(old)):
        if key not in new_views:
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
        items += [
            RemovedItem(
                kind="card",
                view_path=old_view.get("path"),
                view_index=view_index,
                location=slot.location,
                index=slot.index,
                payload=slot.card,
                label=_describe(slot.card),
                anchor=_section_anchor(old_view, slot.location),
            )
            for slot in gone_by_view.get(view_index, [])
        ]
    return items


def _present(config: dict) -> list[Slot]:
    """Every card of a state, with the place it sits in."""
    return _slots(config, {key for key, _ in _views_by_key(config)})


def _step(slot: Slot, action: str, expect: Any, payload: Any, label: str) -> UndoStep:
    """A card step at the place `slot` names."""
    return UndoStep(
        action=action,
        kind="card",
        view_path=slot.view.get("path"),
        view_index=slot.view_index,
        location=slot.location,
        index=slot.index,
        expect=expect,
        payload=payload,
        label=label,
    )


def plan_undo(before: dict, after: dict, current: dict) -> UndoPlan:
    """How to take one change back, or why that cannot be exact.

    The change is read as `match_cards(before, after)` - what it removed,
    added, edited and moved. For everything it *produced*, the plan then
    asks one question of the state as it stands today: does this card sit
    there exactly once? Once means it can be pointed at. Zero means
    somebody changed it again since. Two or more means an undo would have
    to guess which - and guessing is what decision 4 forbids.

    Note which side is looked up. The check is on what the change left
    behind, never on its surroundings: a card added *next to* an edited
    one does not make the edit ambiguous, and blocking there would refuse
    almost every real history.
    """
    matching = match_cards(before, after)
    old_views = dict(_views_by_key(before))
    new_views = dict(_views_by_key(after))
    now_views = dict(_views_by_key(current))
    view_work = set(old_views) ^ set(new_views)
    if not (
        matching.removed
        or matching.added
        or matching.edited
        or matching.moved
        or view_work
    ):
        return UndoPlan(blocked="this change did not alter any cards")

    # Every state this plan reads from or writes to has to agree on what
    # a position means: `before` and `after` decide what the change was,
    # `current` is where the steps land.
    pairs = ((before, after), (before, current), (after, current))
    if any(_positions_lie(one, other) for one, other in pairs):
        return UndoPlan(blocked=_POSITION_REFUSAL)
    if any(_sections_lie(one, other) for one, other in pairs):
        return UndoPlan(blocked=_SECTION_REFUSAL)

    by_mark: dict[str, list[Slot]] = {}
    for slot in _present(current):
        by_mark.setdefault(fingerprint(slot.card), []).append(slot)

    def sole(card: Any, label: str) -> tuple[Slot | None, str | None]:
        found = by_mark.get(fingerprint(card), [])
        if len(found) == 1:
            return found[0], None
        if not found:
            return None, (
                f"{label} was changed again after this, so there is no "
                f"exact version left to put back"
            )
        return None, (
            f"{len(found)} cards now look exactly like {label}, so an "
            f"exact undo cannot tell them apart"
        )

    steps: list[UndoStep] = []

    # An edit and a move are the same undo: take the card off the place
    # it sits on today, and put it back on the place it came from. Two
    # steps rather than one replacement, and that is the whole point -
    # `_place` leaves the index out, so a card that was edited *and*
    # shifted arrives here as edited, and a replacement written at
    # today's index would land on its neighbour. Measured over 6000
    # generated histories: 48 silently wrong results that way, none this
    # way, and not one refusal more.
    for old_slot, new_slot in (*matching.edited, *matching.moved):
        label = _describe(new_slot.card)
        here, why = sole(new_slot.card, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label))
        steps.append(_step(old_slot, "insert", None, old_slot.card, label))

    for new_slot in matching.added:
        label = _describe(new_slot.card)
        here, why = sole(new_slot.card, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label))

    for old_slot in matching.removed:
        # Already back by some other route. Inserting would make a second
        # copy, and this part of the change is undone either way.
        if by_mark.get(fingerprint(old_slot.card)):
            continue
        steps.append(
            _step(old_slot, "insert", None, old_slot.card, _describe(old_slot.card))
        )

    # Whole views, which `match_cards` leaves out on purpose: a view that
    # only one state has is one line in the history, not one per card on
    # it. Undoing it is the same two questions in a coarser grain - is it
    # still exactly as the change left it, and is it still there at all.
    #
    # Both branches ask that of the view's *content*, not of its key. A
    # key is a path, and a path is renameable and reusable: asking only
    # whether one is present answers "already taken back" for a view
    # somebody renamed, and "already back" for a stranger that happens to
    # sit on the same path. Both are the one error this tool must never
    # make - a sentence that says nothing changed while something did.
    now_places = _views_by_key(current)

    for key, view in _views_by_key(after):
        if key in old_views:
            continue
        # The change added this view. Take it away - the very one it
        # added, found by what it holds.
        name = _view_name(view, key)
        found = [
            index for index, (_, standing) in enumerate(now_places) if standing == view
        ]
        if len(found) > 1:
            return UndoPlan(
                blocked=f'{len(found)} views now look exactly like "{name}", '
                f"so an exact undo cannot tell them apart"
            )
        if not found:
            if key in now_views:
                return UndoPlan(
                    blocked=f'the view "{name}" was changed again after this'
                )
            return UndoPlan(
                blocked=f'the view "{name}" is no longer on the dashboard as '
                f"this change left it, so an exact undo cannot take it away"
            )
        index = found[0]
        steps.append(
            UndoStep(
                action="remove",
                kind="view",
                view_path=view.get("path"),
                view_index=index,
                location=(),
                index=index,
                expect=view,
                payload=None,
                label=f'view: {name}',
            )
        )

    for index, (key, view) in enumerate(_views_by_key(before)):
        if key in new_views:
            # The change did not remove it.
            continue
        # Already back, either on its own path or - a view without one is
        # keyed by its position - somewhere else. Inserting would make a
        # second copy.
        if any(standing == view for _, standing in now_places):
            continue
        standing = now_views.get(key)
        if standing is not None and view.get("path") is not None:
            # A different view holds that path today. Two views on one
            # path is a broken dashboard, and picking one of them is a
            # guess, so this refuses instead.
            return UndoPlan(
                blocked=f'a different view now sits at "{view["path"]}", so the '
                f'view "{_view_name(view, key)}" cannot be put back there'
            )
        steps.append(
            UndoStep(
                action="insert",
                kind="view",
                view_path=view.get("path"),
                view_index=index,
                location=(),
                index=index,
                expect=None,
                payload=view,
                label=f'view: {_view_name(view, key)}',
            )
        )

    return UndoPlan(blocked=None, steps=tuple(steps))


def summarize(old: dict, new: dict) -> Summary:
    """Count what changed, for the history display."""
    matching = match_cards(old, new)

    # A whole view arriving or leaving is one view, not the sum of its
    # cards. It used to be counted by its cards, on the argument that a
    # count says how much - and the message then contradicted the
    # explanation of the very same commit: "1 removed, 1 added" beside
    # 'the whole view "home" was deleted', or "no card changes" for a
    # renamed view that happened to be empty. One grain for both.
    old_keys = {key for key, _ in _views_by_key(old)}
    new_keys = {key for key, _ in _views_by_key(new)}

    # One entry per moved card already, so a swap contributes two.
    # Multiplying would count each of them twice.
    return Summary(
        added=len(matching.added),
        removed=len(matching.removed),
        edited=len(matching.edited),
        moved=len(matching.moved),
        views_added=len(new_keys - old_keys),
        views_removed=len(old_keys - new_keys),
    )


# Card labels already carry their type ("tile: light.b"), so they need no
# quotes. A view label is a bare name and does.
_PAST = {
    ("card", "removed"): "{label} was deleted",
    ("card", "added"): "{label} was added",
    ("card", "edited"): "{label} was changed",
    ("card", "moved"): "{label} was moved",
    ("card", "moved_to"): "{label} was moved to {where}",
    ("view", "removed"): 'the whole view "{label}" was deleted',
    ("view", "added"): 'the whole view "{label}" was added',
}

_FUTURE = {
    ("card", "removed"): "{label} will be deleted",
    ("card", "added"): "{label} comes back",
    ("card", "edited"): "{label} goes back to how it was",
    ("card", "moved"): "{label} moves back to where it was",
    ("card", "moved_to"): "{label} moves back to {where}",
    ("view", "removed"): 'the whole view "{label}" will be deleted',
    ("view", "added"): 'the whole view "{label}" comes back',
}

# A dashboard restored from nothing would otherwise list every card it
# ever had - 661 of them on the installation this was built against.
_ENTRY_LIMIT = 12

_NOTHING_LOST = "Nothing on this dashboard is deleted."
_NOT_IN_CARDS = (
    "This change cannot be described in terms of cards - see the details below."
)


def _view_name(view: dict, key) -> str:
    """What to call a view: its title, else its path, else its position."""
    return str(view.get("title") or view.get("path") or key)


def _entry(words: dict, kind: str, what: str, label: str) -> Entry:
    return Entry(
        kind=kind,
        what=what,
        label=label,
        text=words[(what, kind)].format(label=label),
    )


def _capped(name: str, entries: list[Entry]) -> ViewChanges:
    """Keep the list readable, and say how much it hides.

    Silently truncating would be the one thing this project must not do:
    a summary that omits without saying so is worse than a long one.
    """
    if len(entries) <= _ENTRY_LIMIT:
        return ViewChanges(view=name, entries=entries)
    return ViewChanges(
        view=name,
        entries=entries[:_ENTRY_LIMIT],
        more=len(entries) - _ENTRY_LIMIT,
    )


def _section_name(slot: Slot) -> str:
    """The section a card landed in, named the way Home Assistant names one.

    Not by a `title` field: measured on the installation this was built
    against, 0 of 80 sections carry one. Home Assistant names a section
    with a `heading` card at its top instead, and 51 of those 80 have
    one. Where there is none there is no name to give, and saying so
    beats inventing one.
    """
    if slot.location[:1] != ("sections",):
        return "another place in this view"
    sections = slot.view.get("sections") or []
    index = slot.location[1]
    section = sections[index] if 0 <= index < len(sections) else {}
    cards = (section or {}).get("cards") or []
    first = cards[0] if cards else None
    if isinstance(first, dict) and first.get("type") == "heading" and first.get("heading"):
        return f'the section "{first["heading"]}"'
    return "another section"


def _where(old_slot: Slot, new_slot: Slot) -> str:
    """Where a card went, said from the place it left."""
    if new_slot.view_key != old_slot.view_key:
        return f'"{_view_name(new_slot.view, new_slot.view_key)}"'
    return _section_name(new_slot)


def _explain(old: dict, new: dict, words: dict, reassure: bool) -> Explanation:
    """The engine behind both tenses.

    `reassure` says whether a "nothing is lost" line is wanted when
    nothing is removed. It is passed rather than inferred from `words`:
    identity of a wording table is not the question being asked.

    Cards are grouped by the view they sat in *before*. A card that left
    for another view is reported in the view it left - that is where
    somebody who misses it looks - and it says where it went instead of
    leaving them to guess.
    """
    matching = match_cards(old, new)
    by_view: dict[Any, list[Entry]] = {}

    def add(key: Any, entry: Entry) -> None:
        by_view.setdefault(key, []).append(entry)

    for slot in matching.removed:
        add(slot.view_key, _entry(words, "removed", "card", _describe(slot.card)))
    for slot in matching.added:
        add(slot.view_key, _entry(words, "added", "card", _describe(slot.card)))
    for _was, now in matching.edited:
        add(now.view_key, _entry(words, "edited", "card", _describe(now.card)))
    for was, now in matching.moved:
        label = _describe(was.card)
        if _place(was) == _place(now):
            add(was.view_key, _entry(words, "moved", "card", label))
        else:
            add(
                was.view_key,
                Entry(
                    kind="moved",
                    what="card",
                    label=label,
                    text=words[("card", "moved_to")].format(
                        label=label, where=_where(was, now)
                    ),
                ),
            )

    new_views = dict(_views_by_key(new))
    old_keys = {key for key, _ in _views_by_key(old)}
    groups: list[ViewChanges] = []
    removed_anything = False

    for key, old_view in _views_by_key(old):
        name = _view_name(old_view, key)
        if key not in new_views:
            # One line for the view, not one per card on it.
            groups.append(ViewChanges(name, [_entry(words, "removed", "view", name)]))
            removed_anything = True
            continue
        entries = by_view.get(key, [])
        if entries:
            groups.append(_capped(name, entries))
            removed_anything = removed_anything or any(
                entry.kind == "removed" for entry in entries
            )

    for key, new_view in _views_by_key(new):
        if key not in old_keys:
            name = _view_name(new_view, key)
            groups.append(ViewChanges(name, [_entry(words, "added", "view", name)]))

    if not groups:
        # Something changed - the caller only asks when it did - but not
        # anything this can name. Saying "nothing changed" above a diff
        # that shows the difference would be refuted at a glance.
        return Explanation(groups=[], note=_NOT_IN_CARDS)
    if removed_anything or not reassure:
        return Explanation(groups=groups)
    return Explanation(groups=groups, note=_NOTHING_LOST)


def explain_change(old: dict, new: dict) -> Explanation:
    """What one recorded change did, in words. Past tense."""
    return _explain(old, new, _PAST, reassure=False)


def explain_effect(current: dict, target: dict) -> Explanation:
    """What applying a restore would do, in words. Future tense.

    The reassurance matters here and not in the past tense: before
    pressing Apply, the question is not what changed but what is at risk.
    """
    return _explain(current, target, _FUTURE, reassure=True)


def _meta_detail(old_meta: dict | None, new_meta: dict | None) -> str:
    """What changed about a dashboard, as opposed to on it."""
    if not new_meta or old_meta is None or old_meta == new_meta:
        return "metadata recorded"
    if new_meta.get("title") and old_meta.get("title") != new_meta.get("title"):
        return f'renamed to "{new_meta["title"]}"'
    fields = sorted(
        field
        for field in set(old_meta) | set(new_meta)
        if old_meta.get(field) != new_meta.get(field)
    )
    return f"{', '.join(fields)} changed" if fields else "metadata recorded"


def _views(count: int, verb: str) -> str:
    """"1 view removed", "2 views added", or nothing."""
    if not count:
        return ""
    return f"{count} view{'s' if count != 1 else ''} {verb}"


def change_message(
    name: str,
    old: dict | None,
    new: dict,
    reason: str,
    old_meta: dict | None = None,
    new_meta: dict | None = None,
) -> str:
    """The one line that will stand in the history for this change.

    People read these while looking for something they lost, so they have
    to be exactly true. A message that claims more than happened is worse
    than a vague one - "changed outside Home Assistant" shown to somebody
    whose dashboard nobody touched is an accusation, not a note.

    `old` is None when nothing was recorded yet. `reason` is "save" for a
    change Home Assistant announced, and anything else for one found by
    comparison, where nobody can say what caused it.
    """
    if old is None:
        return f"{name}: first recorded state"
    if old == new:
        # Not the cards, then. Something *about* the dashboard changed -
        # its title, its icon - or nothing did and only metadata was
        # recorded for the first time. Either way: no outside change.
        return f"{name}: {_meta_detail(old_meta, new_meta)}"
    if reason != "save":
        # Changed while nobody was listening: a restored backup, a
        # hand-edited storage file, another tool. Recording that as an
        # ordinary save would hide it.
        return f"{name}: changed outside Home Assistant"
    counts = summarize(old, new)
    parts = [
        _views(counts.views_removed, "removed"),
        _views(counts.views_added, "added"),
        f"{counts.removed} removed" if counts.removed else "",
        f"{counts.added} added" if counts.added else "",
        f"{counts.edited} edited" if counts.edited else "",
        f"{counts.moved} moved" if counts.moved else "",
    ]
    return f"{name}: " + (", ".join(part for part in parts if part) or "no card changes")
