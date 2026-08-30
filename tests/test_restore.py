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
