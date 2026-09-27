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

import copy
import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field, replace
from typing import Any, NamedTuple
from .model import (
    Entry,
    Explanation,
    Matching,
    RemovedItem,
    SectionMatching,
    SectionPair,
    SectionSlot,
    SettingChange,
    Slot,
    Summary,
    UndoPlan,
    UndoStep,
    ViewChanges,
    _ABSENT,
    _LABEL_LIMIT,
    _SectionAnchor,
    _by_position,
    _describe,
    _first_entity,
    _first_line,
    _inner_card,
    _own,
    _place,
    _section_list,
    _section_title,
    _shorten,
    _translated,
    _view_name,
    _views_by_key,
    _weak_key,
    badge_containers,
    card_containers,
    fingerprint,
    same_config,
)


def _slots(config: dict, keys: set, containers=card_containers) -> list[Slot]:
    """Every item of the named views, in the order they are written."""
    found: list[Slot] = []
    for view_index, (key, view) in enumerate(_views_by_key(config)):
        if key not in keys:
            continue
        for location, cards in containers(view):
            for index, card in enumerate(cards):
                found.append(Slot(key, view_index, view, location, index, card, fingerprint(card)))
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


def _unpaired(slot: Slot, translate: dict) -> bool:
    """Whether a slot sits in a section the pairing left unexplained."""
    location = slot.location
    return (
        len(location) == 3
        and location[0] == "sections"
        and (slot.view_key, location[1]) not in translate
    )


def match_cards(old: dict, new: dict, containers=card_containers) -> Matching:
    """Pair the cards of two states of one dashboard.

    `containers` says which lists are paired: cards by default, a view's
    badges for `match_badges`. Never both at once - a badge and a card
    can be byte-identical (`type: entity` is both), and one run over
    both would read a deleted card as "moved into the badges".

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

    Sections first (GitHub #31). A section carries no id either, and a
    card's place names its section by index - so a section moved whole
    used to move every card on it. The sections are paired first, outside
    in, and a card's old place is followed to where its section went
    before the passes compare places. Badges never sit in sections and
    skip this.
    """
    if containers is not card_containers:
        return _match_slots(old, new, containers, {})
    pairs, rest_old, rest_new = _pair_sections(old, new)
    translate = {(pair.old.view_key, pair.old.index): pair.new.index for pair in pairs}
    matching = _match_slots(old, new, containers, translate)
    return replace(
        matching,
        sections=_settle_sections(old, new, pairs, rest_old, rest_new, matching),
    )


def match_sections(old: dict, new: dict) -> SectionMatching:
    """What happened to a dashboard's sections between two states (spec O, section 1).

    The section half of `match_cards`, which needs the cards to prove a
    section went or came whole - so it is that call, read for its
    sections.
    """
    return match_cards(old, new).sections


def _match_slots(old: dict, new: dict, containers, translate: dict) -> Matching:
    """The four card passes of `match_cards`, old places followed through `translate`."""
    old_keys = {key for key, _ in _views_by_key(old)}
    new_keys = {key for key, _ in _views_by_key(new)}
    common = old_keys & new_keys
    old_open = _slots(old, common, containers)
    new_open = _slots(new, common, containers)

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
        mark = new_slot.mark
        here.setdefault((_place(new_slot), mark), []).append(j)
        anywhere.setdefault(mark, []).append(j)

    # Cards of paired sections, and cards outside sections, claim their
    # places first. A card of a section nothing paired keeps its real
    # index but comes last: when a section before it went, that index
    # now names the section that moved up, and its own identical card
    # must not be taken from it (GitHub #31).
    order = sorted(range(len(old_open)), key=lambda i: _unpaired(old_open[i], translate))
    for pairs, buckets, at_place in (
        (in_place, here, True),
        (displaced, anywhere, False),
    ):
        for i in order:
            old_slot = old_open[i]
            if i in taken_old:
                continue
            mark = old_slot.mark
            waiting = buckets.get((_translated(old_slot, translate), mark) if at_place else mark, ())
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
            if j in taken_new or _place(new_slot) != _translated(old_slot, translate):
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
        translate=translate,
    )


def match_badges(old: dict, new: dict) -> Matching:
    """Pair the badges of two states - the same four passes, in their own world."""
    return match_cards(old, new, containers=badge_containers)



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
        grouped.setdefault(_place(new_open[pair[1]]), []).append(pair)

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


def _pair_view_sections(
    key: Any, old_index: int, old_view: dict, new_index: int, new_view: dict
) -> tuple[list[SectionPair], list[SectionSlot], list[SectionSlot]]:
    """Pair one view's sections across two states, outside in.

    The shape of `match_cards`: identical at the same index, identical
    anywhere else in the view, then - at the same index only - the same
    cards under other settings, and the same settings over other cards.
    The last is the ordinary save, a card edited inside a section. What
    is left is returned as it is; whether it went or came whole is for
    `_settle_sections` to prove, with the cards.
    """
    olds = [SectionSlot(key, old_index, i, s) for i, s in enumerate(_section_list(old_view))]
    news = [SectionSlot(key, new_index, j, s) for j, s in enumerate(_section_list(new_view))]
    old_marks = [fingerprint(slot.section) for slot in olds]
    new_marks = [fingerprint(slot.section) for slot in news]
    taken_old: set[int] = set()
    taken_new: set[int] = set()
    pairs: list[SectionPair] = []

    def claim(i: int, j: int, how: str) -> None:
        taken_old.add(i)
        taken_new.add(j)
        pairs.append(SectionPair(olds[i], news[j], how))

    for i in range(min(len(olds), len(news))):
        if old_marks[i] == new_marks[i]:
            claim(i, i, "same")
    # Old sections in their order, each taking the first free new one:
    # the same pair of states always produces the same pairing.
    for i in range(len(olds)):
        if i in taken_old:
            continue
        j = next(
            (j for j in range(len(news)) if j not in taken_new and new_marks[j] == old_marks[i]),
            None,
        )
        if j is not None:
            claim(i, j, "found")
    for i in range(min(len(olds), len(news))):
        if i in taken_old or i in taken_new:
            continue
        old, new = olds[i].section, news[i].section
        if not isinstance(old, dict) or not isinstance(new, dict):
            continue
        same_cards = fingerprint(old.get("cards")) == fingerprint(new.get("cards"))
        same_own = fingerprint(_own(old)) == fingerprint(_own(new))
        if same_cards and not same_own:
            claim(i, i, "settings")
        elif same_own and not same_cards:
            claim(i, i, "cards")
    return (
        pairs,
        [slot for i, slot in enumerate(olds) if i not in taken_old],
        [slot for j, slot in enumerate(news) if j not in taken_new],
    )


