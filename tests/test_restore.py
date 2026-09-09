"""Tests for putting removed items back."""

import analyze
import pytest
import restore

A = {"type": "tile", "entity": "light.a"}
B = {"type": "tile", "entity": "light.b"}
C = {"type": "tile", "entity": "light.c"}


def _config(cards):
    return {"views": [{"path": "home", "title": "Home", "cards": list(cards)}]}


def test_card_goes_back_to_its_old_position():
    item = analyze.find_removed(_config([A, B, C]), _config([A, C]))[0]
    result = restore.reinsert(_config([A, C]), item)
    assert result["views"][0]["cards"] == [A, B, C]


def test_card_is_appended_when_the_view_has_shrunk():
    item = analyze.find_removed(_config([A, B, C]), _config([A]))
    removed_c = next(i for i in item if i.payload == C)
    result = restore.reinsert(_config([A]), removed_c)
    assert result["views"][0]["cards"] == [A, C]


def test_the_input_is_not_modified():
    original = _config([A, C])
    item = analyze.find_removed(_config([A, B, C]), original)[0]
    restore.reinsert(original, item)
    assert original["views"][0]["cards"] == [A, C]


def test_a_removed_view_comes_back():
    old = {"views": [{"path": "home", "cards": [A]}, {"path": "gone", "cards": [B]}]}
    new = {"views": [{"path": "home", "cards": [A]}]}
    item = analyze.find_removed(old, new)[0]
    result = restore.reinsert(new, item)
    assert [v["path"] for v in result["views"]] == ["home", "gone"]


def test_a_card_inside_a_section_comes_back():
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A, B]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A]}]}]}
    item = analyze.find_removed(old, new)[0]
    result = restore.reinsert(new, item)
    assert result["views"][0]["sections"][0]["cards"] == [A, B]


def test_a_vanished_target_view_is_refused_loudly():
    item = analyze.find_removed(_config([A, B]), _config([A]))[0]
    with pytest.raises(LookupError):
        restore.reinsert({"views": []}, item)


def test_an_edited_card_lands_back_on_the_right_card():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    plan = analyze.plan_undo(_config([old, B]), _config([new, B]), _config([new, B]))
    result = restore.apply_undo(_config([new, B]), plan)
    assert result["views"][0]["cards"] == [old, B]


def test_two_removals_in_one_list_do_not_shift_each_other():
    plan = analyze.plan_undo(_config([A]), _config([A, B, C]), _config([A, B, C]))
    result = restore.apply_undo(_config([A, B, C]), plan)
    assert result["views"][0]["cards"] == [A]


def test_a_move_comes_back_exactly_once():
    before = {"views": [{"path": "a", "cards": [A, B]}, {"path": "b", "cards": []}]}
    after = {"views": [{"path": "a", "cards": [A]}, {"path": "b", "cards": [B]}]}
    plan = analyze.plan_undo(before, after, after)
    result = restore.apply_undo(after, plan)
    assert result["views"][0]["cards"] == [A, B]
    assert result["views"][1]["cards"] == []


def test_the_input_is_not_modified_by_an_undo():
    original = _config([A, B])
    plan = analyze.plan_undo(_config([A]), original, original)
    restore.apply_undo(original, plan)
    assert original == _config([A, B])


def test_a_card_that_moved_away_since_is_refused():
    """The plan is made against one state and applied to another."""
    plan = analyze.plan_undo(_config([A]), _config([A, B]), _config([A, B]))
    with pytest.raises(LookupError, match="no longer where"):
        restore.apply_undo(_config([B, A]), plan)


def test_a_blocked_plan_refuses_loudly():
    plan = analyze.UndoPlan(blocked="nope")
    with pytest.raises(LookupError, match="nope"):
        restore.apply_undo(_config([A]), plan)


def test_two_cards_edited_and_swapped_come_back_in_order():
    """Both are edited, and they traded places in the same save.

    Written back in place this produces the two cards in the wrong
    order, and nothing refuses: each card really is standing where the
    plan expects it - the expectation just says nothing about where it
    belongs.
    """
    old0 = {"type": "tile", "entity": "light.a", "name": "Bett"}
    old1 = {"type": "tile", "entity": "light.b", "name": "Tisch"}
    new0 = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    new1 = {"type": "tile", "entity": "light.b", "name": "Tischlampe"}
    plan = analyze.plan_undo(
        _config([old0, old1]), _config([new1, new0]), _config([new1, new0])
    )
    result = restore.apply_undo(_config([new1, new0]), plan)
    assert result["views"][0]["cards"] == [old0, old1]


