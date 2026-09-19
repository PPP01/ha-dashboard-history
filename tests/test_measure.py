"""Tests for what the history costs and holds."""

import pytest
from store import HistoryStore, Measurement


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def test_an_empty_history_measures_as_empty(store):
    found = store.measure()
    assert found.revisions == 0
    assert found.oldest is None
    assert found.newest is None
    assert found.newest_key is None
    assert found.dashboards == ()


def test_a_store_without_a_repository_does_not_raise(tmp_path):
    found = HistoryStore(tmp_path / "nothing").measure()
    assert isinstance(found, Measurement)
    assert found.revisions == 0


def test_revisions_are_counted_across_dashboards(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.measure().revisions == 3


def test_the_newest_commit_is_named_with_its_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    found = store.measure()
    assert found.newest_key == "other"
    assert found.newest >= found.oldest


def test_versions_are_counted_without_reading_the_tags(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "")
    store.write_snapshot("other", "b: 1\n", "first")
    store.create_version("other/v1.0.0", "First", "")
    assert store.measure().versions == 2

import os


def _walked(path):
    """Sum the same tree independently, for the test to compare against."""
    logical = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            logical += os.lstat(os.path.join(root, name)).st_size
    return logical


def test_the_logical_size_is_the_sum_of_every_file(store):
    store.write_snapshot("home", "a: 1\n", "first")
    found = store.measure()
    assert found.bytes_logical == _walked(store.path)


def test_git_and_worktree_add_up_to_the_whole(store):
    store.write_snapshot("home", "a: 1\n", "first")
    found = store.measure()
    assert found.bytes_git_logical + found.bytes_worktree_logical == found.bytes_logical
    assert found.bytes_worktree_logical > 0


def test_allocated_size_is_whole_blocks_or_absent(store):
    store.write_snapshot("home", "a: 1\n", "first")
    allocated = store.measure().bytes_allocated
    assert allocated is None or allocated % 512 == 0


def test_loose_objects_are_counted_and_packing_moves_them(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    before = store.measure()
    assert before.loose_objects > 0
    assert before.packs == 0

    from dulwich.repo import Repo

    with Repo(str(store.path)) as repo:
        repo.object_store.pack_loose_objects()
    after = store.measure()
    assert after.packs >= 1
    assert after.loose_objects < before.loose_objects


def test_each_dashboard_gets_a_row_sorted_by_revisions(store):
    store.write_snapshot("quiet", "a: 1\n", "first")
    for n in range(3):
        store.write_snapshot("busy", f"b: {n}\n", f"change {n}")
    rows = store.measure().dashboards
    assert [row.key for row in rows] == ["busy", "quiet"]
    assert rows[0].revisions == 3
    assert rows[1].revisions == 1
    assert all(not row.gone for row in rows)


def test_a_live_dashboard_reports_the_length_of_its_current_state(store):
    text = "a: 1\nb: 2\n"
    store.write_snapshot("home", text, "first")
    row = store.measure().dashboards[0]
    assert row.bytes == len(text.encode("utf-8"))


def test_a_deleted_dashboard_reports_what_a_restore_would_bring_back(store):
    text = "a: 1\nb: 2\nc: 3\n"
    store.write_snapshot("home", text, "first")
    store.mark_deleted("home", "home was deleted")
    row = store.measure().dashboards[0]
    assert row.gone is True
    # Not the deletion commit, which holds no dashboard text at all.
    assert row.bytes == len(text.encode("utf-8"))


def test_first_and_last_bracket_a_dashboards_own_commits(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    row = store.measure().dashboards[0]
    assert row.first <= row.last


def test_versions_are_attributed_to_their_own_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "")
    rows = {row.key: row for row in store.measure().dashboards}
    assert rows["home"].versions == 1
    assert rows["other"].versions == 0
