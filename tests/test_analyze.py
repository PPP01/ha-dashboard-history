"""Tests for change classification.

These are the most important tests in the project: if an edited card were
classified as a deletion, the interface would offer to restore something
that is not missing — and a false alarm destroys trust in exactly the
message people open the tool for.
"""

import json
import os
import pathlib

import pytest

import analyze

# Set DASHBOARD_HISTORY_REAL_STORAGE to a Home Assistant .storage
# directory to run the real-data checks against your own dashboards.
# No default path: a personal one in a public repository says something
# about a machine and nothing about this project. conftest.py also reads
# tests/.real-storage, which git ignores.
_STORAGE = os.environ.get("DASHBOARD_HISTORY_REAL_STORAGE", "")
REAL_DASHBOARDS = sorted(pathlib.Path(_STORAGE).glob("lovelace.*")) if _STORAGE else []


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
    assert removed[0].view_title == "Home"


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


def test_a_message_says_whether_the_change_added_something():
    # The panel needs this to know that offering a plain put-back would
    # be a trap: put the removed card back and the added one is still
    # there, so the dashboard ends up with both. It used to read the
    # message with a regular expression of its own, which is logic in
    # the panel and is forbidden; this is the same question asked where
    # the wording is written.
    assert analyze.message_adds("home: 3 added")
    assert analyze.message_adds("home: 2 removed, 3 added")
    assert analyze.message_adds("home: 2 removed, 3 added, 1 moved")
    assert not analyze.message_adds("home: 2 removed")
    assert not analyze.message_adds("home: 1 edited, 2 moved")
    assert not analyze.message_adds("home: no card changes")
    assert not analyze.message_adds("home: first recorded state")
    assert not analyze.message_adds("home: changed outside Home Assistant")


def test_a_view_that_appeared_counts_as_an_addition():
    # The panel's regular expression looked for a number followed
    # straight by "added" and so missed "2 views added" - the word in
    # between. A view that appeared is as much a thing a put-back leaves
    # standing as a card that did.
    old = {"views": [{"path": "home", "cards": [A]}]}
    new = {"views": [{"path": "home", "cards": [A]}, {"path": "new", "cards": [B]}]}
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 view added"
    assert analyze.message_adds("dash: 1 view added")
    assert analyze.message_adds("dash: 2 views added")
    assert not analyze.message_adds("dash: 2 views removed")


def test_a_dashboard_named_like_a_count_does_not_fake_an_addition():
    # The live false positive, and the reason this is read as a shape
    # rather than searched for as a substring. Rename a dashboard to
    # "3 added" and every message about it carries those words, on
    # changes that touched no card at all.
    config = _config([A])
    renamed = analyze.change_message(
        "home", config, config, "reconcile", {"title": "Home"}, {"title": "3 added"}
    )
    assert renamed == 'home: renamed to "3 added"'
    assert not analyze.message_adds(renamed)
    assert not analyze.message_adds("3 added: metadata recorded")
    assert not analyze.message_adds("3 added: first recorded state")
    # And the same dashboard really adding a card still says so.
    assert analyze.message_adds("3 added: 1 added")


def test_a_dashboard_whose_name_holds_a_colon_still_reads():
    # "Home: ground floor" is a title somebody will write, and it puts a
    # second ": " in front of the counts. The lead-in is peeled off one
    # at a time until what is left is nothing but counts.
    assert analyze.message_adds("Home: ground floor: 1 added")
    assert not analyze.message_adds("Home: ground floor: 1 removed")
    assert not analyze.message_adds("Home: ground floor: icon, title changed")


def test_view_removed_is_found():
    old = {"views": [{"path": "home", "cards": [A]}, {"path": "gone", "cards": [B]}]}
    new = {"views": [{"path": "home", "cards": [A]}]}
    removed = analyze.find_removed(old, new)
    assert len(removed) == 1
    assert removed[0].kind == "view"
    assert removed[0].view_path == "gone"
    # No title on the removed view - `view_title` falls back to its path,
    # the same order `_view_name` tries them in.
    assert removed[0].view_title == "gone"


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


def test_removed_items_carry_their_views_title_for_grouping():
    # A view's title, not its path, is what the diff above a put-back
    # list already heads its own groups with (`_view_name`) - two cards
    # gone from two differently-titled views must come back naming those
    # titles, not the slugs a caller would otherwise have to look up
    # again to group these items the same way.
    old = {
        "views": [
            {"path": "erste", "title": "Erste Ansicht", "cards": [A]},
            {"path": "zweite", "title": "Zweite Ansicht", "cards": [B]},
        ]
    }
    new = {
        "views": [
            {"path": "erste", "title": "Erste Ansicht", "cards": []},
            {"path": "zweite", "title": "Zweite Ansicht", "cards": []},
        ]
    }
    removed = analyze.find_removed(old, new)
    titles = {item.payload["entity"]: item.view_title for item in removed}
    assert titles == {"light.a": "Erste Ansicht", "light.b": "Zweite Ansicht"}


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
    # `view_title` is what a caller groups removed items by - it must not
    # go missing along with the path, or a pathless view's items would be
    # ungroupable.
    assert removed[0].view_title == "No path"


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
    # A section setting: the cards match exactly, and a section has no
    # name to address a setting by (GitHub #28 leaves sections out on
    # purpose). The summary sits directly above a diff that plainly shows
    # the difference - claiming "nothing changed" there would be refuted
    # at a glance, which is worse than having no summary at all.
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "cards": [A]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"type": "grid", "column_span": 2, "cards": [A]}]}]}
    result = analyze.explain_change(old, new)
    assert result.groups == []
    assert "see the details" in result.note


def test_a_view_converted_to_sections_is_explained_as_its_own_event():
    """The conversion itself is the event - not the section list it produces.

    Converting a view leaves its existing cards exactly where match_cards
    still finds them, so nothing about the cards looks unusual - but the
    layout itself changed, and `type` is not a card. Unnamed, this used
    to fall into the same bucket as the rename above: no groups at all.
    GitHub #32.
    """
    old = {"views": [{"path": "home", "title": "Home", "cards": [A]}]}
    new = {
        "views": [
            {
                "path": "home",
                "title": "Home",
                "type": "sections",
                "cards": [A],
                "sections": [{"type": "grid", "cards": []}],
            }
        ]
    }
    result = analyze.explain_change(old, new)
    assert [entry.text for group in result.groups for entry in group.entries] == [
        'the view "Home" was converted from masonry to sections'
    ]


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
        pytest.skip("set DASHBOARD_HISTORY_REAL_STORAGE to run this")
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
        pytest.skip("set DASHBOARD_HISTORY_REAL_STORAGE to run this")
    for path in REAL_DASHBOARDS:
        config = json.loads(path.read_text(encoding="utf-8"))["data"]["config"]
        result = analyze.explain_effect({}, config)
        for group in result.groups:
            assert len(group.entries) <= 12
        assert result.note == "Nothing on this dashboard is deleted." or not result.groups


def test_a_card_moved_into_a_new_section_is_not_a_deletion_at_all():
    # Corrected twice, and the sequence is the point. summarize first
    # walked the old state's containers and looked each up in the new
    # one, so a section added in the new state was never visited and its
    # cards never counted: moving a card into a new section read as a
    # bare deletion. Counting the new container's cards as added made
    # that "1 removed, 1 added" - half a truth, and this test pinned the
    # half. Matching crosses container boundaries now, so the whole
    # truth is available: nothing deleted, nothing added, one card moved,
    # and nothing offered back that is still on the dashboard.
    old = {"views": [{"path": "home", "title": "Home", "cards": [A, B]}]}
    new = {
        "views": [
            {"path": "home", "title": "Home", "cards": [A], "sections": [{"cards": [B]}]}
        ]
    }
    counts = analyze.summarize(old, new)
    assert (counts.removed, counts.added, counts.moved) == (0, 0, 1)
    assert analyze.find_removed(old, new) == []


