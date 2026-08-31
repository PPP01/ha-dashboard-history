"""Tests for change classification.

These are the most important tests in the project: if an edited card were
classified as a deletion, the interface would offer to restore something
that is not missing — and a false alarm destroys trust in exactly the
message people open the tool for.
"""

import json
import os
import pathlib

import analyze

# Point DASHBOARD_HISTORY_REAL_STORAGE at any Home Assistant .storage
# directory to run the real-data checks against your own dashboards.
_STORAGE = pathlib.Path(
    os.environ.get(
        "DASHBOARD_HISTORY_REAL_STORAGE",
        "/path/to/home-assistant/.storage",
    )
)
REAL_DASHBOARDS = sorted(_STORAGE.glob("lovelace.*")) if _STORAGE.is_dir() else []


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


def test_a_metadata_only_commit_does_not_claim_an_outside_change():
    # The cards are identical; the commit exists only because the title or
    # icon was recorded. Calling that "changed outside Home Assistant" is
    # an accusation, and every existing user would get one per dashboard.
    config = _config([A, B])
    assert (
        analyze.change_message("home", config, config, "startup")
        == "home: metadata recorded"
    )


def test_an_outside_change_is_still_named_as_one():
    assert (
        analyze.change_message("home", _config([A, B]), _config([A]), "startup")
        == "home: changed outside Home Assistant"
    )


def test_a_save_is_summarised():
    assert (
        analyze.change_message("home", _config([A, B]), _config([A]), "save")
        == "home: 1 removed"
    )


def test_the_first_recorded_state_says_so():
    assert (
        analyze.change_message("home", None, _config([A]), "startup")
        == "home: first recorded state"
    )


def test_a_save_without_card_changes_says_so():
    config = _config([A])
    assert (
        analyze.change_message("home", config, config, "save")
        == "home: metadata recorded"
    )


def test_a_rename_is_named_in_the_message():
    # "metadata recorded" is true but useless. Somebody scanning the history
    # for the moment a dashboard got its new name should find it there.
    config = _config([A])
    assert (
        analyze.change_message(
            "home", config, config, "reconcile", {"title": "Home"}, {"title": "Kitchen"}
        )
        == 'home: renamed to "Kitchen"'
    )


def test_another_metadata_change_names_the_field():
    config = _config([A])
    assert (
        analyze.change_message(
            "home",
            config,
            config,
            "reconcile",
            {"title": "Home", "icon": "mdi:a"},
            {"title": "Home", "icon": "mdi:b"},
        )
        == "home: icon changed"
    )


def test_metadata_recorded_for_the_first_time_says_just_that():
    config = _config([A])
    assert (
        analyze.change_message("home", config, config, "startup", None, {"title": "Home"})
        == "home: metadata recorded"
    )


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


# -- the plain-language explanation ------------------------------------
#
# The wording lives in analyze.py rather than in the panel on purpose.
# Three times in this project the code was righter than its own report:
# the false alarm "changed outside Home Assistant", the misleading "does
# not exist at", and the caveat that was silently dropped when a
# dashboard was recreated. Wording that can go wrong belongs where
# pytest can reach it.


def test_a_deleted_card_is_explained_by_name():
    result = analyze.explain_change(_config([A, B]), _config([A]))
    assert [group.view for group in result.groups] == ["Home"]
    assert [entry.text for entry in result.groups[0].entries] == [
        "tile: light.b was deleted"
    ]


def test_the_same_deletion_reads_as_a_warning_in_future_tense():
    result = analyze.explain_effect(_config([A, B]), _config([A]))
    assert result.groups[0].entries[0].text == "tile: light.b will be deleted"
    # Nothing to reassure about: something IS deleted here.
    assert result.note == ""


def test_a_restore_says_plainly_that_nothing_is_lost():
    result = analyze.explain_effect(_config([A]), _config([A, B]))
    assert result.groups[0].entries[0].text == "tile: light.b comes back"
    assert result.note == "Nothing on this dashboard is deleted."


def test_an_edited_card_is_one_event_not_two():
    edited = dict(B, name="Kitchen light")
    result = analyze.explain_change(_config([A, B]), _config([A, edited]))
    assert [entry.kind for entry in result.groups[0].entries] == ["edited"]
    assert result.groups[0].entries[0].text == "tile: Kitchen light was changed"


def test_a_swap_is_explained_as_two_moves():
    result = analyze.explain_change(_config([A, B]), _config([B, A]))
    assert sorted(entry.kind for entry in result.groups[0].entries) == [
        "moved",
        "moved",
    ]


def test_a_deletion_alone_moves_nothing():
    # The same rule _moved already follows: rank among the survivors, not
    # raw position. Otherwise every card behind a deletion is noise.
    result = analyze.explain_change(_config([A, B, C]), _config([A, C]))
    assert [entry.kind for entry in result.groups[0].entries] == ["removed"]