def test_an_edit_and_a_move_in_one_save_both_land():
    """One card edited, another moved past it - the two paths together."""
    x = {"type": "gauge", "entity": "sensor.x", "min": 0}
    edited = {"type": "gauge", "entity": "sensor.x", "min": 5}
    before = _config([A, B, x])
    after = _config([edited, B, A])
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    result = restore.apply_undo(after, plan)
    assert result["views"][0]["cards"] == [A, B, x]


# -- a section index is not a section ----------------------------------
#
# Measured on 2026-09-04: putting a card back walked ("sections", i,
# "cards") in whatever state it was handed. Where that index pointed at
# an existing but different section, the card was filed there without a
# word - the loud LookupError only appeared when the index ran off the
# end. The quiet outcome is the dangerous one.


def _sections(*sections):
    return {"views": [{"path": "home", "type": "sections",
                       "sections": [dict(s) for s in sections]}]}


def test_a_card_refuses_to_go_back_into_a_different_section():
    """Its section went away after the card did, so index 1 means another.

    The card is what disappeared between `old` and `new` - one card, no
    section - and the state it would be written into is a third one, in
    which "Oben" has since been removed. That is the shape `reinsert`
    meets in practice: a plan made against one state, applied to a later
    one.
    """
    old = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B, C]})
    new = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == C)
    today = _sections({"title": "Unten", "cards": [B]})
    with pytest.raises(LookupError, match="section"):
        restore.reinsert(today, item)


def test_a_card_refuses_when_a_section_was_pushed_along():
    """A section inserted in front moves "Unten" from index 1 to 2."""
    old = _sections({"title": "Oben", "cards": [A]}, {"title": "Unten", "cards": [B, C]})
    new = _sections({"title": "Neu", "cards": []},
                    {"title": "Oben", "cards": [A]},
                    {"title": "Unten", "cards": [B]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == C)
    with pytest.raises(LookupError, match="section"):
        restore.reinsert(new, item)


def test_a_card_goes_back_into_the_section_it_came_from():
    """The everyday case: the section is still standing where it was."""
    old = _sections({"title": "Oben", "cards": [A, B]})
    new = _sections({"title": "Oben", "cards": [A]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    result = restore.reinsert(new, item)
    assert result["views"][0]["sections"][0]["cards"] == [A, B]


# A view without a URL path is keyed by its position, and a position is
# an address rather than an identity. Package 1 of the 2026-09-04 review
# closed that on the undo path (`analyze._positions_lie`) and for cards
# on the writing path (`_anchor_holds`), but a view arriving here carried
# no check at all - measured on 2026-09-09: deleting the neighbour of an
# untouched pathless view offered that view back and added a second copy
# of it.


def _views(*views):
    return {"views": [dict(view) for view in views]}


HOME = {"title": "Home", "cards": [C]}


def test_a_pathless_view_that_is_still_there_refuses_to_be_added_again():
    """Deleting `b` shifts "Home" from position 2 to 1.

    "Home" was never touched. Its old key ("#", 2) is absent from the new
    state, so it is offered back - and putting it back would leave the
    dashboard holding it twice.
    """
    old = _views({"path": "a", "cards": [A]}, {"path": "b", "cards": [B]}, HOME)
    new = _views({"path": "a", "cards": [A]}, HOME)
    item = next(i for i in analyze.find_removed(old, new) if i.payload == HOME)
    with pytest.raises(LookupError, match="URL path"):
        restore.reinsert(new, item)


def test_a_pathless_view_that_really_went_is_still_put_back():
    """The control case, and the reason this is not a blanket refusal.

    "Home" is gone from the new state, and nothing that looks like it is
    left - so it is missing, and additive is exactly the right shape.
    """
    old = _views({"path": "a", "cards": [A]}, HOME)
    new = _views({"path": "a", "cards": [A]})
    item = next(i for i in analyze.find_removed(old, new) if i.payload == HOME)
    result = restore.reinsert(new, item)
    assert [view.get("title") for view in result["views"]] == [None, "Home"]


def test_a_card_refuses_to_go_back_when_two_views_share_a_path():
    """With a path naming two views, there is no telling which is meant."""
    old = {
        "views": [
            {"path": "x", "title": "One", "cards": [A, B]},
            {"path": "x", "title": "Two", "cards": [C]},
        ]
    }
    new = {
        "views": [
            {"path": "x", "title": "One", "cards": [A]},
            {"path": "x", "title": "Two", "cards": [C]},
        ]
    }
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    with pytest.raises(LookupError, match="share one URL path"):
        restore.reinsert(new, item)


def test_a_doubled_path_stops_a_card_that_has_nothing_to_do_with_it():
    """Deliberately coarse, the way `_positions_lie` is coarse.

    The card belongs to "safe", whose path is unique, and it could be
    filed without any ambiguity. It is still refused: one doubled path
    means a path is not an identity on this dashboard, and the addresses
    every item here carries are paths. Refusing too often is the right
    error to make.
    """
    old = {
        "views": [
            {"path": "safe", "cards": [A, B]},
            {"path": "x", "cards": [C]},
        ]
    }
    new = {
        "views": [
            {"path": "safe", "cards": [A]},
            {"path": "x", "cards": [C]},
        ]
    }
    item = next(i for i in analyze.find_removed(old, new) if i.payload == B)
    today = {
        "views": [
            {"path": "safe", "cards": [A]},
            {"path": "x", "cards": [C]},
            {"path": "x", "cards": []},
        ]
    }
    with pytest.raises(LookupError, match="does not identify a view"):
        restore.reinsert(today, item)


def test_reinsert_refuses_an_item_of_a_kind_it_does_not_know():
    """A kind it has no branch for must not fall into another one.

    Measured on 2026-09-09: `location=("sections",)` walked into the card
    branch, where `_cards_at` returned `view["sections"]` - a list, so no
    refusal at all - and the item was inserted among the sections with
    none of the checks that belong to it. A kind is answered or refused,
    never approximated.
    """
    from analyze import RemovedItem

    config = {"views": [{"path": "home", "sections": [{"cards": [A]}]}]}
    item = RemovedItem(
        kind="something-else",
        view_path="home",
        view_index=0,
        location=("sections",),
        index=0,
        payload={"cards": []},
        label="whatever",
    )
    with pytest.raises(LookupError, match="does not know"):
        restore.reinsert(config, item)


def test_a_deleted_section_goes_back_into_its_gap():
    """The everyday case: deleted, then wanted back, nothing else touched."""
    first = {"title": None, "cards": [A, B]}
    second = {"title": None, "cards": [C]}
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(first), dict(second)]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(second)]}]}
    item = next(i for i in analyze.find_removed(old, new) if i.kind == "section")

    result = restore.reinsert(new, item)

    assert result["views"][0]["sections"] == [first, second]


