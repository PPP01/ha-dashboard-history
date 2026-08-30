"""Tests for change classification.

These are the most important tests in the project: if an edited card were
classified as a deletion, the interface would offer to restore something
that is not missing — and a false alarm destroys trust in exactly the
message people open the tool for.
"""

import analyze


def _config(cards):
    return {"views": [{"path": "home", "title": "Home", "cards": list(cards)}]}


A = {"type": "tile", "entity": "light.a"}
B = {"type": "tile", "entity": "light.b"}
C = {"type": "tile", "entity": "light.c"}


def test_nothing_changed():
    s = analyze.summarize(_config([A, B]), _config([A, B]))
    assert (s.added, s.removed, s.edited, s.moved) == (0, 0, 0, 0)


def test_card_removed_is_found():
    removed = analyze.find_removed(_config([A, B]), _config([A]))
    assert len(removed) == 1
    assert removed[0].kind == "card"
    assert removed[0].payload == B
    assert removed[0].index == 1
    assert removed[0].view_path == "home"


def test_card_added_is_not_a_removal():
    assert analyze.find_removed(_config([A]), _config([A, B])) == []


def test_edited_card_is_not_reported_as_removed():
    edited = dict(A, name="New name")
    assert analyze.find_removed(_config([A, B]), _config([edited, B])) == []
    s = analyze.summarize(_config([A, B]), _config([edited, B]))
    assert (s.edited, s.removed, s.added) == (1, 0, 0)


def test_reordered_cards_are_not_reported_as_removed():
    assert analyze.find_removed(_config([A, B]), _config([B, A])) == []
    s = analyze.summarize(_config([A, B]), _config([B, A]))
    assert s.moved == 2
    assert (s.removed, s.added) == (0, 0)


def test_a_deletion_does_not_report_the_survivors_as_moved():
    # Deleting the first card shifts every card behind it. Reporting those
    # as moved buries the one fact that matters: on a large view it is
    # twenty entries of noise around a single deletion.
    s = analyze.summarize(_config([A, B, C]), _config([B, C]))
    assert (s.removed, s.moved) == (1, 0)


def test_an_insertion_does_not_report_the_survivors_as_moved():
    s = analyze.summarize(_config([B, C]), _config([A, B, C]))
    assert (s.added, s.moved) == (1, 0)


def test_a_card_without_a_name_is_labelled_by_its_content():
    # A markdown card carries neither entity nor title nor name. Three
    # deleted ones would otherwise all read "markdown", and nobody could
    # tell which is which.
    card = {"type": "markdown", "content": "# Solar heute\n\nEin Text."}
    removed = analyze.find_removed(_config([A, card]), _config([A]))
    assert "Solar heute" in removed[0].label


def test_a_long_content_label_is_shortened():
    card = {"type": "markdown", "content": "x" * 200}
    removed = analyze.find_removed(_config([A, card]), _config([A]))
    assert len(removed[0].label) < 80


def test_an_edited_heading_card_is_not_reported_as_removed():
    # 62 of the cards on the installation this was built against are
    # headings, and none of them carry an entity, a title or a name.
    # Reading an edit as a deletion would offer to restore something that
    # is not missing - the one failure that destroys trust in the tool.
    old = {"type": "heading", "heading": "Solar", "icon": "mdi:solar-power"}
    new = {"type": "heading", "heading": "Solar", "icon": "mdi:weather-sunny"}
    assert analyze.find_removed(_config([A, old]), _config([A, new])) == []
    s = analyze.summarize(_config([A, old]), _config([A, new]))
    assert (s.edited, s.removed, s.added) == (1, 0, 0)


def test_an_edited_entities_card_is_not_reported_as_removed():
    old = {"type": "entities", "entities": ["sensor.a", "sensor.b"]}
    new = {"type": "entities", "entities": ["sensor.a", "sensor.b", "sensor.c"]}
    assert analyze.find_removed(_config([A, old]), _config([A, new])) == []


def test_an_edited_wrapper_card_is_not_reported_as_removed():
    inner = {"type": "tile", "entity": "light.z"}
    old = {"type": "vertical-stack", "cards": [inner]}
    new = {"type": "vertical-stack", "cards": [inner, B]}
    assert analyze.find_removed(_config([A, old]), _config([A, new])) == []


def test_an_edited_markdown_card_keeps_its_identity():
    # Its first line is the part that survives an edit of the body.
    old = {"type": "markdown", "content": "# Solar\n\nAlter Text."}
    new = {"type": "markdown", "content": "# Solar\n\nNeuer Text."}
    assert analyze.find_removed(_config([A, old]), _config([A, new])) == []


def test_a_deleted_heading_card_is_still_found():
    # The point is to stop false alarms, not to stop real ones.
    heading = {"type": "heading", "heading": "Solar"}
    removed = analyze.find_removed(_config([A, heading]), _config([A]))
    assert len(removed) == 1
    assert removed[0].payload == heading


def test_a_heading_card_is_labelled_by_its_heading():
    heading = {"type": "heading", "heading": "Solar heute"}
    removed = analyze.find_removed(_config([A, heading]), _config([A]))
    assert "Solar heute" in removed[0].label


def test_a_wrapper_card_is_labelled_by_what_is_inside():
    wrapper = {"type": "vertical-stack", "cards": [{"type": "tile", "entity": "light.z"}, B]}
    removed = analyze.find_removed(_config([A, wrapper]), _config([A]))
    assert "light.z" in removed[0].label


def test_view_removed_is_found():
    old = {"views": [{"path": "home", "cards": [A]}, {"path": "gone", "cards": [B]}]}
    new = {"views": [{"path": "home", "cards": [A]}]}
    removed = analyze.find_removed(old, new)
    assert len(removed) == 1
    assert removed[0].kind == "view"
    assert removed[0].view_path == "gone"


def test_cards_inside_sections_are_covered():
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A, B]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A]}]}]}
    removed = analyze.find_removed(old, new)
    assert len(removed) == 1
    assert removed[0].payload == B
    assert removed[0].location == ("sections", 0, "cards")


def test_several_removals_in_one_save():
    removed = analyze.find_removed(_config([A, B, C]), _config([B]))
    assert {tuple(sorted(item.payload.items())) for item in removed} == {
        tuple(sorted(A.items())), tuple(sorted(C.items()))
    }


def test_removed_item_has_a_readable_label():
    removed = analyze.find_removed(_config([A, B]), _config([A]))
    assert "light.b" in removed[0].label


def test_removed_view_keeps_its_position():
    old = {"views": [{"path": "a", "cards": []}, {"path": "gone", "cards": []},
                     {"path": "c", "cards": []}]}
    new = {"views": [{"path": "a", "cards": []}, {"path": "c", "cards": []}]}
    item = analyze.find_removed(old, new)[0]
    assert item.index == 1 and item.view_index == 1


def test_views_without_a_path_are_handled():
    old = {"views": [{"title": "No path", "cards": [A, B]}]}
    new = {"views": [{"title": "No path", "cards": [A]}]}
    removed = analyze.find_removed(old, new)
    assert len(removed) == 1
    assert removed[0].view_path is None