def _pair_sections(
    old: dict, new: dict
) -> tuple[list[SectionPair], list[SectionSlot], list[SectionSlot]]:
    """`_pair_view_sections` for every view both states have.

    A converted view (#32) is left out: its layout changed, and the empty
    section Home Assistant adds with a conversion is a side effect of that
    event, not an event of its own.
    """
    pairs: list[SectionPair] = []
    rest_old: list[SectionSlot] = []
    rest_new: list[SectionSlot] = []
    new_views = {key: (index, view) for index, (key, view) in enumerate(_views_by_key(new))}
    for old_index, (key, old_view) in enumerate(_views_by_key(old)):
        if key not in new_views:
            continue
        new_index, new_view = new_views[key]
        if _view_type(old_view) != _view_type(new_view):
            continue
        found, gone, came = _pair_view_sections(key, old_index, old_view, new_index, new_view)
        pairs += found
        rest_old += gone
        rest_new += came
    return pairs, rest_old, rest_new


def _moved(pairs: list[SectionPair]) -> list[SectionPair]:
    """The pairs of one view outside the longest run that kept its order.

    The run is the longest increasing subsequence of the new indices, read
    in old order; of several equally long, the one whose old indices come
    first, element by element. A swap is then one move, the first of five
    sent to the end is one move, and a section that only closed a gap
    after a deletion is none.
    """
    ordered = sorted(pairs, key=lambda pair: pair.old.index)
    longest = [1] * len(ordered)
    for i in range(len(ordered) - 1, -1, -1):
        for k in range(i + 1, len(ordered)):
            if ordered[k].new.index > ordered[i].new.index:
                longest[i] = max(longest[i], longest[k] + 1)
    kept: set[int] = set()
    need = max(longest, default=0)
    last = -1
    for i, pair in enumerate(ordered):
        if need and longest[i] == need and pair.new.index > last:
            kept.add(i)
            last = pair.new.index
            need -= 1
    return [pair for i, pair in enumerate(ordered) if i not in kept]


def _count_places(slots: list[Slot]) -> dict:
    """How many of these slots sit in each card list."""
    counts: dict = {}
    for slot in slots:
        place = (slot.view_key, slot.location)
        counts[place] = counts.get(place, 0) + 1
    return counts


def _whole(slot: SectionSlot, counted: dict, empty_counts: bool) -> bool:
    """Whether every card of a section is among the counted ones."""
    cards = slot.section.get("cards") if isinstance(slot.section, dict) else None
    if not isinstance(cards, list):
        return False
    if not cards:
        return empty_counts
    return counted.get((slot.view_key, ("sections", slot.index, "cards")), 0) == len(cards)


