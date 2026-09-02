"""Tests for the git-backed history store."""

import threading

import pytest
from dulwich.repo import Repo
from store import HistoryStore, _as_text
from versions import candidates


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def test_first_snapshot_creates_a_revision(store):
    assert store.write_snapshot("home", "a: 1\n", "first") is not None


def test_unchanged_snapshot_creates_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.write_snapshot("home", "a: 1\n", "second") is None


def test_changed_snapshot_creates_a_revision(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_history_is_per_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("other", "b: 1\n", "other first")
    store.write_snapshot("home", "a: 2\n", "home second")
    assert [c.message for c in store.list_changes("home")] == ["home second", "home first"]
    assert [c.message for c in store.list_changes("other")] == ["other first"]


def test_a_rename_appears_in_the_history(store):
    # A rename touches only meta/<key>.yaml. Filtering the walk on the
    # configuration alone would record it and then never show it - captured
    # and invisible is the worst of both.
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    store.write_snapshot("home", "a: 1\n", "renamed", meta="title: Kitchen\n")
    assert [c.message for c in store.list_changes("home")] == ["renamed", "first"]


def test_metadata_appearing_later_appears_in_the_history(store):
    # What every existing installation does on its first start after the
    # update: same cards, metadata recorded for the first time.
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 1\n", "metadata recorded", meta="title: Home\n")
    assert [c.message for c in store.list_changes("home")] == [
        "metadata recorded",
        "first",
    ]


def test_history_of_unknown_dashboard_is_empty(store):
    assert store.list_changes("nothing") == []


def test_history_of_empty_repository_is_empty(store):
    # No commit at all: there is no HEAD to walk.
    assert store.list_changes("home") == []


def test_read_at_returns_the_old_text(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.read_at("home", first) == "a: 1\n"


def test_read_at_before_the_file_existed_returns_none(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other")
    assert store.read_at("other", first) is None


def test_an_abbreviated_revision_is_resolved(store):
    # `git log --oneline` prints exactly this short form, so it is what
    # anyone looking into the repository will copy. dulwich does not
    # resolve it on its own.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.resolve(first[:7]) == first
    assert store.read_at("home", first[:7]) == "a: 1\n"


def test_a_full_revision_and_head_resolve(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve(first) == first
    assert store.resolve("HEAD") == first
    assert store.resolve(f"  {first}  ") == first


def test_an_unknown_revision_resolves_to_none(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve("nosuchthing") is None
    assert store.resolve("ffffffff") is None
    assert store.resolve("") is None


def test_a_too_short_revision_is_refused(store):
    # Four characters is git's own minimum. Below that an abbreviation
    # says too little to act on.
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve(first[:3]) is None


def test_a_version_resolves_to_the_commit_it_marks(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("v1", "Title", "Text.", first)
    tag = Repo(str(store.path))[b"refs/tags/v1"]
    assert store.resolve(tag.id.decode()) == first


def test_a_version_resolves_by_its_name(store):
    # The claim that a tag name works as a revision stood in the spec and
    # in the README and was never true: dulwich's Repo.__getitem__ does no
    # ref-name expansion, so `repo[b"v1.0.0"]` raises KeyError even when
    # the tag is right there. It went unnoticed because the only test
    # resolved the tag's *object id* instead of its name.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Title", "Text.", first)
    assert store.resolve("home/v1.0.0") == first


def test_a_version_name_reads_the_state_it_marks(store):
    # This is what makes going back to a version free: read_at takes the
    # name straight through, so restore_state needs no new code at all.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Title", "Text.", first)
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.read_at("home", "home/v1.0.0") == "a: 1\n"


def test_an_unknown_name_still_resolves_to_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.resolve("home/v9.9.9") is None


def test_metadata_travels_with_the_state(store):
    first = store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.read_meta_at("home", first) == "title: Home\n"
    assert store.read_at("home", first) == "a: 1\n"


def test_changed_metadata_alone_creates_a_revision(store):
    # Renaming a dashboard changes nothing about its cards. Without this it
    # would leave no trace, and a restore would bring back the old name.
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    second = store.write_snapshot("home", "a: 1\n", "renamed", meta="title: Kitchen\n")
    assert second is not None
    assert store.read_meta_at("home", second) == "title: Kitchen\n"


def test_unchanged_state_and_metadata_create_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.write_snapshot("home", "a: 1\n", "again", meta="title: Home\n") is None


def test_metadata_is_not_mistaken_for_a_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.list_dashboards() == ["home"]


def test_deleting_a_dashboard_takes_its_metadata_with_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    store.mark_deleted("home", "home: dashboard deleted")
    assert store.read_meta_at("home", "HEAD") is None
    assert store.read_meta_at("home", first) == "title: Home\n"


def test_a_deleted_dashboard_is_marked_and_stays_readable(store):
    # Deleting a whole dashboard is the heaviest loss there is, and Home
    # Assistant announces it with no event at all. Leaving no trace would
    # make it the only change the history misses.
    first = store.write_snapshot("gone", "a: 1\n", "first")
    store.write_snapshot("stays", "b: 1\n", "other")
    assert store.mark_deleted("gone", "gone: dashboard deleted") is not None
    assert [c.message for c in store.list_changes("gone")] == [
        "gone: dashboard deleted",
        "first",
    ]
    # The state itself is not lost - that is what a history is for.
    assert store.read_at("gone", first) == "a: 1\n"
    assert store.read_at("gone", "HEAD") is None
    assert store.read_at("stays", "HEAD") == "b: 1\n"


def test_marking_an_unknown_dashboard_does_nothing(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.mark_deleted("never-existed", "x: dashboard deleted") is None


def test_a_dashboard_is_marked_deleted_only_once(store):
    store.write_snapshot("gone", "a: 1\n", "first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    assert store.mark_deleted("gone", "gone: dashboard deleted") is None


def test_a_recreated_dashboard_starts_a_fresh_chapter(store):
    # If a *different* dashboard later takes the same url_path, comparing
    # it against its stranger of a predecessor would produce an enormous
    # and meaningless diff.
    store.write_snapshot("reused", "a: 1\n", "first")
    store.mark_deleted("reused", "reused: dashboard deleted")
    assert store.write_snapshot("reused", "totally: different\n", "new") is not None
    assert store.read_at("reused", "HEAD") == "totally: different\n"


def test_list_dashboards_names_what_the_history_tracks(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    assert store.list_dashboards() == ["home", "other"]
    store.mark_deleted("other", "other: dashboard deleted")
    assert store.list_dashboards() == ["home"]


def test_list_all_dashboards_remembers_deleted_ones(store):
    # The deleted one is the point: it is exactly what somebody comes
    # looking for, so the panel has to be able to offer it.
    store.write_snapshot("stays", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    assert store.list_dashboards() == ["stays"]
    assert store.list_all_dashboards() == ["gone", "stays"]


def test_list_all_dashboards_ignores_metadata(store):
    store.write_snapshot("home", "a: 1\n", "first", meta="title: Home\n")
    assert store.list_all_dashboards() == ["home"]


def test_last_known_meta_survives_the_deletion(store):
    store.write_snapshot("gone", "a: 1\n", "first", meta="title: Gone\n")
    store.mark_deleted("gone", "gone: dashboard deleted")
    assert store.read_meta_at("gone", "HEAD") is None
    assert store.last_known_meta("gone") == "title: Gone\n"


def test_last_known_meta_is_none_when_none_was_recorded(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.last_known_meta("home") is None


def test_list_dashboards_of_an_empty_repository_is_empty(store):
    assert store.list_dashboards() == []


def test_version_marks_a_revision_without_changing_history(store):
    store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("v1", "Kitchen rework", "Two cards moved.", second)
    versions = store.list_versions()
    assert [v.name for v in versions] == ["v1"]
    assert versions[0].title == "Kitchen rework"
    assert versions[0].description == "Two cards moved."
    assert versions[0].revision == second
    # The individual changes are still there and still separate.
    assert len(store.list_changes("home")) == 2


def test_the_temporary_file_is_never_tracked(store, tmp_path):
    # A leftover .tmp must never end up in the repository.
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml.tmp").write_text("junk", encoding="utf-8")
    store.write_snapshot("home", "a: 2\n", "second")
    repo = Repo(str(tmp_path / "history"))
    assert sorted(path.decode() for path in repo.open_index()) == ["home.yaml"]


def test_a_state_lost_before_the_commit_is_recorded_afterwards(store, tmp_path):
    # A crash between writing the file and committing leaves the file ahead
    # of the repository. Comparing against the file would drop that state
    # from the history for good and without a word; comparing against HEAD
    # picks it up on the next run.
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml").write_text("a: 2\n", encoding="utf-8")
    assert store.write_snapshot("home", "a: 2\n", "second") is not None
    assert [c.message for c in store.list_changes("home")] == ["second", "first"]


def test_an_unchanged_snapshot_repairs_the_working_tree(store, tmp_path):
    store.write_snapshot("home", "a: 1\n", "first")
    (tmp_path / "history" / "home.yaml").write_text("tampered\n", encoding="utf-8")
    assert store.write_snapshot("home", "a: 1\n", "again") is None
    assert (tmp_path / "history" / "home.yaml").read_text(encoding="utf-8") == "a: 1\n"


def test_parallel_writes_all_arrive(store):
    # dulwich holds an exclusive lock on the git index. Without serialising,
    # eight parallel writes let exactly one commit through.
    def write(number):
        store.write_snapshot(f"d{number}", f"n: {number}\n", f"commit {number}")

    threads = [threading.Thread(target=write, args=(i,)) for i in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert all(store.list_changes(f"d{i}") for i in range(8))


# -- descriptions of one's own -----------------------------------------
#
# The automatic message says what happened. Why it happened is only in
# somebody's head, and "before rebuilding the heating cards" is what you
# find again in a year - "2 removed, 1 edited" is not.
#
# The text is a git note, so the commit itself is untouched. That is not
# tidiness: a rewritten commit invalidates every revision this tool
# hands out, in panel responses, service results and error messages.


def test_a_description_appears_in_the_history(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision, "Before the heating rebuild") is True
    assert store.list_changes("home")[0].description == "Before the heating rebuild"


def test_a_change_without_a_description_has_an_empty_one(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.list_changes("home")[0].description == ""


def test_a_description_does_not_change_the_revision(store):
    # The whole reason for using notes instead of rewriting the commit.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Something")
    assert store.list_changes("home")[0].revision == revision


def test_a_description_replaces_the_previous_one(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "First wording")
    store.set_description(revision, "Second wording")
    assert store.list_changes("home")[0].description == "Second wording"


def test_an_emptied_description_is_gone_not_blank(store):
    # A blank note would leave the row with an invisible headline and the
    # automatic message hidden underneath it.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Something")
    store.set_description(revision, "   ")
    assert store.list_changes("home")[0].description == ""
    assert store.descriptions() == {}


def test_emptying_a_description_that_was_never_there_is_harmless(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision, "") is True


def test_a_description_survives_umlauts(store):
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "Vor dem Umbau der Heizung — äöüß")
    assert store.list_changes("home")[0].description == (
        "Vor dem Umbau der Heizung — äöüß"
    )


def test_an_abbreviated_revision_can_be_described(store):
    # What anyone copies out of the panel, which shows seven characters.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description(revision[:7], "Short form") is True
    assert store.list_changes("home")[0].description == "Short form"


def test_an_unknown_revision_is_refused(store):
    # dulwich raises KeyError for an unknown object, so this must be
    # resolved first. Refusing is right anyway: a note filed against
    # nothing is a note nobody ever sees again.
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.set_description("f" * 40, "Nowhere") is False
    assert store.descriptions() == {}


def test_descriptions_are_per_revision(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.set_description(first, "The older one")
    store.set_description(second, "The newer one")
    assert [c.description for c in store.list_changes("home")] == [
        "The newer one",
        "The older one",
    ]


def test_the_state_before_a_change_is_the_previous_one_of_that_dashboard(store):
    # Not the commit's parent: another dashboard's commit can sit in
    # between, and its state is no state of this dashboard at all.
    first = store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("other", "b: 1\n", "other first")
    second = store.write_snapshot("home", "a: 2\n", "home second")
    assert store.previous_change("home", second) == first


def test_the_first_change_has_nothing_before_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.previous_change("home", first) is None


def test_the_state_before_an_unknown_revision_is_unknown(store):
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.previous_change("home", "f" * 40) is None


def test_notes_stay_out_of_the_dashboard_history(store):
    # descriptions live on refs/notes/commits, so the commits that carry
    # them must not turn up as dashboards or as changes. Pinned rather
    # than assumed: list_all_dashboards walks every commit there is, and
    # a stray one there would invent a dashboard out of nothing.
    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(revision, "A note of my own")
    assert store.list_all_dashboards() == ["home"]
    assert len(store.list_changes("home")) == 1
    assert store.list_dashboards() == ["home"]


# -- which recorded states are the one in front of you -----------------
#
# A history that goes back and forth - a card moved up, then down, then up
# again - holds several states with byte-identical content and, because the
# messages are generated, identical wording too. Measured on the test
# installation: seven entries reading "2 moved", every second one identical
# to the live dashboard. Without marking, that list cannot be navigated.


def test_the_revision_holding_the_live_text_is_found(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    assert store.matching_revisions("home", [second, first], "a: 2\n") == {second}


def test_every_revision_with_the_same_content_is_found(store):
    # The back-and-forth case, which is the reason this exists.
    up = store.write_snapshot("home", "a: 1\n", "up")
    down = store.write_snapshot("home", "a: 2\n", "down")
    up_again = store.write_snapshot("home", "a: 1\n", "up again")
    assert store.matching_revisions("home", [up_again, down, up], "a: 1\n") == {
        up,
        up_again,
    }


def test_nothing_matches_a_text_that_was_never_recorded(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.matching_revisions("home", [first], "a: 99\n") == set()


def test_an_unknown_revision_simply_does_not_match(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    assert store.matching_revisions("home", ["f" * 40, first], "a: 1\n") == {first}


def test_matching_reads_only_this_dashboard_s_file(store):
    home = store.write_snapshot("home", "a: 1\n", "home")
    other = store.write_snapshot("other", "b: 2\n", "other")
    # "b: 2" belongs to the other dashboard and was never home's content,
    # at any revision.
    assert store.matching_revisions("home", [other, home], "b: 2\n") == set()
    # And home's own content matches at *both* revisions - including the one
    # whose commit touched another dashboard, because home.yaml still held
    # that text there. That is what "the state at this revision" means, and
    # the caller only ever passes revisions from one dashboard's own history.
    assert store.matching_revisions("home", [other, home], "a: 1\n") == {
        home,
        other,
    }


def test_matching_against_an_empty_repository_is_empty(tmp_path):
    fresh = HistoryStore(tmp_path / "nothing")
    assert fresh.matching_revisions("home", ["abc"], "a: 1\n") == set()


# -- forgetting a dashboard for good -----------------------------------
#
# The one irreversible operation in this project, in a tool built to stop
# things disappearing. It exists because a deleted dashboard stays in the
# list forever, and after enough years that list is mostly gravestones.
#
# git can only really remove something by rewriting history, so every
# revision from the first affected commit onwards changes. Two things hang
# off revisions and would vanish silently: the descriptions people write
# (git notes are keyed by commit sha) and named versions (tags). Carrying
# those across is most of what these tests are about.


def _versions(store):
    return {v.name: v.title for v in store.list_versions()}


def test_forgetting_removes_the_dashboard_from_the_history(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    assert "gone" in store.list_all_dashboards()

    assert store.forget("gone") > 0
    assert "gone" not in store.list_all_dashboards()
    assert store.list_changes("gone") == []


def test_a_forgotten_dashboard_cannot_be_read_at_any_revision(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.forget("gone")
    # Not merely delisted: the text is not in the repository any more.
    assert store.read_at("gone", "HEAD") is None
    assert store.resolve(doomed) is None


def test_forgetting_leaves_another_dashboard_whole(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    store.write_snapshot("gone", "b: 2\n", "gone second")
    store.write_snapshot("home", "a: 3\n", "home third")

    store.forget("gone")
    changes = store.list_changes("home")
    assert [c.message for c in changes] == ["home third", "home second", "home first"]
    assert store.read_at("home", changes[0].revision) == "a: 3\n"
    assert store.read_at("home", changes[1].revision) == "a: 2\n"
    assert store.read_at("home", changes[2].revision) == "a: 1\n"


def test_forgetting_removes_the_metadata_too(store):
    store.write_snapshot("home", "a: 1\n", "home", meta="title: Home\n")
    store.write_snapshot("gone", "b: 1\n", "gone", meta="title: Gone\n")
    store.forget("gone")
    assert store.read_meta_at("gone", "HEAD") is None
    assert store.read_meta_at("home", "HEAD") == "title: Home\n"


def test_a_description_survives_the_rewrite(store):
    first = store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    second = store.write_snapshot("home", "a: 2\n", "home second")
    store.set_description(first, "Before the heating rebuild")
    store.set_description(second, "Sonne oben")

    store.forget("gone")
    # The revisions changed - that is unavoidable - so the descriptions are
    # checked against the messages they belong to, not against shas.
    assert {c.message: c.description for c in store.list_changes("home")} == {
        "home second": "Sonne oben",
        "home first": "Before the heating rebuild",
    }


def test_a_description_on_a_forgotten_change_goes_with_it(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.set_description(doomed, "About the one being forgotten")
    store.forget("gone")
    # Not moved onto a surviving commit: it described a state that is gone,
    # and a description on the wrong state is worse than none.
    assert "About the one being forgotten" not in store.descriptions().values()


def test_a_named_version_survives_the_rewrite(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    store.create_version("v1", "First release", "what it is about")

    store.forget("gone")
    assert _versions(store) == {"v1": "First release"}
    # And it still points at a commit that exists.
    version = store.list_versions()[0]
    assert store.resolve(version.revision) == version.revision


def test_a_version_of_the_forgotten_dashboard_goes_with_it(store):
    # Decision 13 of the design record made a version belong to ONE
    # dashboard. Moving it to the nearest surviving ancestor was right
    # while it marked a moment of the whole history; measured afterwards,
    # `gone/v1.0.0` survived a forget and pointed at `home`'s commit -
    # `read_at` answered None for it, and the numbering for a future
    # `gone` counted up from a version nobody could reach.
    home = store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.create_version("gone/v1.0.0", "The one being forgotten", "", doomed)
    store.create_version("home/v1.0.0", "The one that stays", "", home)

    store.forget("gone")
    assert _versions(store) == {"home/v1.0.0": "The one that stays"}
    assert store.list_versions("gone") == []
    # And nothing left behind points at a stranger's commit: every
    # surviving version marks a state of the dashboard it names.
    for version in store.list_versions():
        key, _, _ = version.name.partition("/")
        assert store.read_at(key, version.revision) is not None


def test_a_lightweight_tag_is_rewritten_rather_than_left_stale(store):
    # The ref that defeated `forget` entirely. It has no tag object, so
    # the old collection skipped it and left it pointing into the history
    # that was supposed to be gone.
    store.write_snapshot("home", "a: 1\n", "home first")
    doomed = store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 2\n", "home second")
    _lightweight_tag(store, "by-hand", doomed)

    store.forget("gone")
    repo = Repo(str(store.path))
    try:
        left = list(repo.refs.as_dict(b"refs/tags").values())
        alive = {entry.commit.id for entry in repo.get_walker()}
    finally:
        repo.close()
    # Every surviving tag stands on the rewritten history. `resolve` is no
    # test of that: it finds an unreachable commit just as happily, which
    # is precisely why such a ref kept the forgotten objects from being
    # pruned.
    assert left
    for sha in left:
        assert sha in alive, f"{_as_text(sha)} is not in the rewritten history"


def test_forgetting_an_unknown_dashboard_changes_nothing(store):
    store.write_snapshot("home", "a: 1\n", "home first")
    before = [c.revision for c in store.list_changes("home")]
    assert store.forget("never-existed") == 0
    assert [c.revision for c in store.list_changes("home")] == before


def test_forgetting_the_only_dashboard_empties_the_history(store):
    store.write_snapshot("only", "a: 1\n", "only first")
    store.write_snapshot("only", "a: 2\n", "only second")
    assert store.forget("only") == 2
    assert store.list_all_dashboards() == []
    assert store.list_changes("only") == []
    # And the repository is still usable afterwards.
    assert store.write_snapshot("fresh", "c: 1\n", "fresh") is not None


def test_forgetting_is_refused_for_nothing_and_survives_an_empty_repo(tmp_path):
    fresh = HistoryStore(tmp_path / "nothing")
    assert fresh.forget("home") == 0


def _lightweight_tag(store, name: str, revision: str) -> None:
    """A tag made by hand: a ref straight to the commit, no tag object.

    Exactly what somebody gets from `git tag <name>` in the repository the
    README invites them to look inside, and decision 13 of the design
    record says such a tag stays visible.
    """
    repo = Repo(str(store.path))
    try:
        repo.refs[f"refs/tags/{name}".encode()] = revision.encode()
    finally:
        repo.close()


def _blobs(store) -> list[bytes]:
    repo = Repo(str(store.path))
    try:
        return [
            repo[sha].data for sha in repo.object_store if repo[sha].type_name == b"blob"
        ]
    finally:
        repo.close()


def test_the_forgotten_text_is_gone_from_the_object_store(store):
    # The literal reading of "for good". Rewriting refs alone leaves every
    # blob on disk, unreachable but readable by anyone who knows a sha -
    # and `resolve` knows how to find them. This is the check that the
    # promise is kept and not merely made.
    #
    # With a lightweight tag in the way, because that is what defeated it:
    # `_raw_tags` collected only annotated tags, so a hand-made one was
    # neither deleted nor rewritten, went on pointing at a pre-rewrite
    # commit, and kept the whole old history reachable - garbage_collect
    # prunes nothing a ref can still reach. Measured before the fix:
    # `forget` reported success and the text below was still readable.
    store.write_snapshot("home", "a: 1\n", "home")
    doomed = store.write_snapshot("gone", "confidential: yes\n", "gone")
    _lightweight_tag(store, "made-by-hand", doomed)
    store.forget("gone")

    blobs = _blobs(store)
    assert blobs, "the surviving dashboard should still have its blob"
    assert not any(b"confidential" in blob for blob in blobs)


def test_versions_can_be_asked_for_one_dashboard(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("solar", "b: 1\n", "solar first")
    store.create_version("home/v1.0.0", "Home", "", first)
    store.create_version("solar/v1.0.0", "Solar", "", second)
    assert [v.name for v in store.list_versions("home")] == ["home/v1.0.0"]
    assert [v.name for v in store.list_versions("solar")] == ["solar/v1.0.0"]
    assert len(store.list_versions()) == 2


def test_the_same_version_twice_is_refused(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Home", "", first)
    with pytest.raises(ValueError, match="already exists"):
        store.create_version("home/v1.0.0", "Again", "", first)


def test_a_flat_tag_blocks_the_namespace_below_it(store):
    # git cannot hold a tag `home` and a tag `home/v1.0.0` at once - the
    # ref file and the ref directory are the same path. Measured: dulwich
    # raises IsADirectoryError and leaves a stray .lock behind, so this is
    # refused up front rather than suffered.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home", "Loose", "", first)
    with pytest.raises(ValueError, match="home"):
        store.create_version("home/v1.0.0", "Blocked", "", first)


def test_a_namespace_blocks_the_flat_tag_above_it(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    with pytest.raises(ValueError, match="home/v1.0.0"):
        store.create_version("home", "Loose", "", first)


def test_a_lightweight_tag_in_a_namespace_is_reported(store):
    # `list_versions` used to skip it, so `candidates` never saw it and
    # offered its number again - and `_refuse_colliding_name`, which reads
    # the raw refs, then refused in the middle of the dialog. Decision 13
    # of the design record promises such a tag is shown, not hidden.
    first = store.write_snapshot("heizung", "a: 1\n", "first")
    _lightweight_tag(store, "heizung/v1.0.0", first)

    listed = store.list_versions("heizung")
    assert [v.name for v in listed] == ["heizung/v1.0.0"]
    # No message on a lightweight tag, so nothing to show as title or text.
    assert (listed[0].title, listed[0].description) == ("", "")
    assert listed[0].revision == first

    # And therefore no refusal mid-dialog: what the buttons offer is free.
    offered = candidates("heizung", [v.name for v in listed])
    assert offered["current"] == "heizung/v1.0.0"
    store.create_version(offered["patch"], "Next", "", first)
    assert offered["patch"] in _versions(store)


def test_a_name_git_cannot_accept_is_refused_as_an_answer(store):
    # dulwich raises RefFormatError, which inherits straight from
    # Exception: `operations.py` catches ValueError, the WebSocket wrapper
    # swallows what escapes and `services.py` does not. A name git cannot
    # accept is the same class of answer as a name that collides, so it
    # leaves this module as the same kind of exception.
    first = store.write_snapshot("home", "a: 1\n", "first")
    with pytest.raises(ValueError, match="git cannot use that as a version name"):
        store.create_version("home/v1 0.0", "Spaces", "", first)
    with pytest.raises(ValueError, match="git cannot use that as a version name"):
        store.create_version("home/v1.0.0^", "Caret", "", first)
    # Nothing half-made left behind.
    assert store.list_versions() == []


def test_a_deletion_commit_holds_no_state_to_return_to(store):
    # The fact under the refusal in `operations.async_create_version`: at
    # the commit that records a deletion the dashboard's file has left the
    # tree, so there is no state there anybody could come back to - and
    # that commit is the newest entry in a deleted dashboard's history,
    # which is exactly where a version without a revision would land.
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.mark_deleted("gone", "gone: dashboard deleted")
    newest = store.list_changes("gone")[0]

    # A known revision - the separation `_state_at` makes matters here:
    # this is a statement about the dashboard, not about the input.
    assert store.resolve(newest.revision) == newest.revision
    assert store.read_at("gone", newest.revision) is None
    # The state before it is still there, and that one can be marked.
    before = store.previous_change("gone", newest.revision)
    assert store.read_at("gone", before) == "b: 1\n"


def _tree_and_blob(store, key: str, revision: str) -> tuple[str, str]:
    """The tree and blob ids behind one recorded state.

    Both are ordinary git objects sitting in the same object store as the
    commits, so both answer to a full id and to an abbreviated prefix.
    """
    repo = Repo(str(store.path))
    try:
        tree = repo[revision.encode()].tree
        _, blob = repo[tree].lookup_path(repo.get_object, f"{key}.yaml".encode())
        return _as_text(tree), _as_text(blob)
    finally:
        repo.close()


def test_an_object_that_is_not_a_commit_resolves_to_nothing(store):
    # A blob and a tree used to resolve to themselves, and every caller
    # then treated the answer as a commit: `read_at` reaches for `.tree`
    # and raised AttributeError - a generic failure through the WebSocket,
    # a bare traceback through `services.py`. Worse, `create_version`
    # accepted one and made a tag that can never be returned to, and
    # versions cannot be deleted. None already means "unknown revision" to
    # every caller, so that is what these are now.
    first = store.write_snapshot("home", "a: 1\n", "first")
    tree, blob = _tree_and_blob(store, "home", first)

    assert store.resolve(blob) is None
    assert store.resolve(tree) is None
    # The abbreviated form is the one a person is likely to paste.
    assert store.resolve(blob[:8]) is None
    assert store.resolve(tree[:8]) is None
    # And nothing downstream crashes on one.
    assert store.read_at("home", blob) is None
    assert store.read_at("home", tree) is None
    assert store.previous_change("home", blob) is None

    with pytest.raises(ValueError, match="unknown revision"):
        store.create_version("home/v1.0.0", "On a blob", "", blob)
    with pytest.raises(ValueError, match="unknown revision"):
        store.create_version("home/v1.0.1", "On a tree", "", tree)
    # Nothing half-made left behind: a version that cannot be returned to
    # would sit in the list forever.
    assert store.list_versions() == []


def test_a_lightweight_tag_on_a_blob_is_not_a_state_to_return_to(store):
    # The second route to the same fault, and one nobody has to type: a
    # tag made by hand in the repository the README invites people to look
    # inside. `list_versions` reports it, as decision 13 of the design
    # record promises, so its revision travels straight into `read_at`.
    first = store.write_snapshot("home", "a: 1\n", "first")
    _, blob = _tree_and_blob(store, "home", first)
    _lightweight_tag(store, "home/v1.0.0", blob)

    listed = store.list_versions("home")
    assert [v.name for v in listed] == ["home/v1.0.0"]
    # No crash, and no pretence that there is a state there.
    assert store.read_at("home", listed[0].revision) is None
    assert store.resolve("home/v1.0.0") is None
    assert store.read_at("home", "home/v1.0.0") is None


def test_a_tag_blocks_every_namespace_it_stands_in(store):
    # A dashboard key may hold a slash - Home Assistant accepts
    # `url_path="dh-slash/check"` - and then the blocking parent of
    # `dh-slash/check/v1.0.0` is `dh-slash/check`, not `dh-slash`. Looking
    # only at the first segment let the real collision through, and it
    # then surfaced raw: measured on dulwich 1.2.14 it is a
    # NotADirectoryError here, the deeper cousin of the IsADirectoryError
    # this refusal was written against.
    first = store.write_snapshot("dh-slash/check", "a: 1\n", "first")
    store.create_version("dh-slash/check", "Loose", "", first)
    with pytest.raises(ValueError, match="dh-slash/check"):
        store.create_version("dh-slash/check/v1.0.0", "Blocked", "", first)


def test_a_tag_in_the_first_segment_still_blocks(store):
    # The other end of the same name: `dh-slash` is a proper prefix too,
    # so it blocks just as it always did for a key without a slash.
    first = store.write_snapshot("dh-slash/check", "a: 1\n", "first")
    store.create_version("dh-slash", "Loose", "", first)
    with pytest.raises(ValueError, match="dh-slash"):
        store.create_version("dh-slash/check/v1.0.0", "Blocked", "", first)
