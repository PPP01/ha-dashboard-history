"""Putting removed items back into a live configuration.

Restoring a disappearance is additive: nothing is overwritten, so there
is no merge and no ambiguity. That is the whole reason this integration
restricts itself to disappearances rather than trying to undo edits.

The configuration handed in is never modified. The caller still needs the
old state to render a preview against.
"""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Only needed for the annotations, and `from __future__ import
    # annotations` keeps those lazy. A real import would have to be
    # relative inside the integration and absolute in the tests, which
    # load this module flat - it cannot be both.
    from .analyze import RemovedItem, UndoPlan, UndoStep


def _paths_share(config: dict) -> bool:
    """Whether two views of this state claim the same URL path.

    Written here rather than imported: this module has no runtime import
    of `analyze` on purpose (see the note at the top of the file), so the
    five lines live twice. `_find_view` walks the views by path and
    returns the first match, which is exactly the wrong answer when there
    are two.
    """
    paths = [
        view.get("path")
        for view in config.get("views") or []
        if isinstance(view, dict) and view.get("path")
    ]
    return len(paths) != len(set(paths))


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


def _anchored_index(view: dict, item: RemovedItem) -> int | None:
    """Where the card goes back in its section, or None if that is unproven.

    Only cards that sat in a section carry an anchor, so everything else
    passes straight through. The section has to have the same settings
    and still hold the cards that stood beside this one, in their order;
    cards added since may sit between them. A card that was alone has
    nothing beside it to recognise the section by, so then the section
    has to be empty. See `analyze._section_anchor` for why a title was
    never enough.

    The answer is an index, not a yes: right after the last survivor that
    stood ahead of the card, or right before the first one if none did.
    """
    count, settings, survivors, before = item.anchor
    sections = view.get("sections") or []
    if len(sections) != count:
        return None
    at = item.location[1]
    if not isinstance(at, int) or not 0 <= at < len(sections):
        return None
    section = sections[at]
    if not isinstance(section, dict):
        return None
    own = {key: value for key, value in section.items() if key != "cards"}
    if own != settings:
        return None
    cards = list(section.get("cards") or [])
    if not survivors:
        return 0 if not cards else None
    # In order, extras allowed: each survivor is found after the last.
    found: list[int] = []
    position = 0
    for wanted in survivors:
        while position < len(cards) and cards[position] != wanted:
            position += 1
        if position == len(cards):
            return None
        found.append(position)
        position += 1
    return found[before - 1] + 1 if before else found[0]


def _anchor_holds(view: dict, item: RemovedItem) -> bool:
    """Whether the section at that index is still the one the card left."""
    return item.anchor is None or _anchored_index(view, item) is not None


def _section_gap_holds(view: dict, item: RemovedItem) -> bool:
    """Whether the gap this section left is still the only one it fits.

    True exactly when today's sections are the ones that stood beside it,
    in their order. Then the run is one short at `item.index` and there is
    no second place it could belong to.

    Compared with `==` on the sections themselves, which is why the item
    carries them rather than a digest of them: this module has no runtime
    import of `analyze` (see the note at the top) and so no fingerprint
    to compare.

    Not over titles, and that is the point. Of the 80 sections on the
    installation this was developed against, 0 carry one - a check
    against titles would pass on a run of `None`s while telling us
    nothing. Strict instead: a card edited in a neighbouring section
    since the deletion is enough to refuse, and the whole-state restore
    is what covers that.
    """
    if item.neighbours is None:
        return False
    return list(view.get("sections") or []) == list(item.neighbours)


def _view_has_gone(views: list, item: RemovedItem) -> bool:
    """Whether the view being put back is really missing from the state.

    A view with a path was reported missing because its path is not
    there, which is an identity and needs no second opinion. A view
    without one was reported missing because the position it was keyed by
    now holds something else - and that happens just as readily when the
    view never moved and a *neighbour* was deleted in front of it.

    So the same proof the undo works from: look for what is supposed to
    have disappeared, byte for byte, in the state as it stands. Found, and
    nothing disappeared. Measured on 2026-09-09, deleting the neighbour of
    an untouched pathless view offered that view back and put a second
    copy of it on the dashboard - the writing twin of case C1-B in the
    review of 2026-09-04, whose package 1 closed the undo path here and
    left this one open.

    The limit, and it is the one package 2 lifts: a pathless view that was
    both shifted and edited is not byte-identical to itself, so this lets
    it through. Nothing short of an identity chain of our own tells that
    apart from a view somebody really deleted.
    """
    if item.view_path is not None:
        return True
    return not any(view == item.payload for view in views)


