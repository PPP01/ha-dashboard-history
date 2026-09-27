"""Types, and how a dashboard is read and named."""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any, NamedTuple


class _SectionAnchor(NamedTuple):
    """What the section a removed card sat in was, when it sat in one.

    A plain `tuple` underneath - `restore._anchored_index` unpacks it
    positionally and cannot import this type - but named here so the five
    positions are not five unlabelled counts to keep straight in the two
    places that build or read one.
    """

    sections: int  # how many sections the view had
    settings: dict | None  # the section's own settings, everything but `cards`
    survivors: tuple  # the cards that should still stand beside this one
    before: int  # how many of them stood ahead of this card
    departed: tuple = ()  # its neighbours that left for another list in the view since



@dataclass(frozen=True)
class RemovedItem:
    """Something that was present before and is gone now."""

    kind: str  # "card", "view" or "section"
    view_path: str | None
    view_index: int  # position of the view in the old configuration
    location: tuple  # path to the card list inside the view
    index: int  # position in the card list, or of the view itself
    payload: dict
    label: str
    # What the section this card sat in was, when it sat in one: how many
    # sections the view had, that section's own settings, and the cards
    # that should still stand beside it. A section carries no path and no
    # id, so this is the only proof there is that index i still means it
    # - and when it fails, the card is parked instead (decision 26).
    anchor: _SectionAnchor | None = None
    # The other sections of that view, in order, as they stood when this
    # section was removed - only on `kind="section"`. It is the proof that
    # the gap this goes back into is the only one it could go into: if
    # today's sections are exactly these, then index `index` is the single
    # place missing. Carried as the sections themselves rather than as
    # fingerprints of them, because `restore` compares it with `==` and
    # cannot import `analyze.fingerprint` at runtime.
    neighbours: tuple | None = None
    # The view's own name, the same way `_view_name` resolves it for the
    # human-readable diff (title, else path, else position) - so a list of
    # removed items can be grouped and headed the same way that diff
    # already groups its own entries, instead of a raw `view_path` that is
    # `None` for a pathless view and a bare slug rather than its title.
    view_title: str | None = None



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
    settings: int = 0
    badges: int = 0
    sections_moved: int = 0
    sections_added: int = 0
    sections_removed: int = 0



@dataclass(frozen=True)
class Entry:
    """One nameable thing that changed."""

    kind: str  # "removed", "added", "edited" or "moved"
    what: str  # "card", "view", "badge", "setting", "section" or "section_setting"
    label: str
    text: str  # the finished sentence, ready to show



@dataclass(frozen=True)
class ViewChanges:
    """What changed in one view, or on the dashboard itself.

    `more` is what the cap left out. `scope` is "dashboard" for the one
    group about the dashboard's own settings (GitHub #28), which has no
    view to be headed by.
    """

    view: str
    entries: list[Entry]
    more: int = 0
    scope: str = "view" 



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



def badge_containers(view: dict) -> Iterator[tuple[tuple, list]]:
    """Yield a view's own badge list, with the path that locates it.

    Only the list beside `cards:` (GitHub #29). A badge inside a card -
    a heading card's own `badges:` - is part of that card's body and
    travels with it, so it is never looked at here.
    """
    if isinstance(view.get("badges"), list):
        yield ("badges",), view["badges"]



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



def _describe(card: Any, depth: int = 0, fallback: str = "card") -> str:
    """A short human-readable label for a card.

    The field order differs from _weak_key on purpose: identity wants the
    most stable field, a label wants the most human one.
    """
    if not isinstance(card, dict):
        return str(card)
    kind = str(card.get("type", fallback))
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
    # The card's fingerprint, computed once here rather than by every
    # consumer that needs it (GitHub #38) - `match_cards`'s own passes,
    # `_group_by_mark`, and `plan_undo`'s `sole`/`sole_badge` all read
    # this instead of calling `fingerprint(slot.card)` again.
    mark: str



@dataclass(frozen=True)
class SectionMatching:
    """What happened to a dashboard's sections between two states (#31).

    `pairs` are the sections found in both, `moved` the pairs outside the
    run that kept its order. `removed` and `added` are sections proven to
    have gone or come whole. `rest_old` and `rest_new` are what neither
    explains: the explanation says nothing about them, and an undo of a
    view that has any refuses.
    """

    pairs: tuple = ()
    moved: tuple = ()
    removed: tuple = ()
    added: tuple = ()
    rest_old: tuple = ()
    rest_new: tuple = ()

    def views(self) -> set:
        """Every view this matching has something to say about."""
        return (
            {pair.old.view_key for pair in self.moved}
            | {pair.old.view_key for pair in self.pairs if pair.how == "settings"}
            | {
                slot.view_key
                for slot in (*self.removed, *self.added, *self.rest_old, *self.rest_new)
            }
        )



