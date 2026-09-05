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