def test_a_whole_deleted_view_is_one_line_and_not_hundreds():
    old = {"views": [{"path": "home", "title": "Home", "cards": [A, B, C]}]}
    result = analyze.explain_change(old, {"views": []})
    assert [entry.text for entry in result.groups[0].entries] == [
        'the whole view "Home" was deleted'
    ]


def test_a_recreated_dashboard_is_one_line_per_view():
    # The heaviest case: a dashboard restored from nothing. Listing every
    # card would be hundreds of lines - on the installation this was built
    # against, 661 of them.
    target = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A, B]},
            {"path": "up", "title": "Upstairs", "cards": [C]},
        ]
    }
    result = analyze.explain_effect({}, target)
    assert [group.view for group in result.groups] == ["Home", "Upstairs"]
    assert [len(group.entries) for group in result.groups] == [1, 1]
    assert result.note == "Nothing on this dashboard is deleted."


def test_a_long_list_is_capped_and_says_how_much_it_hides():
    cards = [{"type": "tile", "entity": f"light.n{index}"} for index in range(20)]
    result = analyze.explain_effect(_config([]), _config(cards))
    assert len(result.groups[0].entries) == 12
    assert result.groups[0].more == 8


def test_an_unnameable_change_never_claims_that_nothing_changed():
    # A renamed view: the cards match exactly, so there is nothing to
    # name. The summary sits directly above a diff that plainly shows the
    # difference - claiming "nothing changed" there would be refuted at a
    # glance, which is worse than having no summary at all.
    old = {"views": [{"path": "home", "title": "Home", "cards": [A]}]}
    new = {"views": [{"path": "home", "title": "Warm", "cards": [A]}]}
    result = analyze.explain_change(old, new)
    assert result.groups == []
    assert "see the details" in result.note


def test_two_views_are_two_groups():
    old = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A, B]},
            {"path": "up", "title": "Upstairs", "cards": [C]},
        ]
    }
    new = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A]},
            {"path": "up", "title": "Upstairs", "cards": []},
        ]
    }
    result = analyze.explain_change(old, new)
    assert [group.view for group in result.groups] == ["Home", "Upstairs"]
    assert [len(group.entries) for group in result.groups] == [1, 1]


def test_a_view_without_a_title_is_named_by_its_path():
    old = {"views": [{"path": "garage", "cards": [A, B]}]}
    new = {"views": [{"path": "garage", "cards": [A]}]}
    result = analyze.explain_change(old, new)
    assert result.groups[0].view == "garage"


def test_a_card_in_a_section_is_explained_too():
    # The sections layout, which is what Home Assistant creates by default
    # for a new dashboard now.
    old = {
        "views": [
            {"path": "home", "title": "Home", "sections": [{"cards": [A, B]}]}
        ]
    }
    new = {"views": [{"path": "home", "title": "Home", "sections": [{"cards": [A]}]}]}
    result = analyze.explain_change(old, new)
    assert [entry.text for entry in result.groups[0].entries] == [
        "tile: light.b was deleted"
    ]


def _without_first_card(config):
    """The same configuration with the first card of each view removed."""
    import copy

    shrunk = copy.deepcopy(config)
    for view in shrunk.get("views") or []:
        for _, cards in analyze.card_containers(view):
            if cards:
                del cards[0]
                break
    return shrunk


def test_every_real_card_can_be_named():
    # The formulations have to hang on real cards, not on the four
    # invented ones above - none of which has a nested container, a
    # missing title or an entity list. Comparing a real configuration
    # against itself minus one card per view is what forces the wording
    # through the card path; explain_effect({}, config) would not, because
    # it folds each view into a single line.
    if not REAL_DASHBOARDS:
        return
    named = 0
    for path in REAL_DASHBOARDS:
        config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        if not (config.get("views") or []):
            continue
        result = analyze.explain_change(config, _without_first_card(config))
        for group in result.groups:
            assert group.view.strip(), f"a view without a name in {path.name}"
            for entry in group.entries:
                assert entry.text.strip(), f"an empty sentence in {path.name}"
                assert entry.kind in ("removed", "added", "edited", "moved")
                assert entry.what in ("card", "view")
                # The label is what makes this worth reading at all. An
                # empty one would produce " was deleted" and tell nobody
                # which card is gone.
                assert entry.label.strip(), f"an unnamed card in {path.name}"
                named += 1
    assert named, "the real dashboards produced no explanation at all"


def test_a_real_dashboard_restored_from_nothing_stays_readable():
    # The heaviest case on real data: 661 cards on this installation, and
    # the summary still has to fit on a screen.
    if not REAL_DASHBOARDS:
        return
    for path in REAL_DASHBOARDS:
        config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        result = analyze.explain_effect({}, config)
        for group in result.groups:
            assert len(group.entries) <= 12
        assert result.note == "Nothing on this dashboard is deleted." or not result.groups
