"""Tests for how many changes a dashboard holds that no version carries."""

import pytest
from dulwich.repo import Repo
from store import HistoryStore


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def test_a_store_without_a_repository_answers_nothing(tmp_path):
    nothing = HistoryStore(tmp_path / "nothing")
    assert nothing.unversioned_counts() == {}
    survey, counts = nothing.dashboard_listing()
    assert survey.names == [] and survey.live == set()
    assert counts == {}


def test_a_repository_without_a_commit_answers_nothing(store):
    # `ensure()` made the repository, nothing has been recorded yet: no
    # HEAD, so no index to read. Not the same case as no repository.
    assert store.unversioned_counts() == {}
    survey, counts = store.dashboard_listing()
    assert survey.names == [] and counts == {}


def test_without_any_version_every_change_counts(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    store.write_snapshot("home", "a: 3\n", "third")
    assert store.unversioned_counts() == {"home": 3}


def test_a_version_on_the_newest_change_leaves_nothing_unversioned(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", newest)
    assert store.unversioned_counts() == {"home": 0}


def test_only_changes_newer_than_the_newest_version_count(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.write_snapshot("home", "a: 3\n", "third")
    store.write_snapshot("home", "a: 4\n", "fourth")
    store.create_version("home/v1.0.0", "First", "", first)
    store.create_version("home/v1.0.1", "Second", "", second)
    # Two states sit in front of the newest version, not three: the
    # older version does not add to it.
    assert store.unversioned_counts() == {"home": 2}


def test_dashboards_are_counted_apart(store):
    home = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    store.write_snapshot("other", "b: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", home)
    assert store.unversioned_counts() == {"home": 0, "other": 2}


def test_another_dashboards_version_does_not_tidy_this_one(store):
    home = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    # A tag belongs to the key in its name, wherever it points.
    store.create_version("other/v1.0.0", "Odd", "", home)
    assert store.unversioned_counts()["home"] == 1


def test_two_versions_on_one_state_count_once(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "One", "", newest)
    store.create_version("home/v1.0.1", "Two", "", newest)
    assert store.unversioned_counts() == {"home": 0}


def test_a_new_version_is_seen_on_the_next_call(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    assert store.unversioned_counts() == {"home": 2}
    # HEAD did not move between the two calls: a tag does not move it.
    store.create_version("home/v1.0.0", "First", "", newest)
    assert store.unversioned_counts() == {"home": 0}


def test_a_removed_version_is_noticed_on_the_next_call(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", newest)
    assert store.unversioned_counts() == {"home": 0}
    store.remove_version("home", "home/v1.0.0")
    assert store.unversioned_counts() == {"home": 2}


def test_a_change_after_the_version_is_counted(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    assert store.unversioned_counts() == {"home": 0}
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.unversioned_counts() == {"home": 1}


def test_an_unchanged_version_is_not_read_again(store, monkeypatch):
    # The point of `_tag_targets`: loading every tag object costs half a
    # second at a year of automatic versions, and the panel asks on every
    # recorded change. A refactoring that drops the cache would still pass
    # every test above; this one is what fails.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    store.unversioned_counts()  # fills the cache
    tags = set(Repo(str(store.path)).refs.as_dict(b"refs/tags").values())
    assert tags
    looked_up = []
    original = Repo.__getitem__

    def spying(self, name):
        looked_up.append(name)
        return original(self, name)

    monkeypatch.setattr(Repo, "__getitem__", spying)
    store.unversioned_counts()
    # The spy is live (commits are still looked up through it) and the
    # tag objects are not among what it saw.
    assert looked_up
    assert not tags & set(looked_up)


def _forget_once_between_the_two_reads(store, forgotten):
    """Make a `forget` run exactly between reading the index and the refs.

    The same interruption a second executor thread causes, without a
    thread: the first call of `_marked_revisions` runs `forget` first,
    then reads as usual. Once only, so a retry reads undisturbed.
    """
    original = store._marked_revisions

    def interrupted(repo):
        store._marked_revisions = original
        store.forget(forgotten)
        return original(repo)

    store._marked_revisions = interrupted


def test_a_forget_between_the_two_reads_cannot_mix_generations(store):
    store.write_snapshot("gone", "a: 1\n", "gone")
    home = store.write_snapshot("home", "a: 1\n", "home")
    store.create_version("home/v1.0.0", "First", "", home)
    _forget_once_between_the_two_reads(store, "gone")
    # Without the retry this is {"gone": 1, "home": 1}: the index still
    # holds the commits from before the rewrite, the tags already point
    # at the new ones, and nothing matches.
    assert store.unversioned_counts() == {"home": 0}


def test_the_listing_never_mixes_names_and_counts_of_two_generations(store):
    store.write_snapshot("gone", "a: 1\n", "gone")
    home = store.write_snapshot("home", "a: 1\n", "home")
    store.create_version("home/v1.0.0", "First", "", home)
    _forget_once_between_the_two_reads(store, "gone")
    survey, counts = store.dashboard_listing()
    assert survey.names == ["home"]
    assert counts == {"home": 0}