# --------------------------------------------------------------- moving
#
# A card that moved is not missing, and offering it back puts a second
# copy on the dashboard. Matching used to run inside one container only -
# one card list of one view - so every card that crossed a container
# boundary was unmatched on both sides at once: gone from the old place,
# new in the other. The row read "1 removed, 1 added" and the interface
# offered a restore that duplicates.

_VIEW_A = {"path": "a", "title": "A"}
_VIEW_B = {"path": "b", "title": "B"}


def _two_views(a_cards, b_cards):
    return {
        "views": [
            {**_VIEW_A, "cards": list(a_cards)},
            {**_VIEW_B, "cards": list(b_cards)},
        ]
    }


def test_a_card_moved_to_another_view_is_not_offered_back():
    old = _two_views([A, B], [C])
    new = _two_views([A], [C, B])
    assert analyze.find_removed(old, new) == []


def test_a_card_moved_to_another_view_counts_as_moved():
    counts = analyze.summarize(_two_views([A, B], [C]), _two_views([A], [C, B]))
    assert (counts.added, counts.removed, counts.moved) == (0, 0, 1)


def test_a_card_moved_between_sections_is_not_offered_back():
    old = {"views": [{"path": "home", "sections": [{"cards": [A, B]}, {"cards": [C]}]}]}
    new = {"views": [{"path": "home", "sections": [{"cards": [A]}, {"cards": [C, B]}]}]}
    assert analyze.find_removed(old, new) == []


def test_a_real_deletion_survives_an_identical_card_elsewhere():
    # The trap the staging exists for. B is deleted from view A while an
    # identical B sits untouched in view B. Pairing across places before
    # pairing in place would marry the deleted card to the untouched one
    # and swallow the deletion whole.
    old = _two_views([A, B], [B])
    new = _two_views([A], [B])
    found = analyze.find_removed(old, new)
    assert [item.payload for item in found] == [B]
    assert found[0].view_path == "a"


def test_two_identical_cards_with_one_deleted_is_one_deletion():
    assert len(analyze.find_removed(_config([A, B, B]), _config([A, B]))) == 1


# ------------------------------------------------- the ambiguous twin
#
# Two cards of the same type and entity: the first is deleted, the second
# edited. Pass two took the *first* weak match, which married the deleted
# card to the survivor and then declared the survivor deleted - offering
# back a card that is still on the dashboard, while the one really gone
# was never offered at all. Measured: the survivor differs from its own
# old form in one field of four (0.75), from the deleted card in three of
# five (0.40), so pairing by best similarity settles it.

_GONE = {"type": "tile", "entity": "light.a", "icon": "mdi:one", "name": "One"}
_BLUE = {"type": "tile", "entity": "light.a", "color": "blue", "name": "Two"}
_GREEN = {"type": "tile", "entity": "light.a", "color": "green", "name": "Two"}


def test_the_deleted_twin_is_offered_not_the_edited_one():
    found = analyze.find_removed(_config([_GONE, _BLUE]), _config([_GREEN]))
    assert [item.payload for item in found] == [_GONE]


def test_the_edited_twin_is_reported_as_edited():
    counts = analyze.summarize(_config([_GONE, _BLUE]), _config([_GREEN]))
    assert (counts.removed, counts.added, counts.edited) == (1, 0, 1)


# ----------------------------------------------------- the named limits
#
# Both of these are known gaps, pinned as tests rather than left as
# prose. A limit nobody wrote down is a limit that moves silently.

_KEYLESS = {"type": "custom:apexcharts-card", "graph_span": "24h"}


def test_a_card_with_nothing_to_recognise_it_by_still_reads_as_two_changes():
    # Measured on the installation this was built against: 27 of 484
    # cards carry no entity, title, name, heading, entity list, text or
    # nameable inner card. Editing one is indistinguishable from
    # deleting it and adding another, in the data itself.
    counts = analyze.summarize(_config([_KEYLESS]), _config([dict(_KEYLESS, graph_span="48h")]))
    assert (counts.removed, counts.added) == (1, 1)


def test_a_card_moved_and_edited_at_once_still_reads_as_two_changes():
    # Exact matching crosses container boundaries, weak matching does
    # not. A card that moved *and* changed is therefore matched by
    # neither. Deliberate: weak matching across views would risk the
    # opposite error, and the same entity on two views is ordinary.
    old = _two_views([A, B], [C])
    new = _two_views([A], [C, dict(B, name="renamed")])
    counts = analyze.summarize(old, new)
    assert (counts.removed, counts.added) == (1, 1)


# ------------------------------------------------------- saying where
def test_a_moved_card_says_which_view_it_went_to():
    words = analyze.explain_change(_two_views([A, B], [C]), _two_views([A], [C, B]))
    said = [entry.text for group in words.groups for entry in group.entries]
    assert said == ['tile: light.b was moved to "B"']


def test_a_card_moved_into_a_named_section_says_its_name():
    heading = {"type": "heading", "heading": "Heizung"}
    old = {"views": [{"path": "home", "title": "Home",
                      "sections": [{"cards": [A, B]}, {"cards": [heading]}]}]}
    new = {"views": [{"path": "home", "title": "Home",
                      "sections": [{"cards": [A]}, {"cards": [heading, B]}]}]}
    words = analyze.explain_change(old, new)
    said = [entry.text for group in words.groups for entry in group.entries]
    assert said == ['tile: light.b was moved to the section "Heizung"']


def test_a_card_moved_out_of_a_section_names_imported_cards():
    """Where Home Assistant shows it, in its own words (decision 26)."""
    old = {"views": [{"path": "home", "type": "sections", "cards": [],
                      "sections": [{"cards": [A, B]}]}]}
    new = {"views": [{"path": "home", "type": "sections", "cards": [A],
                      "sections": [{"cards": [B]}]}]}
    texts = [e.text for g in analyze.explain_change(old, new).groups for e in g.entries]
    assert texts == ['tile: light.a was moved to the "Imported cards" area']


# ---------------------------------------------------------- planning an undo
def test_an_edited_card_can_be_taken_back():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    plan = analyze.plan_undo(_config([old]), _config([new]), _config([new]))
    assert plan.blocked is None
    assert [(s.action, s.expect, s.payload) for s in plan.steps] == [
        ("remove", new, None),
        ("insert", None, old),
    ]


def test_a_card_edited_twice_is_refused():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    once = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    twice = {"type": "tile", "entity": "light.a", "name": "Nachttisch"}
    plan = analyze.plan_undo(_config([old]), _config([once]), _config([twice]))
    assert plan.steps == ()
    assert "changed again after this" in plan.blocked
    # Named the way the tool names cards everywhere else - `_describe`
    # prefers the card's own name over its entity, so this reads
    # "tile: Bettlampe", not "tile: light.a".
    assert "Bettlampe" in plan.blocked


def test_two_identical_candidates_are_refused():
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    plan = analyze.plan_undo(_config([old]), _config([new]), _config([new, new]))
    assert plan.steps == ()
    assert "cannot tell them apart" in plan.blocked


def test_a_deleted_card_is_planned_back_at_its_old_place():
    a = {"type": "tile", "entity": "light.a"}
    b = {"type": "tile", "entity": "light.b"}
    plan = analyze.plan_undo(_config([a, b]), _config([a]), _config([a]))
    assert [(s.action, s.index, s.payload) for s in plan.steps] == [("insert", 1, b)]


