"""Planning the targeted undo of one change (decision 15)."""

from __future__ import annotations

import copy
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
