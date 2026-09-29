"""Planning the targeted undo of one change (decision 15)."""

from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from .matching import (
    _moved,
    _pair_view_sections,
    _paths_collide,
    _positions_lie,
    _same,
    _section_drift,
    _setting_at,
    _slots,
    _view_type_changed,
    match_badges,
    match_cards,
    setting_changes,
)
from .model import (
    SectionMatching,
    SectionSlot,
    Slot,
    UndoPlan,
    UndoStep,
    _ABSENT,
    _describe,
    _section_list,
    _section_title,
    _view_name,
    _views_by_key,
    badge_containers,
    card_containers,
    fingerprint,
)


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



def _rearranged(key: Any, name: str, after_view: dict, current_view: dict) -> str | None:
    """Why the sections cannot be proven to stand where the change left them.

    Since the change: nothing arrived, went or moved among the sections,
    so each stands at the index it had after the change. One of them may
    have been edited since - its identity is then forced, every other
    one standing byte for byte in its place. Two edited since could as
    well have swapped places too, and index is no proof of which is
    which.
    """
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
    return None


def _park_removed_section(
    ctx: UndoContext,
    key: Any,
    current_view: dict,
    current_index: int,
    removed: SectionSlot,
) -> tuple[UndoStep, ...]:
    """The cards of a removed section, parked in the view's "Imported cards".

    GitHub #39, decision 26 for a whole section: where the section stood
    can no longer be proven, so its cards go to the end of `cards:` -
    one step each, the form `apply_undo` already writes for a parked
    card. Idempotent like the card path: per card, as many copies as
    the change took from the view and are not back since. Nothing is
    ever refused here - only added, so a copy too many is the lesser
    harm, and which of several alike is missing does not matter.

    Reads `ctx.card_now`/`ctx.card_then` here, earlier than the cards
    planner would - both are cached, and only on this path, so no
    entry in `_COMPUTED_BEFORE["sections"]` is needed.
    """
    cards = removed.section["cards"]
    marks = [fingerprint(card) for card in cards]
    missing = {
        mark: max(0, marks.count(mark) - _card_came_back(ctx, mark, key))
        for mark in set(marks)
    }
    steps: list[UndoStep] = []
    for position, (card, mark) in enumerate(zip(cards, marks)):
        if missing[mark] == 0:
            continue
        missing[mark] -= 1
        steps.append(
            UndoStep(
                action="insert",
                kind="card",
                view_path=current_view.get("path"),
                view_index=current_index,
                location=("cards",),
                index=position,
                expect=None,
                payload=copy.deepcopy(card),
                label=_describe(card),
                parked=True,
            )
        )
    return tuple(steps)


def _card_events_in(ctx: UndoContext, key: Any) -> bool:
    """Whether the change touched a single card of this view.

    Edited, moved, added or removed - the card matching's own answer,
    wherever the card sat (a section or `cards:`). The removed section's
    own cards are not among them: `loose_removed` leaves them out.
    """
    matching = ctx.matching
    moves = (*matching.edited, *matching.moved)
    return any(key in (old.view_key, new.view_key) for old, new in moves) or any(
        slot.view_key == key for slot in (*matching.loose_added(), *matching.loose_removed())
    )


def _park_instead(
    refusal: str,
    ctx: UndoContext | None,
    key: Any,
    current_view: dict,
    current_index: int,
    removed: list,
    mixed: bool,
) -> tuple[UndoStep, ...] | str:
    """Park the one removed section's cards where the exact undo refuses.

    Only for a view whose change was that one removal and nothing else:
    `mixed` says a section moved, was reset or arrived, and a single card
    of the view changed as well. That last one is asked here, not left
    to `_sections_meet_cards`: with every removed card back, no section
    step is planned, the gate has no view to protect and would let a
    partial undo of the card change through. Only from the undo: without
    `ctx` there is nothing to count against and the refusal stands.
    """
    if ctx is None or mixed or len(removed) != 1 or _card_events_in(ctx, key):
        return refusal
    return _park_removed_section(ctx, key, current_view, current_index, removed[0])