def test_a_deleted_card_already_back_needs_no_step():
    a = {"type": "tile", "entity": "light.a"}
    b = {"type": "tile", "entity": "light.b"}
    plan = analyze.plan_undo(_config([a, b]), _config([a]), _config([a, b]))
    assert plan.blocked is None
    assert plan.steps == ()


def test_a_deleted_card_with_an_untouched_copy_elsewhere_is_put_back():
    """GitHub #35: the copy on "b" never left, so it is not this one back."""
    old = {"views": [{"path": "a", "cards": [A]}, {"path": "b", "cards": [A]}]}
    new = {"views": [{"path": "a", "cards": []}, {"path": "b", "cards": [A]}]}
    plan = analyze.plan_undo(old, new, new)
    assert [(s.action, s.view_path) for s in plan.steps] == [("insert", "a")]


def test_a_card_copy_added_elsewhere_since_is_not_the_deleted_one_back():
    old = {"views": [{"path": "a", "cards": [A]}, {"path": "c", "cards": []}]}
    new = {"views": [{"path": "a", "cards": []}, {"path": "c", "cards": []}]}
    current = {"views": [{"path": "a", "cards": []}, {"path": "c", "cards": [A]}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("insert", "a")]


def test_one_card_back_of_two_deleted_refuses():
    old = {"views": [{"path": "a", "cards": [A, B, A]}]}
    new = {"views": [{"path": "a", "cards": [B]}]}
    current = {"views": [{"path": "a", "cards": [B, A]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == (
        "only some of the copies of tile: light.a this change deleted are "
        "back, so an exact undo cannot tell which are missing"
    )


def test_two_cards_deleted_and_both_back_is_nothing_to_do():
    old = {"views": [{"path": "a", "cards": [A, A]}]}
    new = {"views": [{"path": "a", "cards": []}]}
    current = {"views": [{"path": "a", "cards": [A, A]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked is None and plan.steps == ()


def test_a_card_back_in_one_view_does_not_count_for_another():
    """Deleted from "a" and "b", added back only on "a"."""
    old = {"views": [{"path": "a", "cards": [A]}, {"path": "b", "cards": [A]}]}
    new = {"views": [{"path": "a", "cards": []}, {"path": "b", "cards": []}]}
    current = {"views": [{"path": "a", "cards": [A]}, {"path": "b", "cards": []}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("insert", "b")]


def test_an_added_card_is_planned_away():
    a = {"type": "tile", "entity": "light.a"}
    b = {"type": "tile", "entity": "light.b"}
    plan = analyze.plan_undo(_config([a]), _config([a, b]), _config([a, b]))
    assert [(s.action, s.expect) for s in plan.steps] == [("remove", b)]


def test_a_change_without_card_effect_is_refused():
    a = {"type": "tile", "entity": "light.a"}
    plan = analyze.plan_undo(_config([a]), _config([a]), _config([a]))
    assert plan.blocked == "this change did not alter any cards"


def test_later_work_elsewhere_does_not_block():
    """The check is on what the change produced, not on its neighbours."""
    old = {"type": "tile", "entity": "light.a", "name": "Bett"}
    new = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    later = {"type": "tile", "entity": "light.z"}
    plan = analyze.plan_undo(_config([old]), _config([new]), _config([new, later]))
    assert plan.blocked is None
    assert [s.action for s in plan.steps] == ["remove", "insert"]


def test_a_moved_card_is_removed_here_and_put_back_there():
    stays = {"type": "markdown", "content": "Stays"}
    travels = {"type": "markdown", "content": "Travels"}
    before = {
        "views": [
            {"path": "a", "cards": [stays, travels]},
            {"path": "b", "cards": []},
        ]
    }
    after = {
        "views": [
            {"path": "a", "cards": [stays]},
            {"path": "b", "cards": [travels]},
        ]
    }
    plan = analyze.plan_undo(before, after, after)
    actions = [(s.action, s.view_path, s.index) for s in plan.steps]
    assert ("remove", "b", 0) in actions
    assert ("insert", "a", 1) in actions


def test_an_edited_card_goes_back_to_its_own_place():
    """Where an edit is put back is decided on the old side, not today's.

    An edit can move a card too, and `_place` leaves the index out - so
    such a card arrives as *edited*, not as moved, and a step written
    at today's index would land on its neighbour. Two edited cards that
    also swapped are the smallest case where that shows: today card 0
    is `new1` and card 1 is `new0`, so `old0` must be taken off index 1
    and put back at index 0.
    """
    old0 = {"type": "tile", "entity": "light.a", "name": "Bett"}
    old1 = {"type": "tile", "entity": "light.b", "name": "Tisch"}
    new0 = {"type": "tile", "entity": "light.a", "name": "Bettlampe"}
    new1 = {"type": "tile", "entity": "light.b", "name": "Tischlampe"}
    plan = analyze.plan_undo(
        _config([old0, old1]), _config([new1, new0]), _config([new1, new0])
    )
    assert plan.blocked is None
    assert [(s.action, s.index) for s in plan.steps] == [
        ("remove", 1),
        ("insert", 0),
        ("remove", 0),
        ("insert", 1),
    ]


def test_a_deleted_view_is_planned_back():
    a = {"path": "a", "title": "A", "cards": [{"type": "tile", "entity": "light.a"}]}
    b = {"path": "b", "title": "B", "cards": []}
    plan = analyze.plan_undo({"views": [a, b]}, {"views": [a]}, {"views": [a]})
    assert plan.blocked is None
    assert [(s.action, s.kind, s.payload) for s in plan.steps] == [
        ("insert", "view", b)
    ]


def test_an_added_view_is_planned_away():
    a = {"path": "a", "title": "A", "cards": []}
    b = {"path": "b", "title": "B", "cards": []}
    plan = analyze.plan_undo({"views": [a]}, {"views": [a, b]}, {"views": [a, b]})
    assert [(s.action, s.kind, s.index) for s in plan.steps] == [
        ("remove", "view", 1)
    ]


def test_an_added_view_changed_since_is_refused():
    a = {"path": "a", "title": "A", "cards": []}
    b = {"path": "b", "title": "B", "cards": []}
    worked_on = {"path": "b", "title": "B", "cards": [{"type": "tile"}]}
    plan = analyze.plan_undo(
        {"views": [a]}, {"views": [a, b]}, {"views": [a, worked_on]}
    )
    assert plan.steps == ()
    assert "changed again" in plan.blocked


def test_an_added_view_renamed_since_is_refused():
    """A path is renameable, so its absence is not proof of anything.

    The change added the view `b`; somebody has since given it the path
    `c`. Looking only for the key would find nothing, plan nothing, and
    let the caller answer "this change is already taken back" - which is
    a false statement about a view that is still there.
    """
    a = {"path": "a", "title": "A", "cards": []}
    b = {"path": "b", "title": "B", "cards": []}
    renamed = {"path": "c", "title": "B", "cards": []}
    plan = analyze.plan_undo(
        {"views": [a]}, {"views": [a, b]}, {"views": [a, renamed]}
    )
    assert plan.steps == ()
    assert "no longer on the dashboard" in plan.blocked
    assert "B" in plan.blocked


def test_a_stranger_on_a_removed_views_path_is_refused():
    """A path is reusable, so its presence is not proof either.

    The change removed the view `b`; a different view carries that path
    today. Counting the path as "already back" would answer that the
    change is undone while the view it removed is nowhere - and putting
    the old one back regardless would leave two views on one path.
    """
    a = {"path": "a", "title": "A", "cards": []}
    b = {"path": "b", "title": "B", "cards": []}
    stranger = {"path": "b", "title": "Something else", "cards": []}
    plan = analyze.plan_undo(
        {"views": [a, b]}, {"views": [a]}, {"views": [a, stranger]}
    )
    assert plan.steps == ()
    assert "a different view now sits at" in plan.blocked


def test_a_removed_view_really_back_needs_no_step():
    """The control: the same path, holding the same view again."""
    a = {"path": "a", "title": "A", "cards": []}
    b = {"path": "b", "title": "B", "cards": []}
    plan = analyze.plan_undo({"views": [a, b]}, {"views": [a]}, {"views": [a, b]})
    assert plan.blocked is None
    assert plan.steps == ()


# ------------------------------------------- whole views in the message
#
# A whole view counts as one, not as its cards - the same grain the
# explanation uses. Why, and what it looked like before: `summarize`.


def test_a_renamed_empty_view_is_not_called_no_card_changes():
    old = {"views": [{"path": "home", "cards": []}]}
    new = {"views": [{"path": "kitchen", "cards": []}]}
    assert (
        analyze.change_message("dash", old, new, "save")
        == "dash: 1 view removed, 1 view added"
    )


def test_a_vanished_view_is_counted_as_a_view_and_not_as_its_cards():
    old = {"views": [{"path": "home", "cards": [A]}, {"path": "gone", "cards": [B, C]}]}
    new = {"views": [{"path": "home", "cards": [A]}]}
    counts = analyze.summarize(old, new)
    assert (counts.views_removed, counts.removed) == (1, 0)
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 view removed"


def test_two_new_views_are_counted_in_the_plural():
    old = {"views": [{"path": "home", "cards": [A]}]}
    new = {
        "views": [
            {"path": "home", "cards": [A]},
            {"path": "b", "cards": [B]},
            {"path": "c", "cards": []},
        ]
    }
    assert analyze.change_message("dash", old, new, "save") == "dash: 2 views added"


def test_views_and_cards_are_both_named_when_both_changed():
    old = {"views": [{"path": "home", "cards": [A, B]}, {"path": "gone", "cards": [C]}]}
    new = {"views": [{"path": "home", "cards": [A]}]}
    assert (
        analyze.change_message("dash", old, new, "save")
        == "dash: 1 view removed, 1 removed"
    )


# -- positions are not identities --------------------------------------
#
# A view without a URL path is keyed by where it sits. That is an
# address, not an identity: delete the view before it, or drop a new one
# in front of it, and the same key names a different view. Undoing on
# such a key wrote the wrong state - silently, with a preview that read
# like an ordinary undo. Measured on 2026-09-04 against a running Home
# Assistant; the three cases below are what came back.
#
# The rule these tests pin down: when a position cannot be trusted to
# mean the same view in both states, refuse. Decision 4 of the spec
# already says guessing is forbidden, and refusing is what it allows.


def test_undo_refuses_when_a_pathless_view_was_deleted_before_another():
    """The deleted view and its successor share the key ("#", 0).

    Home is gone, Wetter moved up into its place. Read by position this
    is "the cards on view 0 changed", and the undo wrote Home's card
    onto Wetter - destroying a card nobody touched.
    """
    home = {"title": "Home", "cards": [A]}
    weather = {"title": "Wetter", "cards": [B]}
    plan = analyze.plan_undo(
        {"views": [home, weather]}, {"views": [weather]}, {"views": [weather]}
    )
    assert plan.blocked is not None
    assert "URL path" in plan.blocked


def test_undo_refuses_when_a_deletion_shifted_a_pathless_view():
    """The pathless view is not even part of the change.

    Deleting the view with path "b" moves Home from position 2 to 1.
    Nothing about Home changed, yet the undo deleted it.
    """
    first = {"path": "a", "title": "A", "cards": [A]}
    second = {"path": "b", "title": "B", "cards": [B]}
    home = {"title": "Home", "cards": [C]}
    plan = analyze.plan_undo(
        {"views": [first, second, home]},
        {"views": [first, home]},
        {"views": [first, home]},
    )
    assert plan.blocked is not None
    assert "URL path" in plan.blocked


def test_undo_refuses_when_a_view_was_inserted_before_a_pathless_one():
    """Both branches fire on the same view, and it disappears.

    Home counts as added (its key is new) and as already back (its
    content still stands), so it is removed and never put back. The
    measured result was an empty dashboard.
    """
    home = {"title": "Home", "cards": [A]}
    fresh = {"path": "neu", "title": "Neu", "cards": [B]}
    plan = analyze.plan_undo(
        {"views": [home]}, {"views": [fresh, home]}, {"views": [fresh, home]}
    )
    assert plan.blocked is not None
    assert "URL path" in plan.blocked


def test_undo_still_works_on_a_pathless_view_that_stayed_put():
    """The everyday case must survive the rule above.

    Nothing moved: the pathless view sits at the same position in both
    states and holds the same title. Its position therefore does mean
    the same view, and a card deleted from it is undoable as ever.
    """
    before = {"views": [{"path": "a", "cards": [A]}, {"title": "Home", "cards": [B, C]}]}
    after = {"views": [{"path": "a", "cards": [A]}, {"title": "Home", "cards": [C]}]}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert [(s.action, s.kind, s.payload) for s in plan.steps] == [
        ("insert", "card", B)
    ]


def test_undo_still_works_when_a_pathless_view_is_appended_after():
    """Appending a view at the end cannot have shifted anything before it.

    GitHub #33: Home stayed exactly where it was; a pathless view
    appended afterwards used to make the guard refuse anyway, because it
    only ever compared the whole set of positions, never where they
    first stopped lining up.
    """
    home_before = {"title": "Home", "cards": [A]}
    home_after = {"title": "Home", "cards": [A, B]}
    fresh = {"title": "Neu", "cards": [C]}
    plan = analyze.plan_undo(
        {"views": [home_before]},
        {"views": [home_after]},
        {"views": [home_after, fresh]},
    )
    assert plan.blocked is None
    assert [(s.action, s.kind, s.payload) for s in plan.steps] == [
        ("remove", "card", None)
    ]


def test_undo_works_on_the_only_view_even_without_path_or_title():
    """A single view has nothing to be confused with.

    GitHub #33, same idea as the append above: a position that cannot
    have shifted keeps its meaning. With one view in both states there is
    no neighbour that could have moved in front of it - yet an untitled
    one used to be refused for any card change, because its content
    changed and there was no title to recognise it by.
    """
    plan = analyze.plan_undo(
        {"views": [{"cards": [A]}]},
        {"views": [{"cards": [A, B]}]},
        {"views": [{"cards": [A, B]}]},
    )
    assert plan.blocked is None
    assert [(s.action, s.kind) for s in plan.steps] == [("remove", "card")]


def test_undo_refuses_when_the_only_view_gained_a_neighbour_in_front():
    """One view on one side only is not the single-view case."""
    plan = analyze.plan_undo(
        {"views": [{"cards": [A]}]},
        {"views": [{"cards": [A, B]}]},
        {"views": [{"cards": [C]}, {"cards": [A, B]}]},
    )
    assert plan.blocked is not None
    assert "URL path" in plan.blocked


def test_undo_refuses_when_a_pathless_view_was_inserted_before_another():
    """An insertion in the middle must not be read as a mere append.

    GitHub #33's own caution: dropping "Neu" between Home and Office
    raises the view count by one, exactly like appending it after Office
    would - only comparing lengths cannot tell them apart. Office itself
    shifted from position 1 to 2, so the change made to it is still not
    undoable.
    """
    home = {"title": "Home", "cards": [A]}
    office = {"title": "Office", "cards": [B]}
    office_after = {"title": "Office", "cards": [B, C]}
    fresh = {"title": "Neu", "cards": []}
    plan = analyze.plan_undo(
        {"views": [home, office]},
        {"views": [home, office_after]},
        {"views": [home, fresh, office_after]},
    )
    assert plan.blocked is not None
    assert "URL path" in plan.blocked


def test_undo_refuses_when_a_section_was_inserted_before_another():
    """Sections are addressed by index too, and never carry a path.

    Home Assistant gives a section no path and no id, so ("sections", 1,
    "cards") is the only address there is. Put a section in front and it
    names a different one: measured, the undo pulled a card into the new
    section and left the old one empty.
    """
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"title": "Unten", "cards": [B]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"title": "Neu", "cards": [C]},
                                   {"title": "Unten", "cards": [B]}]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert "section" in plan.blocked


def test_undo_still_works_when_the_sections_stayed_put():
    """A card deleted from a section that did not move is undoable."""
    old = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"title": "Oben", "cards": [A]},
                                   {"title": "Unten", "cards": [B, C]}]}]}
    new = {"views": [{"path": "home", "type": "sections",
                      "sections": [{"title": "Oben", "cards": [A]},
                                   {"title": "Unten", "cards": [C]}]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert [(s.action, s.kind, s.payload) for s in plan.steps] == [
        ("insert", "card", B)
    ]


def test_undo_refuses_when_two_untitled_sections_swap_settings():
    """A section swap without titles must not slip past `_section_drift`.

    Home Assistant names a section with a heading card, not `title` -
    untitled sections are the common case, and the docstring on
    `_section_drift` already names this gap. Swapping two whole sections
    (settings included) leaves the ordered title list unchanged
    (`[None, None]` both times), so the old check saw nothing wrong and
    let the undo through. It would have moved the cards back but left
    `column_span` pinned to its index - section 0 ends up with card A's
    old neighbour's setting, a state that never existed. GitHub #31.
    """
    old = {"views": [{"path": "home", "type": "sections", "sections": [
        {"column_span": 2, "cards": [A]},
        {"column_span": 1, "cards": [B]},
    ]}]}
    new = {"views": [{"path": "home", "type": "sections", "sections": [
        {"column_span": 1, "cards": [B]},
        {"column_span": 2, "cards": [A]},
    ]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert "section" in plan.blocked


# -- sections that moved since: park, do not refuse (GitHub #30) ---------

BETT = {"type": "tile", "entity": "light.x", "name": "Bett"}
BETTLAMPE = {"type": "tile", "entity": "light.x", "name": "Bettlampe"}


def _sectioned(*sections, path="home", **extra):
    view = {"type": "sections", "sections": [dict(s) for s in sections], **extra}
    if path is not None:
        view["path"] = path
    return view


def test_an_edit_whose_section_moved_since_is_parked():
    """Decision 26: the card cannot be proven to belong at index 1 any more.

    The change only edited a card. A section was put in front of it
    afterwards. Taking the edited card out is exact - it is found by its
    fingerprint - but where the old one goes back in is not, so it goes
    into the view's own `cards:`, Home Assistant's "Imported cards".
    """
    before = {"views": [_sectioned({"cards": [BETT]})]}
    after = {"views": [_sectioned({"cards": [BETTLAMPE]})]}
    current = {"views": [_sectioned({"column_span": 2, "cards": []}, {"cards": [BETTLAMPE]})]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [(s.action, s.location, s.index, s.parked) for s in plan.steps] == [
        ("remove", ("sections", 1, "cards"), 0, False),
        ("insert", ("cards",), 0, True),
    ]
    assert plan.steps[1].payload == BETT
    assert plan.parked == ("tile: Bett",)


def test_sections_that_moved_in_another_view_do_not_block():
    """The check used to cover the whole dashboard; now it covers a view."""
    other = {"path": "a", "cards": [A]}
    moved = _sectioned({"cards": [B]}, path="s")
    moved_since = _sectioned({"cards": [B]}, {"column_span": 2, "cards": []}, path="s")
    plan = analyze.plan_undo(
        {"views": [other, moved]},
        {"views": [{"path": "a", "cards": []}, moved]},
        {"views": [{"path": "a", "cards": []}, moved_since]},
    )
    assert plan.blocked is None
    assert plan.parked == ()
    assert [(s.action, s.location, s.payload) for s in plan.steps] == [
        ("insert", ("cards",), A)
    ]


def test_only_removals_in_a_shifted_view_stay_exact():
    """Nothing goes back in, so there is nothing whose place is in doubt."""
    before = {"views": [_sectioned({"cards": [A]})]}
    after = {"views": [_sectioned({"cards": [A, B]})]}
    current = {"views": [_sectioned({"column_span": 2, "cards": []}, {"cards": [A, B]})]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.parked == ()
    assert [(s.action, s.location, s.index) for s in plan.steps] == [
        ("remove", ("sections", 1, "cards"), 1)
    ]


def test_a_pathless_view_whose_sections_moved_parks_too():
    """Reaching the section check means `_positions_lie` already vouched
    for the view - the same proof an ordinary insert into it relies on.

    Two views, so the single-view rule of #33 does not decide it: here
    the unchanged title is what lets the position check pass. Without
    it the view's changed content would refuse first, for a reason of
    its own (`test_…_without_its_title_refuses_by_position` below)."""
    first = {"path": "a", "cards": [A]}
    before = {"views": [first, _sectioned({"cards": [BETT]}, path=None, title="Home")]}
    after = {"views": [first, _sectioned({"cards": [BETTLAMPE]}, path=None, title="Home")]}
    current = {"views": [first, _sectioned({"column_span": 2, "cards": []}, {"cards": [BETTLAMPE]},
                                           path=None, title="Home")]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    parked = [s for s in plan.steps if s.parked]
    assert [(s.view_path, s.view_index, s.location) for s in parked] == [(None, 1, ("cards",))]


def test_a_pathless_view_whose_sections_moved_without_its_title_refuses_by_position():
    """The control for the test above: the title is what decided it."""
    first = {"path": "a", "cards": [A]}
    before = {"views": [first, _sectioned({"cards": [BETT]}, path=None)]}
    after = {"views": [first, _sectioned({"cards": [BETTLAMPE]}, path=None)]}
    current = {"views": [first, _sectioned({"column_span": 2, "cards": []}, {"cards": [BETTLAMPE]},
                                           path=None)]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None
    assert "URL path" in plan.blocked


def test_a_change_that_rebuilt_the_sections_says_so():
    """Parking answers "where does this card go", not "what did the view look like"."""
    old = {"views": [_sectioned({"cards": [B]})]}
    new = {"views": [_sectioned({"column_span": 2, "cards": [C]}, {"cards": [B]})]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert "this change rearranged the sections" in plan.blocked


def test_a_card_from_imported_cards_goes_back_to_its_index_not_parked():
    before = {"views": [_sectioned({"cards": [B]}, cards=[A])]}
    after = {"views": [_sectioned({"cards": [B]}, cards=[])]}
    current = {"views": [_sectioned({"column_span": 2, "cards": []}, {"cards": [B]}, cards=[])]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert [(s.action, s.location, s.index, s.parked) for s in plan.steps] == [
        ("insert", ("cards",), 0, False)
    ]


def test_several_parked_cards_keep_the_order_of_their_old_places():
    before = {"views": [_sectioned({"cards": [A]}, {"cards": [B]})]}
    after = {"views": [_sectioned({"cards": []}, {"cards": []})]}
    current = {"views": [_sectioned({"cards": []}, {"cards": []}, {"column_span": 2, "cards": []})]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert plan.parked == ("tile: light.a", "tile: light.b")


def test_parked_cards_of_two_views_stay_grouped_by_view():
    """The dialog lists them; interleaving two views' cards reads as noise."""
    p_before = _sectioned({"cards": [A]}, {"cards": [B]}, path="p")
    q_before = _sectioned({"cards": [C]}, path="q")
    p_after = _sectioned({"cards": []}, {"cards": []}, path="p")
    q_after = _sectioned({"cards": []}, path="q")
    p_now = _sectioned({"cards": []}, {"cards": []}, {"column_span": 2, "cards": []}, path="p")
    q_now = _sectioned({"cards": []}, {"column_span": 2, "cards": []}, path="q")
    plan = analyze.plan_undo(
        {"views": [p_before, q_before]},
        {"views": [p_after, q_after]},
        {"views": [p_now, q_now]},
    )
    assert plan.parked == ("tile: light.a", "tile: light.b", "tile: light.c")


def test_undo_of_a_view_conversion_names_the_conversion_not_sections():
    """A converted view is refused for the right reason, not a coincidence.

    Here the conversion happens to coincide with a card moving into the
    new section, so `match_cards` already sees something to report.
    Converting a view to sections also adds an empty grid section -
    exactly what `_section_drift` reacts to, since the section list went
    from empty to one entry. It fired, but named "the sections", which
    was never the actual cause: the view itself was converted. GitHub #32.
    """
    old = {"views": [{"path": "home", "cards": [A]}]}
    new = {
        "views": [
            {
                "path": "home",
                "type": "sections",
                "sections": [{"type": "grid", "cards": [A]}],
            }
        ]
    }
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert "section" not in plan.blocked
    assert "layout" in plan.blocked


def test_undo_of_a_pure_view_conversion_is_refused_by_layout_not_by_cards():
    """The actual, common shape: conversion alone, no card touched.

    Confirmed 2026-09-23 against a running Home Assistant test container
    (design journal, Entscheidung 26): converting masonry to sections
    does not redistribute cards. It adds one empty grid section and
    leaves every existing card exactly where it was, in the view's own
    `cards:` list. `match_cards` therefore sees nothing - no card
    removed, added, edited or moved - and the early "did not alter any
    cards" gate in `plan_undo` used to fire before `_view_type_changed`
    was ever reached, hiding the real, nameable reason behind a message
    that denies anything happened at all. GitHub #32.
    """
    old = {"views": [{"path": "home", "cards": [A]}]}
    new = {
        "views": [
            {
                "path": "home",
                "type": "sections",
                "cards": [A],
                "sections": [{"type": "grid", "cards": []}],
            }
        ]
    }
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert plan.blocked != "this change did not alter any cards"
    assert "layout" in plan.blocked


def test_undo_refuses_when_two_views_share_one_path():
    """Home Assistant's backend permits it; then a path names two views.

    Measured before this guard: the first of the two was invisible to the
    analysis, deleting it read as cards removed, and the undo wrote those
    cards into the survivor.
    """
    old = {
        "views": [
            {"path": "x", "title": "One", "cards": [{"type": "tile", "entity": "light.a"}]},
            {"path": "x", "title": "Two", "cards": [{"type": "tile", "entity": "light.b"}]},
        ]
    }
    new = {"views": [{"path": "x", "title": "Two", "cards": [{"type": "tile", "entity": "light.b"}]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is not None
    assert "share one URL path" in plan.blocked


def _with_sections(*sections):
    """A view in the sections layout, holding the sections given."""
    return {
        "views": [
            {
                "path": "home",
                "title": "H",
                "type": "sections",
                "sections": [dict(section) for section in sections],
            }
        ]
    }


def test_a_deleted_section_is_offered_as_one_item():
    """Not as its cards, each of which refuses on its own.

    Before this, `find_removed` knew only "view" and "card": the cards of
    a deleted section were offered individually and every one of them
    refused, because the section they name is not the one standing at
    that index now. Buttons that reliably fail.
    """
    first = {"title": None, "cards": [{"type": "tile", "entity": "light.a"},
                                      {"type": "tile", "entity": "light.b"}]}
    second = {"title": None, "cards": [{"type": "tile", "entity": "light.z"}]}
    old = _with_sections(first, second)
    new = _with_sections(second)

    items = analyze.find_removed(old, new)

    assert [item.kind for item in items] == ["section"]
    section = items[0]
    assert section.payload == first
    assert section.index == 0
    assert section.location == ("sections",)
    assert section.neighbours == (second,)


def test_an_empty_section_that_was_deleted_is_not_offered_back():
    """It had nothing on it, and nothing to prove itself with.

    An empty section carries no cards, so nothing in the matching can
    say it was the one that went - every empty section in a shrunken
    view would look equally deleted. And there was nothing on it to
    lose, so refusing to offer it costs nobody anything.
    """
    card = {"type": "tile", "entity": "light.a"}
    old = _with_sections({"title": None, "cards": [card]}, {"title": None, "cards": []})
    new = _with_sections({"title": None, "cards": [card]})

    assert analyze.find_removed(old, new) == []


# -- named settings (GitHub #28) ------------------------------------------


def _changes(old, new):
    return [
        (c.view_key, c.path,
         "ABSENT" if c.old is analyze._ABSENT else c.old,
         "ABSENT" if c.new is analyze._ABSENT else c.new)
        for c in analyze.setting_changes(old, new)
    ]


def test_a_key_added_under_strategy_is_one_leaf():
    old = {"strategy": {"type": "original-states"}}
    new = {"strategy": {"type": "original-states", "show_clock_card": False}}
    assert _changes(old, new) == [(None, ("strategy", "show_clock_card"), "ABSENT", False)]


def test_a_whole_block_that_appears_is_the_leaf():
    assert _changes({}, {"strategy": {"type": "x"}}) == [
        (None, ("strategy",), "ABSENT", {"type": "x"})
    ]


def test_a_view_setting_is_keyed_by_its_view():
    old = {"views": [{"path": "home", "icon": "mdi:home", "cards": [A]}]}
    new = {"views": [{"path": "home", "icon": "mdi:sofa", "cards": [A, B]}]}
    assert _changes(old, new) == [("home", ("icon",), "mdi:home", "mdi:sofa")]


def test_cards_sections_badges_path_type_and_views_are_not_settings():
    old = {"views": [{"path": "home", "type": "masonry", "cards": [], "badges": []}]}
    new = {"views": [{"path": "home", "type": "sections", "sections": [],
                      "cards": [A], "badges": [{"entity": "sun.sun"}]}]}
    assert _changes(old, new) == []


def test_a_list_valued_setting_is_compared_whole():
    old = {"views": [{"path": "home", "visible": [{"user": "a"}]}]}
    new = {"views": [{"path": "home", "visible": [{"user": "a"}, {"user": "b"}]}]}
    assert _changes(old, new) == [
        ("home", ("visible",), [{"user": "a"}], [{"user": "a"}, {"user": "b"}])
    ]


def test_null_is_not_absent():
    old = {"views": [{"path": "home"}]}
    new = {"views": [{"path": "home", "theme": None}]}
    assert _changes(old, new) == [("home", ("theme",), "ABSENT", None)]


def test_one_and_true_are_different_settings():
    """Review focus 3: Python says 1 == True; a setting does not."""
    old = {"views": [{"path": "home", "max_columns": 1}]}
    new = {"views": [{"path": "home", "max_columns": True}]}
    assert _changes(old, new) == [("home", ("max_columns",), 1, True)]


def test_views_only_one_state_has_carry_no_settings():
    old = {"views": [{"path": "a", "icon": "x"}]}
    new = {"views": [{"path": "b", "icon": "y"}]}
    assert _changes(old, new) == []


def _texts(explanation):
    return [(g.scope, g.view, [e.text for e in g.entries]) for g in explanation.groups]


def test_a_strategy_setting_is_explained_on_the_dashboard_itself():
    old = {"strategy": {"type": "original-states"}}
    new = {"strategy": {"type": "original-states", "show_clock_card": False}}
    assert _texts(analyze.explain_change(old, new)) == [
        ("dashboard", "dashboard",
         ['the setting "strategy.show_clock_card" was set to false'])
    ]


def test_view_settings_come_before_cards_and_after_a_conversion():
    old = {"views": [{"path": "home", "icon": "mdi:home", "cards": [A]}]}
    new = {"views": [{"path": "home", "type": "sections", "icon": "mdi:sofa",
                      "cards": [A, B], "sections": [{"type": "grid", "cards": []}]}]}
    [(scope, view, texts)] = _texts(analyze.explain_change(old, new))
    assert scope == "view"
    assert texts == [
        'the view "home" was converted from masonry to sections',
        'the setting "icon" was changed from "mdi:home" to "mdi:sofa"',
        "tile: light.b was added",
    ]


def test_a_removed_setting_and_a_block_value_are_worded_without_a_value():
    old = {"views": [{"path": "home", "theme": "dark", "visible": [{"user": "a"}]}]}
    new = {"views": [{"path": "home", "visible": []}]}
    [(_, _, texts)] = _texts(analyze.explain_change(old, new))
    assert texts == [
        'the setting "theme" was removed',
        'the setting "visible" was changed',
    ]


def test_the_future_tense_says_where_a_setting_goes():
    current = {"views": [{"path": "home", "max_columns": 4}]}
    target = {"views": [{"path": "home", "max_columns": 3}]}
    [(_, _, texts)] = _texts(analyze.explain_effect(current, target))
    assert texts == ['the setting "max_columns" goes back to 3']


def test_a_removed_setting_counts_as_something_removed():
    """The reassurance "Nothing on this dashboard is deleted" must not follow."""
    current = {"views": [{"path": "home", "theme": "dark"}]}
    target = {"views": [{"path": "home"}]}
    assert analyze.explain_effect(current, target).note == ""


def test_many_changed_templates_are_capped_like_cards():
    """Review focus 5."""
    old = {"button_card_templates": {f"t{i}": {"color": "red"} for i in range(20)}}
    new = {"button_card_templates": {f"t{i}": {"color": "blue"} for i in range(20)}}
    [group] = analyze.explain_change(old, new).groups
    assert len(group.entries) == analyze._ENTRY_LIMIT
    assert group.more == 20 - analyze._ENTRY_LIMIT


def _steps(plan):
    return [(s.kind, s.action, s.location, s.payload, s.expect_absent) for s in plan.steps]


def test_a_setting_only_change_is_undoable():
    before = {"strategy": {"type": "original-states"}}
    after = {"strategy": {"type": "original-states", "show_clock_card": False}}
    plan = analyze.plan_undo(before, after, after)
    assert plan.blocked is None
    assert _steps(plan) == [
        ("dashboard_setting", "unset", ("strategy", "show_clock_card"), None, False)
    ]


def test_a_setting_changed_again_refuses():
    before = {"views": [{"path": "home", "icon": "a"}]}
    after = {"views": [{"path": "home", "icon": "b"}]}
    current = {"views": [{"path": "home", "icon": "c"}]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked == 'the setting "icon" was changed again after this'


def test_a_setting_already_back_is_skipped_and_its_neighbour_is_not():
    # Two settings, only one of them back. A plan that ignored settings
    # altogether would pass a single-setting version of this test too.
    before = {"views": [{"path": "home", "icon": "a", "theme": "x"}]}
    after = {"views": [{"path": "home", "icon": "b", "theme": "y"}]}
    current = {"views": [{"path": "home", "icon": "a", "theme": "y"}]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert _steps(plan) == [("view_setting", "set", ("theme",), "x", False)]


def test_another_key_of_the_same_block_changed_since_stays_exact():
    """Review focus 1."""
    before = {"strategy": {"type": "x"}}
    after = {"strategy": {"type": "x", "a": 1}}
    current = {"strategy": {"type": "x", "a": 1, "b": 2}}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is None
    assert _steps(plan) == [("dashboard_setting", "unset", ("strategy", "a"), None, False)]


def test_a_block_removed_since_refuses_rather_than_half_rebuilt():
    """Review focus 2."""
    before = {"strategy": {"type": "x", "a": 1}}
    after = {"strategy": {"type": "x"}}
    current = {}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked == 'the setting "strategy.a" no longer has the "strategy" block it belonged to'


def test_setting_back_a_removed_setting_writes_its_old_value():
    before = {"views": [{"path": "home", "theme": None}]}
    after = {"views": [{"path": "home"}]}
    plan = analyze.plan_undo(before, after, after)
    assert _steps(plan) == [("view_setting", "set", ("theme",), None, True)]


def test_a_setting_of_a_view_gone_since_refuses():
    before = {"views": [{"path": "home", "icon": "a"}]}
    after = {"views": [{"path": "home", "icon": "b"}]}
    plan = analyze.plan_undo(before, after, {"views": []})
    assert plan.blocked is not None
    assert "no longer on the dashboard" in plan.blocked


def test_a_refused_card_refuses_the_setting_with_it():
    before = {"views": [{"path": "home", "icon": "a", "cards": []}]}
    after = {"views": [{"path": "home", "icon": "b", "cards": [A]}]}
    current = {"views": [{"path": "home", "icon": "b", "cards": [A, A]}]}
    plan = analyze.plan_undo(before, after, current)
    assert plan.blocked is not None
    assert plan.steps == ()


def test_a_setting_only_save_is_counted_in_the_history_line():
    old = {"strategy": {"type": "x"}}
    new = {"strategy": {"type": "x", "show_clock_card": False}}
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 setting changed"


def test_settings_are_counted_after_cards():
    old = {"views": [{"path": "home", "icon": "a", "theme": "x", "cards": []}]}
    new = {"views": [{"path": "home", "icon": "b", "cards": [A]}]}
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 added, 2 settings changed"


def test_a_settings_part_parses_and_is_no_addition():
    assert not analyze.message_adds("dash: 2 settings changed")
    assert analyze.message_adds("dash: 1 added, 1 setting changed")


def test_one_becoming_true_is_a_change_not_metadata():
    """Review focus 3: `old == new` says yes, the commit says no."""
    old = {"views": [{"path": "home", "max_columns": 1}]}
    new = {"views": [{"path": "home", "max_columns": True}]}
    assert analyze.change_message("dash", old, new, "save") == "dash: 1 setting changed"


# -- badges (GitHub #29) ----------------------------------------------------

SUN = {"type": "entity", "entity": "sun.sun"}
MOON = {"type": "entity", "entity": "sensor.moon"}


def _badge_matching(old, new):
    m = analyze.match_badges(old, new)
    return (
        [s.card for s in m.removed],
        [s.card for s in m.added],
        [(o.card, n.card) for o, n in m.edited],
        [(o.view_key, n.view_key) for o, n in m.moved],
    )


def test_an_added_badge_is_found():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN]}]}
    assert _badge_matching(old, new) == ([], [SUN], [], [])


def test_an_edited_badge_is_an_edit():
    shown = {**SUN, "show_name": False}
    old = {"views": [{"path": "home", "badges": [SUN]}]}
    new = {"views": [{"path": "home", "badges": [shown]}]}
    assert _badge_matching(old, new) == ([], [], [(SUN, shown)], [])


def test_a_badge_moved_to_another_view_is_a_move():
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": [SUN]}]}
    assert _badge_matching(old, new) == ([], [], [], [("a", "b")])


def test_a_badge_and_an_identical_card_never_meet():
    """Review focus 3: `type: entity` is a card and a badge."""
    old = {"views": [{"path": "home", "cards": [SUN], "badges": []}]}
    new = {"views": [{"path": "home", "cards": [], "badges": [SUN]}]}
    cards = analyze.match_cards(old, new)
    badges = analyze.match_badges(old, new)
    assert [s.card for s in cards.removed] == [SUN] and not cards.moved
    assert [s.card for s in badges.added] == [SUN] and not badges.moved


def test_badges_are_invisible_to_match_cards():
    old = {"views": [{"path": "home", "cards": [A], "badges": []}]}
    new = {"views": [{"path": "home", "cards": [A], "badges": [SUN]}]}
    m = analyze.match_cards(old, new)
    assert not (m.removed or m.added or m.edited or m.moved)


def test_a_badge_without_a_type_is_described_as_a_badge():
    """Review focus 5: the old form `{entity: …}`, three of them on the bank."""
    assert analyze._describe({"entity": "sun.sun"}, fallback="badge") == "badge: sun.sun"
    assert analyze._describe({"entity": "sun.sun"}) == "card: sun.sun"


def test_an_added_badge_is_undone():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert [(s.action, s.kind, s.location, s.index) for s in plan.steps] == [
        ("remove", "badge", ("badges",), 0)
    ]


def test_a_badge_copied_on_other_views_is_found_in_its_own():
    """Review focus 1: stage 2 of the uniqueness question."""
    b = {"path": "b", "badges": [SUN]}
    c = {"path": "c", "badges": [SUN]}
    old = {"views": [{"path": "a", "badges": []}, b, c]}
    new = {"views": [{"path": "a", "badges": [SUN]}, b, c]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked is None
    assert [(s.action, s.view_path) for s in plan.steps] == [("remove", "a")]


def test_a_badge_moved_elsewhere_since_is_found_there():
    old = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": []}]}
    new = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    current = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("remove", "b")]


def test_two_identical_badges_in_one_view_refuse():
    old = {"views": [{"path": "a", "badges": []}]}
    new = {"views": [{"path": "a", "badges": [SUN]}]}
    current = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == (
        "2 badges now look exactly like the badge entity: sun.sun, "
        "so an exact undo cannot tell them apart"
    )


def test_an_edited_badge_changed_again_refuses():
    shown = {**SUN, "show_name": False}
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": [shown]}]}
    current = {"views": [{"path": "a", "badges": [{**SUN, "show_name": True}]}]}
    plan = analyze.plan_undo(old, new, current)
    assert "changed again after this" in plan.blocked


def test_a_deleted_badge_with_an_untouched_copy_elsewhere_is_put_back():
    """Review focus 2: the copy on "b" never left, so it is not this one back."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, new)
    assert [(s.action, s.kind, s.view_path) for s in plan.steps] == [
        ("insert", "badge", "a")
    ]


def test_a_deleted_badge_added_back_since_is_left_alone():
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": []}]}
    current = {"views": [{"path": "a", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked is None
    assert plan.steps == ()


def test_a_badge_only_change_passes_the_early_gate():
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": [MOON]}]}
    plan = analyze.plan_undo(old, new, new)
    assert plan.blocked != "this change did not alter any cards"


def test_the_sole_surviving_badge_of_several_is_not_proof():
    """Review focus 6: the change left two, one went since - the one on
    "a" stood there before and is not the change's to take away."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    new = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": [SUN]}]}
    current = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == (
        "the badge entity: sun.sun was changed again after this, so there "
        "is no exact version left to put back"
    )


def test_one_of_two_badges_gone_from_a_view_refuses():
    """Review focus 6, within one view: which of the two the change added is lost."""
    old = {"views": [{"path": "a", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    current = {"views": [{"path": "a", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert "changed again after this" in plan.blocked


def test_a_badge_copy_added_elsewhere_since_is_not_the_deleted_one_back():
    """Review focus 7: back is counted only in the view it was deleted from."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "c", "badges": []}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "c", "badges": []}]}
    current = {"views": [{"path": "a", "badges": []}, {"path": "c", "badges": [SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("insert", "a")]


def test_one_badge_back_of_two_deleted_refuses():
    """Review focus 7: one back does not settle both, and which place it
    took is not in the states - [MOON, SUN] now could be either SUN."""
    old = {"views": [{"path": "a", "badges": [SUN, MOON, SUN]}]}
    new = {"views": [{"path": "a", "badges": [MOON]}]}
    current = {"views": [{"path": "a", "badges": [MOON, SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == (
        "only some of the copies of the badge entity: sun.sun this change "
        "deleted are back, so an exact undo cannot tell which are missing"
    )


def test_two_badges_deleted_and_both_back_is_nothing_to_do():
    old = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    new = {"views": [{"path": "a", "badges": []}]}
    current = {"views": [{"path": "a", "badges": [SUN, SUN]}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked is None and plan.steps == ()


def test_a_badge_back_in_one_view_does_not_count_for_another():
    """Review focus 7: deleted from "a" and "b", added back only on "a"."""
    old = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": [SUN]}]}
    new = {"views": [{"path": "a", "badges": []}, {"path": "b", "badges": []}]}
    current = {"views": [{"path": "a", "badges": [SUN]}, {"path": "b", "badges": []}]}
    plan = analyze.plan_undo(old, new, current)
    assert [(s.action, s.view_path) for s in plan.steps] == [("insert", "b")]


def test_a_badge_of_a_pathless_view_that_moved_refuses():
    old = {"views": [{"badges": []}, {"path": "z", "cards": []}]}
    new = {"views": [{"badges": [SUN]}, {"path": "z", "cards": []}]}
    current = {"views": [{"path": "new"}, {"badges": [SUN]}, {"path": "z", "cards": []}]}
    plan = analyze.plan_undo(old, new, current)
    assert plan.blocked == analyze._POSITION_REFUSAL


def test_a_badge_is_explained_as_a_badge():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN]}]}
    [group] = analyze.explain_change(old, new).groups
    assert [(e.what, e.text) for e in group.entries] == [
        ("badge", "the badge entity: sun.sun was added")
    ]


def test_a_badge_moved_to_another_view_says_where():
    old = {"views": [{"path": "a", "title": "A", "badges": [SUN]},
                     {"path": "b", "title": "Küche", "badges": []}]}
    new = {"views": [{"path": "a", "title": "A", "badges": []},
                     {"path": "b", "title": "Küche", "badges": [SUN]}]}
    [group] = analyze.explain_change(old, new).groups
    assert [e.text for e in group.entries] == [
        'the badge entity: sun.sun was moved to "Küche"'
    ]


def test_badges_come_between_settings_and_cards():
    old = {"views": [{"path": "home", "icon": "a", "badges": [], "cards": []}]}
    new = {"views": [{"path": "home", "icon": "b", "badges": [SUN], "cards": [A]}]}
    [group] = analyze.explain_change(old, new).groups
    assert [e.what for e in group.entries] == ["setting", "badge", "card"]


def test_badges_are_counted_in_the_history_line():
    old = {"views": [{"path": "home", "badges": []}]}
    new = {"views": [{"path": "home", "badges": [SUN, MOON]}]}
    assert analyze.change_message("dash", old, new, "save") == "dash: 2 badges changed"
    assert not analyze.message_adds("dash: 2 badges changed")
    assert analyze.message_adds("dash: 1 added, 1 badge changed")


def test_a_badge_inside_a_heading_card_is_part_of_the_card():
    """A heading card's own `badges:` travel with the card, never as badges."""
    heading = {"type": "heading", "heading": "Top", "badges": [SUN]}
    grown = {**heading, "badges": [SUN, MOON]}
    old = {"views": [{"path": "a", "cards": [heading], "badges": []}]}
    new = {"views": [{"path": "a", "cards": [grown], "badges": []}]}
    [group] = analyze.explain_change(old, new).groups
    assert [e.what for e in group.entries] == ["card"]