def test_a_deleted_section_refuses_when_a_neighbour_changed_since():
    """Then the gap is no longer the only place it could go.

    Strict on purpose: without titles - and 0 of 80 sections on the real
    installation have one - the run of sections carries no identity, so
    "unchanged neighbours" is the whole proof there is.
    """
    first = {"title": None, "cards": [A, B]}
    second = {"title": None, "cards": [C]}
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(first), dict(second)]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(second)]}]}
    item = next(i for i in analyze.find_removed(old, new) if i.kind == "section")
    # A card added to the surviving section after the deletion.
    today = {"views": [{"path": "home", "type": "sections",
                        "sections": [{"title": None, "cards": [C, A]}]}]}

    with pytest.raises(LookupError, match="stood beside"):
        restore.reinsert(today, item)


def test_putting_a_section_back_leaves_the_input_alone():
    """The caller still needs the old state to render a preview against."""
    first = {"title": None, "cards": [A]}
    second = {"title": None, "cards": [C]}
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(first), dict(second)]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [dict(second)]}]}
    item = next(i for i in analyze.find_removed(old, new) if i.kind == "section")

    restore.reinsert(new, item)

    assert new["views"][0]["sections"] == [second]


def test_an_undo_refuses_to_write_into_a_doubled_path():
    """The plan was made against a state that had one path per view.

    `plan_undo` stops this case since the guard on the reading side, but
    the plan travels: made against one state, applied to a later one. It
    is the later one that decides where the write lands, so the writing
    side asks again.
    """
    old = {"views": [{"path": "x", "title": "One", "cards": [A]}]}
    new = {"views": [{"path": "x", "title": "One", "cards": [A, B]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None, "the plan itself has to be sound for this test"
    today = {
        "views": [
            {"path": "x", "title": "One", "cards": [A, B]},
            {"path": "x", "title": "Another that appeared since", "cards": []},
        ]
    }
    with pytest.raises(LookupError, match="share one URL path"):
        restore.apply_undo(today, plan)
