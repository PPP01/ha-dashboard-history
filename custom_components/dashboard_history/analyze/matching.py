"""Pairing sections, cards, badges and settings across two states."""

from __future__ import annotations

from dataclasses import replace
from typing import Any

from .model import (
    Matching,
    SectionMatching,
    SectionPair,
    SectionSlot,
    SettingChange,
    Slot,
    _ABSENT,
    _SectionAnchor,
    _by_position,
    _own,
    _place,
    _section_list,
    _translated,
    _views_by_key,
    TEXT_FIELDS,
    _weak_key,
    badge_containers,
    card_containers,
    fingerprint,
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



def _text_key(slot: Slot) -> str | None:
    """The type of a card that is named by its own text, else None."""
    key = _weak_key(slot.card)
    if key is None or key[1] not in TEXT_FIELDS:
        return None
    return key[0]



def _renamed(
    old_open: list[Slot],
    new_open: list[Slot],
    taken_old: set[int],
    taken_new: set[int],
    translate: dict,
) -> list[tuple[int, int]]:
    """Pair the cards whose only name is their text, and whose text changed.

    Such a card's weak key IS the text, so editing the text is the one
    edit pass 3 cannot see: a heading renamed from "Blau" to "History"
    read as one deleted and one added, with whatever else was edited
    along with it. Paired here, and only when nothing is left to guess
    between: exactly one such card of that type on each side of a list.
    Two of them and which is which is not knowable, and stays a deletion
    plus an addition - restoring is additive, never a guessed pairing.

    Claims what it pairs in `taken_old`/`taken_new`.
    """
    old_by: dict[tuple, list[int]] = {}
    new_by: dict[tuple, list[int]] = {}
    # The taken check comes first: passes 1-3 have claimed nearly every
    # card by now, and `_weak_key` is not free.
    for i, slot in enumerate(old_open):
        if i not in taken_old and (kind := _text_key(slot)) is not None:
            old_by.setdefault((_translated(slot, translate), kind), []).append(i)
    for j, slot in enumerate(new_open):
        if j not in taken_new and (kind := _text_key(slot)) is not None:
            new_by.setdefault((_place(slot), kind), []).append(j)
    pairs = [
        (olds[0], new_by[group][0])
        for group, olds in old_by.items()
        if len(olds) == 1 and len(new_by.get(group, ())) == 1
    ]
    for i, j in pairs:
        taken_old.add(i)
        taken_new.add(j)
    return pairs



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
    edited.extend(_renamed(old_open, new_open, taken_old, taken_new, translate))

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