def reinsert(config: dict, item: RemovedItem) -> dict:
    """Return a new configuration with `item` put back.

    Raises LookupError when the place it belonged to no longer exists —
    guessing a different place would be worse than refusing.
    """
    result = copy.deepcopy(config)
    views = result.setdefault("views", [])

    if _paths_share(result):
        raise LookupError(
            "two views of this dashboard share one URL path, so a path "
            "does not identify a view here and nothing is put back"
        )

    if item.kind == "view":
        if not _view_has_gone(views, item):
            raise LookupError(
                "this view has no URL path and one just like it is on the "
                "dashboard already, so it did not go missing and putting "
                "it back would add a second copy"
            )
        views.insert(min(item.index, len(views)), copy.deepcopy(item.payload))
        return result

    if item.kind == "section":
        view = _find_view(views, item)
        if view is None:
            raise LookupError(
                f"the view this section belonged to no longer exists "
                f"(path={item.view_path!r}, index={item.view_index})"
            )
        if not _section_gap_holds(view, item):
            raise LookupError(
                "the other sections of this view are not the ones this "
                "section stood beside, so there is no telling where it "
                "belongs now"
            )
        # Not `setdefault`: a view written as `sections: null` in YAML
        # arrives as {"sections": None}, and `setdefault` hands the None
        # straight back - the key is there. `card_containers` guards the
        # same shape with `or []`, so it does occur.
        sections = view.get("sections")
        if not isinstance(sections, list):
            sections = []
            view["sections"] = sections
        sections.insert(min(item.index, len(sections)), copy.deepcopy(item.payload))
        return result

    if item.kind != "card":
        # Answered or refused, never approximated. A `location` meant for
        # another kind walks straight into the card branch otherwise:
        # measured on 2026-09-09, `("sections",)` made `_cards_at` return
        # the list of sections, which is a list and therefore no refusal,
        # and the item went in among them with none of its own checks run.
        raise LookupError(
            f"this is an item of a kind restore does not know: {item.kind!r}"
        )

    view = _find_view(views, item)
    if view is None:
        raise LookupError(
            f"the view this card belonged to no longer exists "
            f"(path={item.view_path!r}, index={item.view_index})"
        )

    # Resolved once: `_anchored_index` re-walks the section's survivors,
    # and the answer is both the proof that the section still holds and
    # the index the card goes back to, needed again below.
    anchored = None if item.anchor is None else _anchored_index(view, item)
    if item.anchor is not None and anchored is None:
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

    # A card that sat in a section goes back beside the neighbour it had;
    # the old index is only right while nothing was added in front.
    index = item.index if anchored is None else anchored
    cards.insert(min(index, len(cards)), copy.deepcopy(item.payload))
    return result


def parks(config: dict, item: RemovedItem) -> bool:
    """Whether putting `item` back goes to "Imported cards" (decision 26).

    Only a card, only in a sections view named by a path, and only when
    the section it left can no longer be proven to be the one at that
    index. Everything else is `reinsert`'s to answer - including its
    refusals.
    """
    if item.kind != "card" or item.anchor is None or item.view_path is None:
        return False
    if _paths_share(config):
        return False
    view = _find_view(config.get("views") or [], item)
    if view is None or view.get("type") != "sections":
        return False
    return not _anchor_holds(view, item) or _cards_at(view, item.location) is None


def _require_view(views: list, item: RemovedItem | UndoStep) -> dict:
    """The view `item` belongs to, or a refusal naming it by its label.

    Shared by every function below that starts from a card, badge or
    parked item and needs its view first.
    """
    view = _find_view(views, item)
    if view is None:
        raise LookupError(
            f"the view {item.label} belonged to no longer exists "
            f"(path={item.view_path!r}, index={item.view_index})"
        )
    return view


def _park_for(views: list, item: RemovedItem | UndoStep) -> list:
    """The `cards:` list `item` is parked into, created when the view has
    none - shared by `park` and the parked branch of `apply_undo`, which
    put the same item at the end of the same "Imported cards" list.
    """
    view = _require_view(views, item)
    cards = view.get("cards")
    if cards is None:
        cards = []
        view["cards"] = cards
    elif not isinstance(cards, list):
        raise LookupError(
            f"the view {item.label} belonged to holds something other "
            f"than a card list under cards:, so nothing is parked there"
        )
    return cards


def park(config: dict, item: RemovedItem) -> dict:
    """Return a new configuration with `item` at the end of "Imported cards"."""
    result = copy.deepcopy(config)
    _park_for(result.get("views") or [], item).append(copy.deepcopy(item.payload))
    return result


