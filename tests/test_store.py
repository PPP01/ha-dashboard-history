"""Tests for the git-backed history store."""

import threading

import pytest
from dulwich.repo import Repo
from store import HistoryStore


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
