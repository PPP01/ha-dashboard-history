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