def _settle_sections(
    old: dict,
    new: dict,
    pairs: list[SectionPair],
    rest_old: list[SectionSlot],
    rest_new: list[SectionSlot],
    matching: Matching,
) -> SectionMatching:
    """Moves from the pairs, and whole sections from what is left, proven by the cards.

    A left-over section went whole only where its view lost exactly one
    section and every card of it is among those the card matching gave up
    on - the proof put-back has used since package 3 of vorhaben F. An
    empty one never counts as gone: it has nothing to prove itself with,
    and every empty section of a shrunken view would look equally lost.
    Arriving is the same question the other way round. There an empty
    section counts: it is the single one left over in a view that grew by
    exactly one, and Home Assistant's own "add section" makes one.
    """
    old_counts = {key: len(_section_list(view)) for key, view in _views_by_key(old)}
    new_counts = {key: len(_section_list(view)) for key, view in _views_by_key(new)}
    gone = _count_places(matching.removed)
    came = _count_places(matching.added)
    removed: list[SectionSlot] = []
    added: list[SectionSlot] = []
    for key in sorted({slot.view_key for slot in rest_old}, key=str):
        if old_counts[key] - new_counts[key] == 1:
            found = [s for s in rest_old if s.view_key == key and _whole(s, gone, False)]
            if len(found) == 1:
                removed.append(found[0])
    for key in sorted({slot.view_key for slot in rest_new}, key=str):
        if new_counts[key] - old_counts[key] == 1:
            found = [s for s in rest_new if s.view_key == key and _whole(s, came, True)]
            if len(found) == 1:
                added.append(found[0])
    moved: list[SectionPair] = []
    for key in sorted({pair.old.view_key for pair in pairs}, key=str):
        moved += _moved([pair for pair in pairs if pair.old.view_key == key])
    return SectionMatching(
        pairs=tuple(pairs),
        moved=tuple(moved),
        removed=tuple(removed),
        added=tuple(added),
        rest_old=tuple(slot for slot in rest_old if slot not in removed),
        rest_new=tuple(slot for slot in rest_new if slot not in added),
    )


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

    Positions are only ever compared up to the shorter state's own
    length (GitHub #33): a view appended at the end raises that length
    on one side alone and cannot have moved anything sitting before it,
    so it is dropped before the comparison rather than read as every
    earlier position having shifted. Deliberately strict on everything
    up to there, though: a pathless view added or removed *within* that
    common length still taints every position at or after it - the
    identity chain of package 2 is what would tell the difference, and
    until it exists a refusal is the answer decision 4 asks for.

    One view in both states is the other position that cannot have
    shifted: there is no neighbour to have moved in front of it, so it
    needs neither path nor title to be recognised (GitHub #33).
    """
    if len(one.get("views") or []) == len(other.get("views") or []) == 1:
        return False
    length = min(len(one.get("views") or []), len(other.get("views") or []))
    here, there = _by_position(one, length), _by_position(other, length)
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


def _paths_collide(config: dict) -> bool:
    """Whether two views of one state claim the same URL path.

    A path is the identity everything above rests on, and this is the one
    way it stops being one. Home Assistant's backend does not enforce
    uniqueness - saved through the API, `['x', 'x']` goes in without
    complaint - and `_views_by_key` is then read into a dict, which keeps
    only the last of the two. The first view is invisible to every
    comparison from that point on.

    Readable rather than worked out: no matching, no similarity, no
    guessing. Which is why this can be answered today, while the question
    "is the view under this path still the same view" cannot.
    """
    paths = [
        view.get("path")
        for view in config.get("views") or []
        if isinstance(view, dict) and view.get("path")
    ]
    return len(paths) != len(set(paths))


def _section_marks(view: dict) -> list:
    """Each section's own settings, in order - all the identity there is.

    Everything but `cards`: a section swap that leaves `cards` as the
    only difference is exactly what the rest of this module already
    matches card by card. `title` alone missed a swap of two sections
    that share it (commonly both unset - Home Assistant names a section
    with a heading card, not `title`) but differ in a setting such as
    `column_span`. GitHub #31: the swap read as an exact card move, and
    the settings stayed pinned to their index, writing a state that
    never existed. Compared through `_same_marks`, strictly, since
    vorhaben O.
    """
    return [
        {key: value for key, value in section.items() if key != "cards"}
        if isinstance(section, dict)
        else None
        for section in view.get("sections") or []
    ]


def _same_marks(one: dict, other: dict) -> bool:
    """Whether two views' sections agree on every setting, strictly.

    Through `fingerprint`, not `==`: `column_span: 1` and `column_span:
    true` are two states, which `==` calls equal (GitHub #28).
    """
    return fingerprint(_section_marks(one)) == fingerprint(_section_marks(other))


def _section_drift(new_views: dict, now_views: dict) -> set:
    """The views whose sections moved since the change - their inserts park.

    The change left the sections of these views as they were, or undoes
    its own section changes in one step of its own (`_plan_sections`);
    either way they have moved since. A card can still be taken out
    exactly - it is found by its fingerprint - but where one goes back in
    cannot be proven any more, so an insertion there is parked in the
    view's own `cards:` (decision 26, GitHub #30).

    Per view, not per dashboard: a section moved in one view says nothing
    about an index in another.
    """
    return {
        key
        for key in set(new_views) & set(now_views)
        if not _same_marks(now_views[key], new_views[key])
    }


def _section_anchor(
    view: dict, location: tuple, index: int, left: set, departed: set = frozenset()
) -> _SectionAnchor | None:
    """How to recognise the section a card sat in, or None outside one.

    What the section was, not what it was called: how many sections the
    view had, the section's own settings (everything but `cards`, like
    `_section_marks`), and the cards that should still stand in it - the
    old ones minus those in `left`, which disappeared or moved elsewhere
    and so owe the section nothing. Titles alone were a check against
    nothing - 0 of 101 sections carry one - and let a swapped section
    take a stranger's card (GitHub #30). Failing this parks the card now
    rather than refusing it, so being strict costs a hint, not a refusal.

    `before` counts the survivors that stood ahead of the card, so it can
    go back right after the last of them rather than to an old index that
    cards added since may have moved.

    `departed` are the neighbours that left for another list of the same
    view: `restore._anchored_index` parks where one of them now stands in
    a section alike this one, because a swap and a drag across are then
    the same bytes (spec O, section 5).
    """
    if len(location) < 2 or location[0] != "sections":
        return None
    sections = view.get("sections") or []
    at = location[1]
    settings: dict | None = None
    survivors: list = []
    away: list = []
    before = 0
    if isinstance(at, int) and 0 <= at < len(sections):
        section = sections[at]
        if isinstance(section, dict):
            settings = _section_marks(view)[at]
            for position, card in enumerate(section.get("cards") or []):
                if (location, position) in left:
                    if (location, position) in departed:
                        away.append(card)
                    continue
                survivors.append(card)
                if position < index:
                    before += 1
    return _SectionAnchor(len(sections), settings, tuple(survivors), before, tuple(away))


def _view_type(view: dict) -> str:
    """A view's own layout, defaulting the way Home Assistant does.

    An absent `type` is not "no layout" - it is Home Assistant's own
    default, the classic `masonry` view (see How It Works, §2).
    """
    return view.get("type") or "masonry"


def _view_type_changed(one: dict, other: dict) -> bool:
    """Whether a view kept its identity but changed layout.

    Converting a view - masonry to sections, most commonly - adds an
    empty grid section, which is exactly what `_section_drift` reacts to:
    the section list went from empty to one entry. Checked first, so the
    refusal names the conversion instead of blaming "the sections" for a
    side effect of it. GitHub #32.
    """
    here, there = dict(_views_by_key(one)), dict(_views_by_key(other))
    return any(
        _view_type(here[key]) != _view_type(there[key]) for key in set(here) & set(there)
    )

# Everything on a view that is not a named setting: the card world, the
# badges (a list without names, vorhaben N), the view's own key, and its
# layout (a conversion, #32 - refused, never written back as a setting).
_NOT_VIEW_SETTINGS = frozenset({"cards", "sections", "badges", "path", "type"})


def _same(one: Any, other: Any) -> bool:
    """Equal as settings. Not `==`: that says 1 is True and 0 is False."""
    if one is _ABSENT or other is _ABSENT:
        return one is other
    return fingerprint(one) == fingerprint(other)


def _setting_leaves(view_key: Any, old: Any, new: Any, path: tuple, out: list) -> None:
    """Descend where both sides are dicts; everywhere else is a leaf."""
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new), key=str):
            _setting_leaves(
                view_key, old.get(key, _ABSENT), new.get(key, _ABSENT), path + (key,), out
            )
        return
    if not _same(old, new):
        out.append(SettingChange(view_key, path, old, new))


def setting_changes(old: dict, new: dict) -> list[SettingChange]:
    """Every named setting that differs, dashboard first, then per view.

    Only views both states have under the same key: a view that only one
    of them has is one line of its own, and its settings go with it.
    """
    out: list[SettingChange] = []
    _setting_leaves(
        None,
        {key: value for key, value in old.items() if key != "views"},
        {key: value for key, value in new.items() if key != "views"},
        (),
        out,
    )
    new_views = dict(_views_by_key(new))
    for key, old_view in _views_by_key(old):
        if key not in new_views:
            continue
        _setting_leaves(
            key,
            {k: v for k, v in old_view.items() if k not in _NOT_VIEW_SETTINGS},
            {k: v for k, v in new_views[key].items() if k not in _NOT_VIEW_SETTINGS},
            (),
            out,
        )
    return out


def _setting_at(container: dict, path: tuple) -> tuple[Any, str | None]:
    """The value at `path`, or `_ABSENT`; and the block that vanished, if one did.

    Every ancestor of a leaf was a dict in both states of the change -
    `_setting_leaves` only descends through dicts on both sides. So one
    that is missing or no dict today was removed since, and writing the
    leaf would rebuild half a block nobody asked for.
    """
    for depth, key in enumerate(path[:-1]):
        container = container.get(key, _ABSENT) if isinstance(container, dict) else _ABSENT
        if not isinstance(container, dict):
            return _ABSENT, ".".join(str(k) for k in path[: depth + 1])
    return container.get(path[-1], _ABSENT), None


_POSITION_REFUSAL = (
    "a view without a URL path sits somewhere else now, so an exact undo "
    "cannot tell which view is which"
)

_SECTIONS_AND_CARDS_REFUSAL = (
    "this change moved sections of a view and also changed single cards "
    "in it, so an exact undo cannot put both back at once"
)

_VIEW_TYPE_REFUSAL = (
    "a view's own layout was converted since, and undoing a conversion "
    "spans more than this one change - a version or a whole-state restore "
    "covers it"
)

_DUPLICATE_PATH_REFUSAL = (
    "two views of this dashboard share one URL path, so a path no longer "
    "tells them apart and an exact undo cannot say which one it means"
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


def _present(config: dict, containers=card_containers) -> list[Slot]:
    """Every item of a state, with the place it sits in."""
    return _slots(config, {key for key, _ in _views_by_key(config)}, containers)


def _group_by_mark(slots: list[Slot]) -> dict[str, list[Slot]]:
    """Slots keyed by their fingerprint, in the order found."""
    groups: dict[str, list[Slot]] = {}
    for slot in slots:
        groups.setdefault(slot.mark, []).append(slot)
    return groups


def _in_view(slots: list[Slot], view_key: Any) -> list[Slot]:
    """Only the slots that belong to one view."""
    return [slot for slot in slots if slot.view_key == view_key]


def _step(
    slot: Slot,
    action: str,
    expect: Any,
    payload: Any,
    label: str,
    kind: str = "card",
    location: tuple | None = None,
    parked: bool = False,
) -> UndoStep:
    """A card or badge step at the place `slot` names.

    `location` overrides `slot`'s own for a parked insertion (decision
    26), which goes to the view's `cards:` instead of where it sat.
    """
    return UndoStep(
        action=action,
        kind=kind,
        view_path=slot.view.get("path"),
        view_index=slot.view_index,
        location=slot.location if location is None else location,
        index=slot.index,
        expect=expect,
        payload=payload,
        label=label,
        parked=parked,
    )


def _plan_sections(
    key: Any,
    before_view: dict,
    after_view: dict,
    current_view: dict | None,
    current_index: int,
    change: SectionMatching,
) -> UndoStep | str | None:
    """The one step that puts a view's sections back, why it cannot, or None.

    Decision 15 for sections (GitHub #31). A section has no address but
    its index, and several moved at once shift each other's - so nothing
    here is an index: the whole row is rebuilt in `before`'s order and
    written in one step. `before`'s order says where each goes; today's
    state is where each one's content comes from. What makes that exact
    is asked first, all of it or nothing.
    """
    name = _view_name(after_view, key)
    mine = [pair for pair in change.pairs if pair.old.view_key == key]
    moved = [pair for pair in change.moved if pair.old.view_key == key]
    reset = [pair for pair in mine if pair.how == "settings"]
    added = [slot for slot in change.added if slot.view_key == key]
    removed = [slot for slot in change.removed if slot.view_key == key]
    if any(slot.view_key == key for slot in (*change.rest_old, *change.rest_new)):
        return (
            f'the sections of the view "{name}" changed in a way this undo '
            f"cannot account for, so it refuses rather than guess"
        )
    if not (moved or reset or added or removed):
        return None
    if current_view is None:
        return f'the view "{name}" is no longer on the dashboard, so its sections cannot be taken back'
    if not isinstance(before_view.get("sections"), list) or not isinstance(
        current_view.get("sections"), list
    ):
        return (
            f'the sections of the view "{name}" are not a plain list in every '
            f"state, so an exact undo cannot write them back"
        )

    # Since the change: nothing arrived, went or moved among the sections,
    # so each stands at the index it had after the change. One of them may
    # have been edited since - its identity is then forced, every other
    # one standing byte for byte in its place. Two edited since could as
    # well have swapped places too, and index is no proof of which is
    # which.
    since, gone, came = _pair_view_sections(key, 0, after_view, 0, current_view)
    if gone or came or _moved(since):
        return (
            f'the other sections of the view "{name}" were rearranged since, '
            f"so there is no telling where these go back"
        )
    if sum(1 for pair in since if pair.how in ("settings", "cards")) > 1:
        return (
            f'more than one section of the view "{name}" was changed since, '
            f"so which is which can no longer be proven"
        )

    then_sections = _section_list(after_view)
    now_sections = _section_list(current_view)
    then_marks = [fingerprint(section) for section in then_sections]
    now_marks = [fingerprint(section) for section in now_sections]
    for index in sorted({*(slot.index for slot in added), *(pair.new.index for pair in (*moved, *reset))}):
        title = _section_title(then_sections[index], index)
        mark = then_marks[index]
        if now_marks[index] != mark:
            return (
                f"the {title} was changed again after this, so there is no "
                f"exact version left to take back"
            )
        alike = max(now_marks.count(mark), then_marks.count(mark))
        if alike > 1:
            return (
                f"{alike} sections now look exactly like {title}, so an "
                f"exact undo cannot tell them apart"
            )

    by_old = {pair.old.index: pair for pair in mine}
    target = []
    for index, section in enumerate(_section_list(before_view)):
        pair = by_old.get(index)
        if pair is None or pair.how == "settings":
            # Gone whole, or only its own settings changed - and its cards
            # are today's, proven above.
            target.append(copy.deepcopy(section))
        else:
            target.append(copy.deepcopy(now_sections[pair.new.index]))
    return UndoStep(
        action="set",
        kind="sections_list",
        view_path=current_view.get("path"),
        view_index=current_index,
        location=(),
        index=0,
        expect=copy.deepcopy(now_sections),
        payload=target,
        label=f'the sections of the view "{name}"',
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
    badge_matching = match_badges(before, after)
    old_views = dict(_views_by_key(before))
    new_views = dict(_views_by_key(after))
    now_views = dict(_views_by_key(current))
    view_work = set(old_views) ^ set(new_views)
    # A conversion (masonry to sections, typically) is a real alteration
    # even though it touches no card: Home Assistant leaves every
    # existing card exactly where it was, in the view's own `cards:`
    # list, and only adds an empty grid section. Left out of this check,
    # a save that did nothing but convert the view had nothing here to
    # register, and fell through to "did not alter any cards" - true of
    # the cards, false of the view.
    #
    # A section moved or re-set is a real alteration too, with no card event
    # of its own since its cards follow it (GitHub #31).
    pairs = ((before, after), (before, current), (after, current))
    type_changed = any(_view_type_changed(one, other) for one, other in pairs)
    settings = setting_changes(before, after)
    if not (
        matching.removed
        or matching.added
        or matching.edited
        or matching.moved
        or badge_matching.removed
        or badge_matching.added
        or badge_matching.edited
        or badge_matching.moved
        or view_work
        or type_changed
        or settings
        or matching.sections.views()
    ):
        return UndoPlan(blocked="this change did not alter any cards")

    # Before any pair is compared: a path that names two views is not an
    # identity, and everything below reads views by their path.
    if any(_paths_collide(state) for state in (before, after, current)):
        return UndoPlan(blocked=_DUPLICATE_PATH_REFUSAL)

    # Every state this plan reads from or writes to has to agree on what
    # a position means: `before` and `after` decide what the change was,
    # `current` is where the steps land.
    if any(_positions_lie(one, other) for one, other in pairs):
        return UndoPlan(blocked=_POSITION_REFUSAL)
    # Checked before `_section_drift`: a conversion changes the section
    # list too, and would otherwise be blamed on "the sections" instead
    # of on itself.
    if type_changed:
        return UndoPlan(blocked=_VIEW_TYPE_REFUSAL)
    shifted = _section_drift(new_views, now_views)
    # A view whose sections the change rearranged is put back in one step
    # of its own (GitHub #31) - or refused, and then before anything else.
    now_index = {key: index for index, (key, _) in enumerate(_views_by_key(current))}
    section_steps: list[UndoStep] = []
    for key in sorted(matching.sections.views(), key=str):
        planned = _plan_sections(
            key,
            old_views[key],
            new_views[key],
            now_views.get(key),
            now_index.get(key, -1),
            matching.sections,
        )
        if isinstance(planned, str):
            return UndoPlan(blocked=planned)
        if planned is not None:
            section_steps.append(planned)

    setting_steps: list[UndoStep] = []
    for change in settings:
        label = ".".join(str(key) for key in change.path)
        if change.view_key is None:
            container = current
        else:
            container = now_views.get(change.view_key)
            if container is None:
                name = _view_name(old_views[change.view_key], change.view_key)
                return UndoPlan(
                    blocked=f'the view "{name}" is no longer on the dashboard, '
                    f'so its setting "{label}" cannot be taken back'
                )
        standing, vanished = _setting_at(container, change.path)
        if vanished is not None:
            return UndoPlan(
                blocked=f'the setting "{label}" no longer has the "{vanished}" '
                f"block it belonged to"
            )
        if _same(standing, change.old):
            # Already back, the way a deleted card that returned is.
            continue
        if not _same(standing, change.new):
            return UndoPlan(blocked=f'the setting "{label}" was changed again after this')
        key = change.view_key
        setting_steps.append(
            UndoStep(
                action="unset" if change.old is _ABSENT else "set",
                kind="dashboard_setting" if key is None else "view_setting",
                view_path=None if key is None else container.get("path"),
                view_index=key[1] if isinstance(key, tuple) else -1,
                location=change.path,
                index=0,
                expect=None if change.new is _ABSENT else change.new,
                payload=None if change.old is _ABSENT else change.old,
                label=f'setting "{label}"',
                expect_absent=change.new is _ABSENT,
            )
        )

    by_mark = _group_by_mark(_present(current))
    card_then = _group_by_mark(_present(after))

    # Counted in two stages, the same way `sole_badge` below counts
    # badges (GitHub #36): "exactly one today" is not proof by itself -
    # an untouched copy that stood there before the change is not the
    # one the change produced. Asked first dashboard-wide, then, failing
    # that, in the card's own view.
    def sole(slot: Slot, label: str) -> tuple[Slot | None, str | None]:
        found, left = by_mark.get(slot.mark, []), card_then.get(slot.mark, [])
        if len(found) == 1 and len(left) == 1:
            return found[0], None
        view_key = slot.view_key
        mine = _in_view(found, view_key)
        mine_then = _in_view(left, view_key)
        if len(mine) == 1 and len(mine_then) == 1:
            return mine[0], None
        if len(mine) < len(mine_then):
            return None, (
                f"{label} was changed again after this, so there is no "
                f"exact version left to put back"
            )
        return None, (
            f"{len(mine)} cards now look exactly like {label}, so an "
            f"exact undo cannot tell them apart"
        )

    steps: list[UndoStep] = []
    steps.extend(setting_steps)
    # The step's own `view_index` and `index` already carry `old_slot`'s -
    # only its original `location` does not, overwritten below to
    # `("cards",)` for `apply_undo` to find and to show, so that is the
    # one piece this still has to keep beside the step for sorting.
    parked: list[tuple[tuple, UndoStep]] = []

    def put_back(old_slot: Slot, label: str) -> None:
        """Insert where the card came from, or park it in "Imported cards"."""
        if old_slot.view_key not in shifted or old_slot.location[:1] != ("sections",):
            steps.append(_step(old_slot, "insert", None, old_slot.card, label))
            return
        # A pathless view is found by its position here, which
        # `_positions_lie` above has already vouched for - the same proof
        # an ordinary insert into it rests on.
        parked.append(
            (
                old_slot.location,
                _step(
                    old_slot,
                    "insert",
                    None,
                    old_slot.card,
                    # The card that is parked, not the one taken out: the
                    # dialog lists what somebody has to go and place.
                    _describe(old_slot.card),
                    location=("cards",),
                    parked=True,
                ),
            )
        )

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
        here, why = sole(new_slot, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label))
        put_back(old_slot, label)

    for new_slot in matching.loose_added():
        label = _describe(new_slot.card)
        here, why = sole(new_slot, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label))

    # Counted, not looked up, and only in the card's own view (GitHub
    # #35): an untouched copy on another view - there all along or added
    # since - is not this one coming back. A dashboard-wide look would
    # reopen the same door the bug used: a copy someone else placed
    # elsewhere after the change would count as this card's return.
    # Mirrors the badge rule below (Vorhaben N) - `deleted` is how many
    # alike the change took from that view, `card_came_back` how many
    # more stand there now than the change left.
    removed_card_marks = [(old_slot, old_slot.mark) for old_slot in matching.loose_removed()]
    deleted_cards: dict[tuple[str, Any], int] = {}
    for old_slot, mark in removed_card_marks:
        place = (mark, old_slot.view_key)
        deleted_cards[place] = deleted_cards.get(place, 0) + 1

    def card_came_back(mark: str, view_key: Any) -> int:
        return len(_in_view(by_mark.get(mark, []), view_key)) - len(
            _in_view(card_then.get(mark, []), view_key)
        )

    for old_slot, mark in removed_card_marks:
        label = _describe(old_slot.card)
        back = card_came_back(mark, old_slot.view_key)
        if back >= deleted_cards[(mark, old_slot.view_key)]:
            # Already back by some other route. Inserting would make a
            # second copy, and this part of the change is undone either
            # way.
            continue
        if back > 0:
            # Some of several alike are back: which places they took is
            # not in the states, and picking one would be a guess.
            return UndoPlan(
                blocked=(
                    f"only some of the copies of {label} this change "
                    f"deleted are back, so an exact undo cannot tell "
                    f"which are missing"
                )
            )
        put_back(old_slot, label)

    # In the order of the places they came from - view, section, card -
    # whichever of the three tables in decision 15 produced them.
    def parked_order(item: tuple[tuple, UndoStep]) -> tuple:
        location, step = item
        return (step.view_index, location, step.index)

    steps.extend(step for _location, step in sorted(parked, key=parked_order))

    # Badges (GitHub #29): the same table as cards, counted in their own
    # world. The same badge on several views is ordinary - 6 of 23 on the
    # installation this was built against - so "exactly once" is asked in
    # two stages: on the whole dashboard, and failing that, in the view
    # the change left it in. Both answer decision 15's question; the
    # second only asks it where the badge was left. And both compare
    # today with what the change left: one standing today, out of several
    # the change left, may be the one that was there before it.
    badge_now = _group_by_mark(_present(current, badge_containers))
    badge_then = _group_by_mark(_present(after, badge_containers))

    def sole_badge(slot: Slot, label: str) -> tuple[Slot | None, str | None]:
        found, left = badge_now.get(slot.mark, []), badge_then.get(slot.mark, [])
        if len(found) == 1 and len(left) == 1:
            return found[0], None
        view_key = slot.view_key
        mine = _in_view(found, view_key)
        mine_then = _in_view(left, view_key)
        if len(mine) == 1 and len(mine_then) == 1:
            return mine[0], None
        if len(mine) < len(mine_then):
            return None, (
                f"{label} was changed again after this, so there is no "
                f"exact version left to put back"
            )
        # Here `mine` holds at least two: the view has as many as the
        # change left, or more, and not exactly one of each.
        return None, (
            f"{len(mine)} badges now look exactly like {label}, "
            f"so an exact undo cannot tell them apart"
        )

    # Counted, not looked up, and only in the badge's own view: a copy on
    # another view - there all along or added since - is not this badge
    # coming back. `came_back` is how many more stand there now than the
    # change left; `deleted` how many alike it took from that view. Each
    # removed slot's mark is kept beside it - `deleted` and the loop
    # below both need it, and it is already sitting on the slot.
    removed_marks = [(old_slot, old_slot.mark) for old_slot in badge_matching.removed]
    deleted: dict[tuple[str, Any], int] = {}
    for old_slot, mark in removed_marks:
        place = (mark, old_slot.view_key)
        deleted[place] = deleted.get(place, 0) + 1

    def came_back(mark: str, view_key: Any) -> int:
        return len(_in_view(badge_now.get(mark, []), view_key)) - len(
            _in_view(badge_then.get(mark, []), view_key)
        )

    def badge_label(badge: Any) -> str:
        return f"the badge {_describe(badge, fallback='badge')}"

    for old_slot, new_slot in (*badge_matching.edited, *badge_matching.moved):
        label = badge_label(new_slot.card)
        here, why = sole_badge(new_slot, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))

    for new_slot in badge_matching.added:
        label = badge_label(new_slot.card)
        here, why = sole_badge(new_slot, label)
        if here is None:
            return UndoPlan(blocked=why)
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))

    for old_slot, mark in removed_marks:
        label = badge_label(old_slot.card)
        back = came_back(mark, old_slot.view_key)
        if back >= deleted[(mark, old_slot.view_key)]:
            continue
        if back > 0:
            # Some of several alike are back: which places they took is
            # not in the states, and picking one would be a guess.
            return UndoPlan(
                blocked=(
                    f"only some of the copies of {label} this change deleted "
                    f"are back, so an exact undo cannot tell which are missing"
                )
            )
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))

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

    # One step writes a view's whole row of sections; a card step in the
    # same view would write into a row that step replaces.
    rewritten = {step.view_path or ("#", step.view_index) for step in section_steps}
    if any(
        step.kind == "card" and (step.view_path or ("#", step.view_index)) in rewritten
        for step in steps
    ):
        return UndoPlan(blocked=_SECTIONS_AND_CARDS_REFUSAL)
    steps.extend(section_steps)
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

    badges = match_badges(old, new)

    section_settings = sum(
        len(_section_setting_changes(pair))
        for pair in matching.sections.pairs
        if pair.how == "settings"
    )

    # One entry per moved card already, so a swap contributes two.
    # Multiplying would count each of them twice.
    return Summary(
        added=len(matching.loose_added()),
        removed=len(matching.loose_removed()),
        edited=len(matching.edited),
        moved=len(matching.moved),
        views_added=len(new_keys - old_keys),
        views_removed=len(old_keys - new_keys),
        settings=len(setting_changes(old, new)) + section_settings,
        badges=len(badges.removed) + len(badges.added) + len(badges.edited) + len(badges.moved),
        sections_moved=len(matching.sections.moved),
        sections_added=len(matching.sections.added),
        sections_removed=len(matching.sections.removed),
    )


# Card labels already carry their type ("tile: light.b"), so they need no
# quotes. A view label is a bare name and does.
_PAST = {
    ("section", "removed"): "{label} was removed",
    ("section", "added"): "{label} was added",
    ("section", "moved"): "{label} was moved",
    ("badge", "removed"): "the badge {label} was deleted",
    ("badge", "added"): "the badge {label} was added",
    ("badge", "edited"): "the badge {label} was changed",
    ("badge", "moved"): "the badge {label} was moved",
    ("badge", "moved_to"): "the badge {label} was moved to {where}",
    ("setting", "added"): 'the setting "{label}" was set to {new}',
    ("setting", "added_bare"): 'the setting "{label}" was set',
    ("setting", "removed"): 'the setting "{label}" was removed',
    ("setting", "edited"): 'the setting "{label}" was changed from {old} to {new}',
    ("setting", "edited_bare"): 'the setting "{label}" was changed',
    ("card", "removed"): "{label} was deleted",
    ("card", "added"): "{label} was added",
    ("card", "edited"): "{label} was changed",
    ("card", "moved"): "{label} was moved",
    ("card", "moved_to"): "{label} was moved to {where}",
    ("view", "removed"): 'the whole view "{label}" was deleted',
    ("view", "added"): 'the whole view "{label}" was added',
    ("view", "type_changed"): 'the view "{label}" was converted from {old_type} to {new_type}',
}

_FUTURE = {
    ("section", "removed"): "{label} will be removed",
    ("section", "added"): "{label} comes back",
    ("section", "moved"): "{label} moves back to where it was",
    ("badge", "removed"): "the badge {label} will be deleted",
    ("badge", "added"): "the badge {label} comes back",
    ("badge", "edited"): "the badge {label} goes back to how it was",
    ("badge", "moved"): "the badge {label} moves back to where it was",
    ("badge", "moved_to"): "the badge {label} moves back to {where}",
    ("setting", "added"): 'the setting "{label}" comes back as {new}',
    ("setting", "added_bare"): 'the setting "{label}" comes back',
    ("setting", "removed"): 'the setting "{label}" will be removed',
    ("setting", "edited"): 'the setting "{label}" goes back to {new}',
    ("setting", "edited_bare"): 'the setting "{label}" goes back to how it was',
    ("card", "removed"): "{label} will be deleted",
    ("card", "added"): "{label} comes back",
    ("card", "edited"): "{label} goes back to how it was",
    ("card", "moved"): "{label} moves back to where it was",
    ("card", "moved_to"): "{label} moves back to {where}",
    ("view", "removed"): 'the whole view "{label}" will be deleted',
    ("view", "added"): 'the whole view "{label}" comes back',
    ("view", "type_changed"): 'the view "{label}" changes layout from {old_type} to {new_type}',
}

# A dashboard restored from nothing would otherwise list every card it
# ever had - 661 of them on the installation this was built against.
_ENTRY_LIMIT = 12

_NOTHING_LOST = "Nothing on this dashboard is deleted."
_NOT_IN_CARDS = (
    "This change cannot be described in terms of cards - see the details below."
)


def _entry(words: dict, kind: str, what: str, label: str) -> Entry:
    return Entry(
        kind=kind,
        what=what,
        label=label,
        text=words[(what, kind)].format(label=label),
    )


def _value_text(value: Any) -> str | None:
    """A setting's value as a sentence can carry it, or None if it cannot.

    Short things only. A list or a block is left to the diff below the
    sentence, which shows it exactly (decision 11).
    """
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return f'"{_shorten(value)}"'
    return None


def _setting_entry(words: dict, change: SettingChange) -> Entry:
    label = ".".join(str(key) for key in change.path)
    if change.new is _ABSENT:
        kind, key, values = "removed", "removed", {}
    elif change.old is _ABSENT:
        new = _value_text(change.new)
        kind = "added"
        key, values = ("added", {"new": new}) if new is not None else ("added_bare", {})
    else:
        old, new = _value_text(change.old), _value_text(change.new)
        kind = "edited"
        # Whether `old` has to be there too depends on the wording this
        # tense uses, not on which table this happens to be - the same
        # reason `_explain` takes `reassure` instead of asking `words is
        # _FUTURE`. The future tense's own template never mentions
        # {old}, so a missing one there is nothing to fall back from.
        if new is not None and (old is not None or "{old}" not in words[("setting", "edited")]):
            key, values = "edited", {"old": old, "new": new}
        else:
            key, values = "edited_bare", {}
    return Entry(
        kind=kind,
        what="setting",
        label=label,
        text=words[("setting", key)].format(label=label, **values),
    )


def _section_setting_changes(pair: SectionPair) -> list[SettingChange]:
    """A paired section's own settings that differ, by name like a view's (M)."""
    out: list[SettingChange] = []
    _setting_leaves(pair.old.view_key, _own(pair.old.section), _own(pair.new.section), (), out)
    return out


def _capped(name: str, entries: list[Entry], scope: str = "view") -> ViewChanges:
    """Keep the list readable, and say how much it hides.

    Silently truncating would be the one thing this project must not do:
    a summary that omits without saying so is worse than a long one.
    """
    if len(entries) <= _ENTRY_LIMIT:
        return ViewChanges(view=name, entries=entries, scope=scope)
    return ViewChanges(
        view=name,
        entries=entries[:_ENTRY_LIMIT],
        more=len(entries) - _ENTRY_LIMIT,
        scope=scope,
    )


def _section_name(slot: Slot) -> str:
    """The section a card landed in, named the way Home Assistant names one.

    Not by a `title` field: measured on the installation this was built
    against, 0 of 80 sections carry one. Home Assistant names a section
    with a `heading` card at its top instead, and 51 of those 80 have
    one. Where there is none there is no name to give, and saying so
    beats inventing one. Named by the same rule as every other section
    (`_section_title`).
    """
    if slot.location[:1] != ("sections",):
        if slot.location == ("cards",) and _view_type(slot.view) == "sections":
            # The view's own list, in a sections view, is what Home
            # Assistant shows as "Imported cards" (decision 26).
            return 'the "Imported cards" area'
        return "another place in this view"
    sections = slot.view.get("sections") or []
    index = slot.location[1]
    section = sections[index] if 0 <= index < len(sections) else {}
    title = _section_title(section, index)
    return f"the {title}" if title.startswith('section "') else title


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
    settings_by_view: dict[Any, list[Entry]] = {}
    for change in setting_changes(old, new):
        settings_by_view.setdefault(change.view_key, []).append(_setting_entry(words, change))
    badges_by_view: dict[Any, list[Entry]] = {}
    badge_matching = match_badges(old, new)

    def badge(key: Any, kind: str, item: Any, where: str | None = None) -> None:
        label = _describe(item, fallback="badge")
        text_key = ("badge", "moved_to" if where else kind)
        badges_by_view.setdefault(key, []).append(
            Entry(
                kind=kind,
                what="badge",
                label=label,
                text=words[text_key].format(label=label, where=where),
            )
        )

    for slot in badge_matching.removed:
        badge(slot.view_key, "removed", slot.card)
    for slot in badge_matching.added:
        badge(slot.view_key, "added", slot.card)
    for _was, now in badge_matching.edited:
        badge(now.view_key, "edited", now.card)
    for was, now in badge_matching.moved:
        where = _where(was, now) if _place(was) != _place(now) else None
        badge(was.view_key, "moved", was.card, where)
    sections_by_view: dict[Any, list[Entry]] = {}

    def section(key: Any, kind: str, slot: SectionSlot) -> None:
        sections_by_view.setdefault(key, []).append(
            _entry(words, kind, "section", _section_title(slot.section, slot.index))
        )

    for slot in matching.sections.removed:
        section(slot.view_key, "removed", slot)
    for slot in matching.sections.added:
        section(slot.view_key, "added", slot)
    for pair in matching.sections.moved:
        section(pair.old.view_key, "moved", pair.old)
    for pair in matching.sections.pairs:
        if pair.how != "settings":
            continue
        title = _section_title(pair.old.section, pair.old.index)
        for change in _section_setting_changes(pair):
            said = _setting_entry(words, change)
            sections_by_view.setdefault(pair.old.view_key, []).append(
                Entry(
                    kind=said.kind,
                    what="section_setting",
                    label=f"{title}: {said.label}",
                    text=f"{title}: {said.text}",
                )
            )
    by_view: dict[Any, list[Entry]] = {}

    def add(key: Any, entry: Entry) -> None:
        by_view.setdefault(key, []).append(entry)

    for slot in matching.loose_removed():
        add(slot.view_key, _entry(words, "removed", "card", _describe(slot.card)))
    for slot in matching.loose_added():
        add(slot.view_key, _entry(words, "added", "card", _describe(slot.card)))
    for _was, now in matching.edited:
        add(now.view_key, _entry(words, "edited", "card", _describe(now.card)))
    for was, now in matching.moved:
        label = _describe(was.card)
        if matching.same_place(was, now):
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

    own = settings_by_view.get(None, [])
    if own:
        # The dashboard's own settings have no view to sit under, and a
        # heading "In the view dashboard" would invent one.
        groups.append(_capped("dashboard", own, scope="dashboard"))
        removed_anything = any(entry.kind == "removed" for entry in own)

    for key, old_view in _views_by_key(old):
        name = _view_name(old_view, key)
        if key not in new_views:
            # One line for the view, not one per card on it.
            groups.append(ViewChanges(name, [_entry(words, "removed", "view", name)]))
            removed_anything = True
            continue
        entries = [
            *settings_by_view.get(key, []),
            *badges_by_view.get(key, []),
            *sections_by_view.get(key, []),
            *by_view.get(key, []),
        ]
        new_view = new_views[key]
        old_type, new_type = _view_type(old_view), _view_type(new_view)
        if old_type != new_type:
            # Ahead of any card entries: the conversion is the actual
            # event, and `type` is not a card - without this, a save that
            # only converts a view has nothing to hang an entry on at all.
            entries.insert(
                0,
                Entry(
                    kind="type_changed",
                    what="view",
                    label=name,
                    text=words[("view", "type_changed")].format(
                        label=name, old_type=old_type, new_type=new_type
                    ),
                ),
            )
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


def _sections_part(count: int, verb: str) -> str:
    """"1 section moved", "2 sections added", or nothing."""
    if not count:
        return ""
    return f"{count} section{'s' if count != 1 else ''} {verb}"


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
    # `==` alone says 1 is True; the commit this message goes with does
    # not, and neither does the explanation shown under it.
    if same_config(old, new):
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
        _sections_part(counts.sections_removed, "removed"),
        _sections_part(counts.sections_added, "added"),
        _sections_part(counts.sections_moved, "moved"),
        f"{counts.removed} removed" if counts.removed else "",
        f"{counts.added} added" if counts.added else "",
        f"{counts.edited} edited" if counts.edited else "",
        f"{counts.moved} moved" if counts.moved else "",
        f"{counts.settings} setting{'s' if counts.settings != 1 else ''} changed"
        if counts.settings
        else "",
        f"{counts.badges} badge{'s' if counts.badges != 1 else ''} changed"
        if counts.badges
        else "",
    ]
    return f"{name}: " + (", ".join(part for part in parts if part) or "no card changes")


# One count part of a generated message, as a whole part rather than as
# something found inside one. The vocabulary is the one `change_message`
# writes just above and `_views` beside it; the two live next to each
# other on purpose, because a word added there and not here would read
# as "this is not a generated message at all".
_COUNT = re.compile(
    r"^\d+ (?:views? (?:added|removed)|sections? (?:added|removed|moved)"
    r"|added|removed|edited|moved|settings? changed|badges? changed)$"
)


def _counts(message: str) -> list[str] | None:
    """The count parts of a generated message, or None if it is not one.

    A generated count line is made *entirely* of counts, which is what
    makes this a structural reading rather than a search for words. The
    dashboard's own name sits in front of them behind a `": "`, and a
    name may hold one of those itself - "Home: ground floor" is a title
    somebody will write - so the lead-in is peeled off one `": "` at a
    time until what is left parses whole. Nothing parses whole by
    accident: `renamed to "3 added"` does not, because of the quotes;
    "icon, title changed" does not, because "icon" is not a count.
    """
    rest = message
    while True:
        parts = [part.strip() for part in rest.split(",")]
        if parts and all(_COUNT.match(part) for part in parts):
            return parts
        _, found, rest = rest.partition(": ")
        if not found:
            return None


def message_adds(message: str) -> bool:
    r"""Whether the change behind this message added something.

    Read here, where the wording is written, and read as a shape rather
    than sniffed for a substring. The panel used to run
    `/\d+ added/` over the message to decide whether offering a plain
    put-back would be a trap - a change that removed *and* added
    something cannot be undone by putting the removed thing back,
    because the added one stays. That is logic in the panel, which the
    design record rules out; worse, it is wrong on a real message. A
    dashboard renamed to `3 added` produces `home: renamed to "3 added"`
    and reads as a trap, on a change that touched no card at all.

    Views count as well as cards, and that is deliberate: the panel's
    regex missed `2 views added`, because of the word in between, and a
    view that appeared is as much a thing a put-back leaves standing as
    a card that did. The wider reading is the true one.

    False for every message that is not a count line - the first
    recorded state, a rename, a change found by comparison. None of
    those added anything the caller can put back.
    """
    parts = _counts(message)
    return any(part.endswith(" added") for part in parts or [])