def _cards_for(views: list, step: UndoStep) -> list:
    """The card list a step points at, or a refusal."""
    view = _require_view(views, step)
    cards = _cards_at(view, step.location)
    if cards is None:
        raise LookupError(
            f"the card list {step.label} belonged to no longer exists "
            f"(location={step.location!r})"
        )
    return cards


def _badges_for(views: list, step: UndoStep) -> list:
    """The badge list a step points at, created when the view has none."""
    view = _require_view(views, step)
    badges = view.get("badges")
    if not isinstance(badges, list):
        badges = []
        view["badges"] = badges
    return badges



def _standing_there(items: list, step: UndoStep) -> None:
    """Refuse unless the expected thing is still at that index."""
    if step.index >= len(items) or items[step.index] != step.expect:
        raise LookupError(
            f"{step.label} is no longer where the undo was planned for it"
        )


_SETTING_KINDS = ("dashboard_setting", "view_setting")


def _same_value(one: Any, other: Any) -> bool:
    """Equal as settings. Not `==`: that says 1 is True and 0 is False.

    The same comparison as `analyze.fingerprint`, written out here for
    the reason at the top of this file.
    """
    return json.dumps(one, sort_keys=True, default=str) == json.dumps(
        other, sort_keys=True, default=str
    )


def _apply_setting(config: dict, views: list, step: UndoStep) -> None:
    """Write one named setting back, if it still holds what was planned.

    The lines that walk a path live here rather than being imported from
    `analyze`, for the reason at the top of this file.
    """
    if step.kind == "dashboard_setting":
        container = config
    else:
        container = _find_view(views, step)
        if container is None:
            raise LookupError(
                f"the view {step.label} belonged to no longer exists "
                f"(path={step.view_path!r}, index={step.view_index})"
            )
    *parents, leaf = step.location
    for key in parents:
        container = container.get(key) if isinstance(container, dict) else None
        if not isinstance(container, dict):
            raise LookupError(f"{step.label} no longer has the block it belonged to")
    present = leaf in container
    if step.expect_absent:
        holds = not present
    else:
        holds = present and _same_value(container[leaf], step.expect)
    if not holds:
        raise LookupError(f"{step.label} is no longer what the undo was planned against")
    if step.action == "unset":
        del container[leaf]
    else:
        container[leaf] = copy.deepcopy(step.payload)


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
    # Remembered so the bookkeeping list below never ends up in a
    # configuration that had no `views:` - a strategy dashboard has none,
    # and an undo of one of its settings must not add an empty list.
    had_views = "views" in result
    views = result.setdefault("views", [])

    if _paths_share(result):
        raise LookupError(
            "two views of this dashboard share one URL path, so a path "
            "does not identify a view here and no step is applied"
        )

    # Settings first: they shift no index, and a pathless view is found
    # by its position, which removing a whole view would move.
    for step in plan.steps:
        if step.kind in _SETTING_KINDS:
            _apply_setting(result, views, step)

    # Cards before views: a card step finds its view by path, but falls
    # back to the index, and removing a view first would move it.
    removals = [step for step in plan.steps if step.action == "remove"]
    for step in sorted(
        (step for step in removals if step.kind in ("card", "badge")), key=lambda s: -s.index
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

    inserts = [step for step in plan.steps if step.action == "insert"]
    for step in sorted((s for s in inserts if not s.parked), key=lambda s: s.index):
        if step.kind == "view":
            views.insert(min(step.index, len(views)), copy.deepcopy(step.payload))
            continue
        cards = _badges_for(views, step) if step.kind == "badge" else _cards_for(views, step)
        # If the list has shrunk since, append rather than fail - the same
        # trade `reinsert` makes, and for the same reason. What this undo
        # proves is that the change's own cards are untouched, never that
        # their neighbourhood is; `equals_state_before` in the caller is
        # what tells the truth about the whole state.
        cards.insert(min(step.index, len(cards)), copy.deepcopy(step.payload))
    # Parked last and appended, never indexed: they go where Home
    # Assistant shows "Imported cards", after anything that has a real
    # index in the same list, so no append shifts an ordinary insert.
    for step in (s for s in inserts if s.parked):
        _park_for(views, step).append(copy.deepcopy(step.payload))
    # An empty list also goes when this undo brought the whole strategy
    # block back: that is the undo of Home Assistant's "take control",
    # which swapped the strategy for views, and the state before it had
    # no `views:`. Only then - a `views: []` that already stood beside a
    # strategy is left alone, or an undo with nothing to do would still
    # find something to write.
    restores_strategy = any(
        step.kind == "dashboard_setting"
        and step.action == "set"
        and tuple(step.location) == ("strategy",)
        for step in plan.steps
    )
    if not views and (not had_views or restores_strategy):
        del result["views"]
    return result