def _plan_sections(
    key: Any,
    before_view: dict,
    after_view: dict,
    current_view: dict | None,
    current_index: int,
    change: SectionMatching,
    ctx: UndoContext | None = None,
) -> UndoStep | tuple[UndoStep, ...] | str | None:
    """The one step that puts a view's sections back, why it cannot, or None.

    Decision 15 for sections (GitHub #31). A section has no address but
    its index, and several moved at once shift each other's - so nothing
    here is an index: the whole row is rebuilt in `before`'s order and
    written in one step. `before`'s order says where each goes; today's
    state is where each one's content comes from. What makes that exact
    is asked first, all of it or nothing.

    In a view whose change was one removed section and nothing else, a
    rearrangement since parks the section's cards instead of refusing
    (GitHub #39).
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

    refusal = _rearranged(key, name, after_view, current_view)
    if refusal is not None:
        return _park_instead(
            refusal, ctx, key, current_view, current_index, removed, bool(moved or reset or added)
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



@dataclass(frozen=True, eq=False)
class UndoContext:
    """The three states of one undo, and what several planners read of them.

    Everything derived is computed once and kept. `plan_undo` asks for
    each value at the point where the single function it replaced
    computed it (`_COMPUTED_FIRST`, `_COMPUTED_BEFORE`), so an input that
    makes one of them raise still raises there.
    """

    before: dict
    after: dict
    current: dict

    @cached_property
    def matching(self):
        return match_cards(self.before, self.after)

    @cached_property
    def badge_matching(self):
        return match_badges(self.before, self.after)

    @cached_property
    def old_views(self) -> dict:
        return dict(_views_by_key(self.before))

    @cached_property
    def new_views(self) -> dict:
        return dict(_views_by_key(self.after))

    @cached_property
    def now_views(self) -> dict:
        return dict(_views_by_key(self.current))

    @cached_property
    def now_places(self) -> list:
        return _views_by_key(self.current)

    @cached_property
    def now_index(self) -> dict:
        return {key: index for index, (key, _) in enumerate(_views_by_key(self.current))}

    @cached_property
    def pairs(self) -> tuple:
        # Every state this plan reads from or writes to has to agree on
        # what a position means: `before` and `after` decide what the
        # change was, `current` is where the steps land.
        return (
            (self.before, self.after),
            (self.before, self.current),
            (self.after, self.current),
        )

    @cached_property
    def type_changed(self) -> bool:
        return any(_view_type_changed(one, other) for one, other in self.pairs)

    @cached_property
    def settings(self) -> list:
        return setting_changes(self.before, self.after)

    @cached_property
    def shifted(self) -> set:
        return _section_drift(self.new_views, self.now_views)

    @cached_property
    def card_now(self) -> dict:
        return _group_by_mark(_present(self.current))

    @cached_property
    def card_then(self) -> dict:
        return _group_by_mark(_present(self.after))

    @cached_property
    def badge_now(self) -> dict:
        return _group_by_mark(_present(self.current, badge_containers))

    @cached_property
    def badge_then(self) -> dict:
        return _group_by_mark(_present(self.after, badge_containers))


# -- checks that come before any planner -----------------------------------


def _nothing_changed(ctx: UndoContext) -> str | None:
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
    matching, badges = ctx.matching, ctx.badge_matching
    if (
        matching.removed
        or matching.added
        or matching.edited
        or matching.moved
        or badges.removed
        or badges.added
        or badges.edited
        or badges.moved
        or set(ctx.old_views) ^ set(ctx.new_views)
        or ctx.type_changed
        or ctx.settings
        or matching.sections.views()
    ):
        return None
    return "this change did not alter any cards"


def _paths_collide_anywhere(ctx: UndoContext) -> str | None:
    # Before any pair is compared: a path that names two views is not an
    # identity, and everything below reads views by their path.
    if any(_paths_collide(state) for state in (ctx.before, ctx.after, ctx.current)):
        return _DUPLICATE_PATH_REFUSAL
    return None


def _positions_disagree(ctx: UndoContext) -> str | None:
    if any(_positions_lie(one, other) for one, other in ctx.pairs):
        return _POSITION_REFUSAL
    return None


def _view_type_converted(ctx: UndoContext) -> str | None:
    # Checked before `_section_drift`: a conversion changes the section
    # list too, and would otherwise be blamed on "the sections" instead
    # of on itself.
    return _VIEW_TYPE_REFUSAL if ctx.type_changed else None


# -- the planners, one per kind --------------------------------------------


def _plan_section_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    # A view whose sections the change rearranged is put back in one step
    # of its own (GitHub #31) - or refused, and then before anything else.
    steps: list[UndoStep] = []
    for key in sorted(ctx.matching.sections.views(), key=str):
        planned = _plan_sections(
            key,
            ctx.old_views[key],
            ctx.new_views[key],
            ctx.now_views.get(key),
            ctx.now_index.get(key, -1),
            ctx.matching.sections,
            ctx,
        )
        if isinstance(planned, str):
            return planned
        if isinstance(planned, tuple):
            steps.extend(planned)
        elif planned is not None:
            steps.append(planned)
    return tuple(steps)


def _plan_setting_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    steps: list[UndoStep] = []
    for change in ctx.settings:
        label = ".".join(str(key) for key in change.path)
        if change.view_key is None:
            container = ctx.current
        else:
            container = ctx.now_views.get(change.view_key)
            if container is None:
                name = _view_name(ctx.old_views[change.view_key], change.view_key)
                return (
                    f'the view "{name}" is no longer on the dashboard, '
                    f'so its setting "{label}" cannot be taken back'
                )
        standing, vanished = _setting_at(container, change.path)
        if vanished is not None:
            return f'the setting "{label}" no longer has the "{vanished}" block it belonged to'
        if _same(standing, change.old):
            # Already back, the way a deleted card that returned is.
            continue
        if not _same(standing, change.new):
            return f'the setting "{label}" was changed again after this'
        key = change.view_key
        steps.append(
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
    return tuple(steps)


def _sole_card(ctx: UndoContext, slot: Slot, label: str) -> tuple[Slot | None, str | None]:
    # Counted in two stages, the same way `_sole_badge` below counts
    # badges (GitHub #36): "exactly one today" is not proof by itself -
    # an untouched copy that stood there before the change is not the
    # one the change produced. Asked first dashboard-wide, then, failing
    # that, in the card's own view.
    found, left = ctx.card_now.get(slot.mark, []), ctx.card_then.get(slot.mark, [])
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


def _put_back(ctx: UndoContext, old_slot: Slot, label: str) -> tuple[tuple | None, UndoStep]:
    """Insert where the card came from, or park it in "Imported cards".

    Returns the step and, for a parked one, the place it came from - the
    step's own `view_index` and `index` already carry `old_slot`'s, only
    its original `location` does not, overwritten to `("cards",)` for
    `apply_undo` to find and to show, so that is the one piece kept
    beside the step for sorting. An ordinary insert comes with `None`.
    """
    if old_slot.view_key not in ctx.shifted or old_slot.location[:1] != ("sections",):
        return None, _step(old_slot, "insert", None, old_slot.card, label)
    # A pathless view is found by its position here, which
    # `_positions_lie` has already vouched for - the same proof an
    # ordinary insert into it rests on.
    return old_slot.location, _step(
        old_slot,
        "insert",
        None,
        old_slot.card,
        # The card that is parked, not the one taken out: the dialog
        # lists what somebody has to go and place.
        _describe(old_slot.card),
        location=("cards",),
        parked=True,
    )


def _card_came_back(ctx: UndoContext, mark: str, view_key: Any) -> int:
    return len(_in_view(ctx.card_now.get(mark, []), view_key)) - len(
        _in_view(ctx.card_then.get(mark, []), view_key)
    )


def _parked_order(item: tuple[tuple, UndoStep]) -> tuple:
    # In the order of the places they came from - view, section, card -
    # whichever of the three tables in decision 15 produced them.
    location, step = item
    return (step.view_index, location, step.index)


def _plan_card_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    matching = ctx.matching
    placed: list[tuple[tuple | None, UndoStep]] = []

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
        here, why = _sole_card(ctx, new_slot, label)
        if here is None:
            return why
        placed.append((None, _step(here, "remove", new_slot.card, None, label)))
        placed.append(_put_back(ctx, old_slot, label))

    for new_slot in matching.loose_added():
        label = _describe(new_slot.card)
        here, why = _sole_card(ctx, new_slot, label)
        if here is None:
            return why
        placed.append((None, _step(here, "remove", new_slot.card, None, label)))

    # Counted, not looked up, and only in the card's own view (GitHub
    # #35): an untouched copy on another view - there all along or added
    # since - is not this one coming back. A dashboard-wide look would
    # reopen the same door the bug used: a copy someone else placed
    # elsewhere after the change would count as this card's return.
    # Mirrors the badge rule below (Vorhaben N) - `deleted` is how many
    # alike the change took from that view, `_card_came_back` how many
    # more stand there now than the change left.
    removed = [(old_slot, old_slot.mark) for old_slot in matching.loose_removed()]
    deleted: dict[tuple[str, Any], int] = {}
    for old_slot, mark in removed:
        place = (mark, old_slot.view_key)
        deleted[place] = deleted.get(place, 0) + 1

    for old_slot, mark in removed:
        label = _describe(old_slot.card)
        back = _card_came_back(ctx, mark, old_slot.view_key)
        if back >= deleted[(mark, old_slot.view_key)]:
            # Already back by some other route. Inserting would make a
            # second copy, and this part of the change is undone either
            # way.
            continue
        if back > 0:
            # Some of several alike are back: which places they took is
            # not in the states, and picking one would be a guess.
            return (
                f"only some of the copies of {label} this change "
                f"deleted are back, so an exact undo cannot tell "
                f"which are missing"
            )
        placed.append(_put_back(ctx, old_slot, label))

    # Parked insertions go after every other card step, sorted.
    ordinary = [step for where, step in placed if where is None]
    parked = sorted(((where, step) for where, step in placed if where is not None), key=_parked_order)
    return (*ordinary, *(step for _where, step in parked))


def _sole_badge(ctx: UndoContext, slot: Slot, label: str) -> tuple[Slot | None, str | None]:
    # Badges (GitHub #29): the same table as cards, counted in their own
    # world. The same badge on several views is ordinary - 6 of 23 on the
    # installation this was built against - so "exactly once" is asked in
    # two stages: on the whole dashboard, and failing that, in the view
    # the change left it in. Both answer decision 15's question; the
    # second only asks it where the badge was left. And both compare
    # today with what the change left: one standing today, out of several
    # the change left, may be the one that was there before it.
    found, left = ctx.badge_now.get(slot.mark, []), ctx.badge_then.get(slot.mark, [])
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


def _badge_came_back(ctx: UndoContext, mark: str, view_key: Any) -> int:
    return len(_in_view(ctx.badge_now.get(mark, []), view_key)) - len(
        _in_view(ctx.badge_then.get(mark, []), view_key)
    )


def _badge_label(badge: Any) -> str:
    return f"the badge {_describe(badge, fallback='badge')}"


def _plan_badge_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    matching = ctx.badge_matching
    steps: list[UndoStep] = []
    for old_slot, new_slot in (*matching.edited, *matching.moved):
        label = _badge_label(new_slot.card)
        here, why = _sole_badge(ctx, new_slot, label)
        if here is None:
            return why
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))

    for new_slot in matching.added:
        label = _badge_label(new_slot.card)
        here, why = _sole_badge(ctx, new_slot, label)
        if here is None:
            return why
        steps.append(_step(here, "remove", new_slot.card, None, label, kind="badge"))

    # Counted, not looked up, and only in the badge's own view: a copy on
    # another view - there all along or added since - is not this badge
    # coming back. `_badge_came_back` is how many more stand there now
    # than the change left; `deleted` how many alike it took from that
    # view. Each removed slot's mark is kept beside it - `deleted` and the
    # loop below both need it, and it is already sitting on the slot.
    removed = [(old_slot, old_slot.mark) for old_slot in matching.removed]
    deleted: dict[tuple[str, Any], int] = {}
    for old_slot, mark in removed:
        place = (mark, old_slot.view_key)
        deleted[place] = deleted.get(place, 0) + 1

    for old_slot, mark in removed:
        label = _badge_label(old_slot.card)
        back = _badge_came_back(ctx, mark, old_slot.view_key)
        if back >= deleted[(mark, old_slot.view_key)]:
            continue
        if back > 0:
            # Some of several alike are back: which places they took is
            # not in the states, and picking one would be a guess.
            return (
                f"only some of the copies of {label} this change deleted "
                f"are back, so an exact undo cannot tell which are missing"
            )
        steps.append(_step(old_slot, "insert", None, old_slot.card, label, kind="badge"))
    return tuple(steps)


# Whole views, which `match_cards` leaves out on purpose: a view that
# only one state has is one line in the history, not one per card on
# it. Undoing it is the same two questions in a coarser grain - is it
# still exactly as the change left it, and is it still there at all.
#
# Both halves ask that of the view's *content*, not of its key. A
# key is a path, and a path is renameable and reusable: asking only
# whether one is present answers "already taken back" for a view
# somebody renamed, and "already back" for a stranger that happens to
# sit on the same path. Both are the one error this tool must never
# make - a sentence that says nothing changed while something did.


def _plan_added_views(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    steps: list[UndoStep] = []
    for key, view in _views_by_key(ctx.after):
        if key in ctx.old_views:
            continue
        # The change added this view. Take it away - the very one it
        # added, found by what it holds.
        name = _view_name(view, key)
        found = [index for index, (_, standing) in enumerate(ctx.now_places) if standing == view]
        if len(found) > 1:
            return (
                f'{len(found)} views now look exactly like "{name}", '
                f"so an exact undo cannot tell them apart"
            )
        if not found:
            if key in ctx.now_views:
                return f'the view "{name}" was changed again after this'
            return (
                f'the view "{name}" is no longer on the dashboard as '
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
    return tuple(steps)


def _plan_removed_views(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    steps: list[UndoStep] = []
    for index, (key, view) in enumerate(_views_by_key(ctx.before)):
        if key in ctx.new_views:
            # The change did not remove it.
            continue
        # Already back, either on its own path or - a view without one is
        # keyed by its position - somewhere else. Inserting would make a
        # second copy.
        if any(standing == view for _, standing in ctx.now_places):
            continue
        standing = ctx.now_views.get(key)
        if standing is not None and view.get("path") is not None:
            # A different view holds that path today. Two views on one
            # path is a broken dashboard, and picking one of them is a
            # guess, so this refuses instead.
            return (
                f'a different view now sits at "{view["path"]}", so the '
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
    return tuple(steps)


def _plan_view_steps(ctx: UndoContext) -> str | tuple[UndoStep, ...]:
    added = _plan_added_views(ctx)
    if isinstance(added, str):
        return added
    removed = _plan_removed_views(ctx)
    if isinstance(removed, str):
        return removed
    return (*added, *removed)


def _sections_meet_cards(planned: dict) -> str | None:
    """Q1: a view's whole row of sections next to a card step in the same view.

    One step writes a view's whole row of sections; a card step in the
    same view would write into a row that step replaces. Unlike the
    other stages this reads what the planners produced, not the context,
    so the combiner calls it after the last planner.
    """
    rewritten = {step.view_path or ("#", step.view_index) for step in planned["sections"]}
    if any(
        step.kind == "card" and (step.view_path or ("#", step.view_index)) in rewritten
        for kind in _OUTPUT_ORDER
        if kind != "sections"
        for step in planned[kind]
    ):
        return _SECTIONS_AND_CARDS_REFUSAL
    return None


# -- the combiner ------------------------------------------------------------

_GATES = (_nothing_changed, _paths_collide_anywhere, _positions_disagree, _view_type_converted)

_PLANNERS = {
    "sections": _plan_section_steps,
    "settings": _plan_setting_steps,
    "cards": _plan_card_steps,
    "badges": _plan_badge_steps,
    "views": _plan_view_steps,
}

# The order in which refusals are looked for; the first one found is the
# answer. Sections first: a view whose sections the change rearranged is
# refused before anything else is asked of it (GitHub #31). A new kind of
# change adds its planner here AND to _OUTPUT_ORDER, deciding both places.
_CHECK_ORDER = ("sections", "settings", "cards", "badges", "views")

# Computed where the single plan_undo computed them, whether a planner
# goes on to read them or not. An input that makes one of them raise -
# a view whose "sections" is a number, say - has to raise at the same
# point as before, not later or not at all (Astra, plan review). The
# order inside each tuple is the order they were computed in.
_COMPUTED_FIRST = (
    "matching",
    "badge_matching",
    "old_views",
    "new_views",
    "now_views",
    "type_changed",
    "settings",
)
_COMPUTED_BEFORE = {
    "sections": ("shifted", "now_index"),
    "cards": ("card_now", "card_then"),
    "badges": ("badge_now", "badge_then"),
    "views": ("now_places",),
}

# The order in which the steps are handed to apply_undo. It is observable:
# apply_undo sorts by index only, with a stable sort, so steps on equal
# indices keep this order - across kinds too. Settings first (they shift
# no index), sections last although checked first: a section step
# replaces a whole row, after the single cards in it are settled.
_OUTPUT_ORDER = ("settings", "cards", "badges", "views", "sections")


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
    # The work is done by four checks, one planner per kind and one check
    # across two planners (spec P, section 3); this function only runs
    # them in _CHECK_ORDER and hands the steps on in _OUTPUT_ORDER. The
    # docstring above is the old one, unchanged (spec P, section 3).
    ctx = UndoContext(before, after, current)
    for name in _COMPUTED_FIRST:
        getattr(ctx, name)
    for gate in _GATES:
        refusal = gate(ctx)
        if refusal is not None:
            return UndoPlan(blocked=refusal)
    planned: dict[str, tuple[UndoStep, ...]] = {}
    for kind in _CHECK_ORDER:
        for name in _COMPUTED_BEFORE.get(kind, ()):
            getattr(ctx, name)
        result = _PLANNERS[kind](ctx)
        if isinstance(result, str):
            return UndoPlan(blocked=result)
        planned[kind] = result
    refusal = _sections_meet_cards(planned)
    if refusal is not None:
        return UndoPlan(blocked=refusal)
    return UndoPlan(blocked=None, steps=tuple(step for kind in _OUTPUT_ORDER for step in planned[kind]))