@dataclass(frozen=True)
class Matching:
    """Every card of one dashboard, paired across two of its states."""

    removed: list
    added: list
    edited: list  # (old, new)
    moved: list  # (old, new)
    sections: SectionMatching = field(default_factory=SectionMatching)
    # (view key, old section index) -> new index, for every paired
    # section (GitHub #31).
    translate: dict = field(default_factory=dict)

    def same_place(self, old: Slot, new: Slot) -> bool:
        """Whether a card stayed in its list, its section followed wherever it went."""
        return _translated(old, self.translate) == _place(new)

    def loose_removed(self) -> list:
        """Removed cards, less those of a section that went whole."""
        whole = {(s.view_key, ("sections", s.index, "cards")) for s in self.sections.removed}
        return [slot for slot in self.removed if (slot.view_key, slot.location) not in whole]

    def loose_added(self) -> list:
        """Added cards, less those of a section that came whole."""
        whole = {(s.view_key, ("sections", s.index, "cards")) for s in self.sections.added}
        return [slot for slot in self.added if (slot.view_key, slot.location) not in whole]



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

    action: str  # "remove" | "insert" | "set" | "unset"
    kind: str  # "card" | "badge" | "view" | "dashboard_setting" | "view_setting" | "sections_list"
    view_path: str | None
    view_index: int
    location: tuple
    index: int
    expect: Any
    payload: Any
    label: str
    # Decision 26: an insertion whose section cannot be proven any more
    # goes to the end of the view's own `cards:` - Home Assistant's
    # "Imported cards" - instead of to an index. `location` is then
    # ("cards",), and `index` only keeps the order of the old place.
    parked: bool = False
    # For a setting step: that nothing is expected at this address today.
    # Its own field because None is a value (`theme: null`), not absence.
    expect_absent: bool = False



@dataclass(frozen=True)
class UndoPlan:
    """Either a reason not to take a change back, or the steps that do.

    Never both. A half-applied undo leaves a state nobody asked for and
    which the row beside it no longer describes, so one unresolvable
    piece blocks the whole thing - decision 15.
    """

    blocked: str | None
    steps: tuple = ()

    @property
    def parked(self) -> tuple[str, ...]:
        """What this plan cannot put back exactly, only make available."""
        return tuple(step.label for step in self.steps if step.parked)



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



def same_config(one: dict, other: dict) -> bool:
    """`==`, but not blind to 1 against True (GitHub #28).

    Since named settings are undoable, `max_columns: 1` and
    `max_columns: true` are two states an undo moves between; Python's
    `==` calls them equal. `fingerprint` only runs when `==` already
    said yes, so the common case costs what it did. Not `_same`: that
    one is for a single setting's value and knows `_ABSENT`; this is for
    two whole dashboard configurations, the shape `change_message` and
    `operations.async_undo_change` both compare.
    """
    return one == other and fingerprint(one) == fingerprint(other)



def _place(slot: Slot) -> tuple:
    """The card list a slot belongs to, across the whole dashboard."""
    return (slot.view_key, slot.location)



def _translated(slot: Slot, translate: dict) -> tuple:
    """Where an old slot's list is in the new state, its section followed.

    A card in a paired section sits, for comparison, in the list of that
    section wherever it went - so a section moved whole moves none of its
    cards. Every other card keeps its plain place, its real index (spec
    O, section 1): a section nothing paired is as if there were no
    section pairing at all.
    """
    location = slot.location
    if len(location) == 3 and location[0] == "sections" and (slot.view_key, location[1]) in translate:
        return (slot.view_key, ("sections", translate[(slot.view_key, location[1])], "cards"))
    return _place(slot)



@dataclass(frozen=True)
class SectionSlot:
    """One section at the place it sits in a view (GitHub #31)."""

    view_key: Any
    view_index: int
    index: int
    section: Any



@dataclass(frozen=True)
class SectionPair:
    """One section found in both states; `how` names the pass that found it."""

    old: SectionSlot
    new: SectionSlot
    how: str  # "same", "found", "settings" or "cards"



def _own(section: Any) -> Any:
    """A section's own settings: everything but its cards."""
    if not isinstance(section, dict):
        return section
    return {key: value for key, value in section.items() if key != "cards"}



def _section_list(view: dict) -> list:
    """A view's sections, or none - `sections:` may be missing or null."""
    sections = view.get("sections")
    return sections if isinstance(sections, list) else []



def _views_by_key(config: dict) -> list[tuple[Any, dict]]:
    """Views paired with the key that identifies them across states."""
    result = []
    for index, view in enumerate(config.get("views") or []):
        if not isinstance(view, dict):
            continue
        result.append((view.get("path") or ("#", index), view))
    return result



def _by_position(config: dict, before: int | None = None) -> dict:
    """Only the views keyed by where they sit, by that key.

    `before`, when given, drops every position at or past it - the
    positions neither state can vouch for (see `_positions_lie`).
    """
    return {
        key: view
        for key, view in _views_by_key(config)
        if isinstance(key, tuple)
        and key
        and key[0] == "#"
        and (before is None or key[1] < before)
    }



# "Not there", as opposed to None - which YAML writes as `null` and which
# is a value like any other (`theme: null`).
_ABSENT = object()



@dataclass(frozen=True)
class SettingChange:
    """One named setting that differs between two states (GitHub #28).

    Named, not positional: `strategy.show_clock_card` means the same thing
    in every state, so it needs no matching - its path is its identity.
    `view_key` is None for the dashboard itself.
    """

    view_key: Any
    path: tuple
    old: Any
    new: Any



def _section_title(section: Any, index: int) -> str:
    """What to call a section: its heading card, else its title, else its place.

    Home Assistant names a section with a heading card at its top - 72
    of 102 on the installation this was built against - and all but never
    with `title` (0 of 102). Only a real heading card counts: a card of
    another type with a `heading` field of its own names nothing.
    """
    cards = section.get("cards") if isinstance(section, dict) else None
    first = cards[0] if isinstance(cards, list) and cards else None
    if (
        isinstance(first, dict)
        and first.get("type") == "heading"
        and isinstance(first.get("heading"), str)
        and first["heading"].strip()
    ):
        return f'section "{_shorten(first["heading"])}"'
    title = section.get("title") if isinstance(section, dict) else None
    if isinstance(title, str) and title.strip():
        return f'section "{_shorten(title)}"'
    return f"section {index + 1}"



def _view_name(view: dict, key) -> str:
    """What to call a view: its title, else its path, else its position."""
    return str(view.get("title") or view.get("path") or key)
