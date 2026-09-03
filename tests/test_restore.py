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
