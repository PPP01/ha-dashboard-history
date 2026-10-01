"""Tests for how many changes a dashboard holds that no version carries."""

import pytest
from dulwich.repo import Repo
from store import ForgetRaceExhausted, HistoryStore


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def counts(store):
    """The counts as the panel gets them: out of the listing."""
    return store.dashboard_listing()[1]


def test_a_store_without_a_repository_answers_nothing(tmp_path):
    survey, found = HistoryStore(tmp_path / "nothing").dashboard_listing()
    assert survey.names == [] and survey.live == set()
    assert found == {}


def test_a_repository_without_a_commit_answers_nothing(store):
    # `ensure()` made the repository, nothing has been recorded yet: no
    # HEAD, so no index to read. Not the same case as no repository.
    survey, found = store.dashboard_listing()
    assert survey.names == [] and found == {}


def test_without_any_version_every_change_counts(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    store.write_snapshot("home", "a: 3\n", "third")
    assert counts(store) == {"home": 3}


def test_a_version_on_the_newest_change_leaves_nothing_unversioned(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", newest)
    assert counts(store) == {"home": 0}


def test_only_changes_newer_than_the_newest_version_count(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.write_snapshot("home", "a: 3\n", "third")
    store.write_snapshot("home", "a: 4\n", "fourth")
    store.create_version("home/v1.0.0", "First", "", first)
    store.create_version("home/v1.0.1", "Second", "", second)
    # Two states sit in front of the newest version, not three: the
    # older version does not add to it.
    assert counts(store) == {"home": 2}


def test_dashboards_are_counted_apart(store):
    home = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    store.write_snapshot("other", "b: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", home)
    assert counts(store) == {"home": 0, "other": 2}


def test_another_dashboards_version_does_not_tidy_this_one(store):
    home = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    # A tag belongs to the key in its name, wherever it points.
    store.create_version("other/v1.0.0", "Odd", "", home)
    assert counts(store)["home"] == 1


def test_two_versions_on_one_state_count_once(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "One", "", newest)
    store.create_version("home/v1.0.1", "Two", "", newest)
    assert counts(store) == {"home": 0}


def test_a_new_version_is_seen_on_the_next_call(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    assert counts(store) == {"home": 2}
    # HEAD did not move between the two calls: a tag does not move it.
    store.create_version("home/v1.0.0", "First", "", newest)
    assert counts(store) == {"home": 0}


def test_a_removed_version_is_noticed_on_the_next_call(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", newest)
    assert counts(store) == {"home": 0}
    store.remove_version("home", "home/v1.0.0")
    assert counts(store) == {"home": 2}


def test_a_change_after_the_version_is_counted(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    assert counts(store) == {"home": 0}
    store.write_snapshot("home", "a: 2\n", "second")
    assert counts(store) == {"home": 1}


def test_an_unchanged_version_is_not_read_again(store, monkeypatch):
    # The point of `_tag_targets`: loading every tag object costs half a
    # second at a year of automatic versions, and the panel asks on every
    # recorded change. A refactoring that drops the cache would still pass
    # every test above; this one is what fails.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    counts(store)  # fills the cache
    tags = set(Repo(str(store.path)).refs.as_dict(b"refs/tags").values())
    assert tags
    looked_up = []
    original = Repo.__getitem__

    def spying(self, name):
        looked_up.append(name)
        return original(self, name)

    monkeypatch.setattr(Repo, "__getitem__", spying)
    counts(store)
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


def test_the_listing_never_mixes_names_and_counts_of_two_generations(store):
    store.write_snapshot("gone", "a: 1\n", "gone")
    home = store.write_snapshot("home", "a: 1\n", "home")
    store.create_version("home/v1.0.0", "First", "", home)
    _forget_once_between_the_two_reads(store, "gone")
    survey, found = store.dashboard_listing()
    assert survey.names == ["home"]
    assert found == {"home": 0}


def test_an_unfinished_forget_costs_the_listing_its_counts_not_its_names(store):
    # The counts are a decoration on the list. While a `forget` is
    # unfinished - or its checkpoint was left behind by a crash - the
    # retry cannot trust any attempt and gives up; the list of
    # dashboards must still load, only without the counts.
    store.write_snapshot("home", "a: 1\n", "first")
    store._checkpoint_path().write_text("{}")
    assert store.forget_in_progress()
    repo = store._repo()
    with pytest.raises(ForgetRaceExhausted):
        store._retrying_a_forget_race(repo, lambda: store._count_unversioned(repo))
    survey, found = store.dashboard_listing()
    assert survey.names == ["home"]
    assert found == {}


def test_a_fault_in_the_count_is_not_mistaken_for_an_unfinished_forget(store):
    # Only an exhausted retry is made up for. A RuntimeError from
    # anywhere below it is a fault, and the list must say so.
    store.write_snapshot("home", "a: 1\n", "first")

    def broken(repo):
        raise RuntimeError("a fault in the count")

    store._count_unversioned = broken
    with pytest.raises(RuntimeError, match="a fault in the count"):
        store.dashboard_listing()


def test_a_state_that_is_a_versions_content_again_is_not_unversioned(store):
    # A card moved out and home again: three recorded states, the newest
    # byte-identical to the one the version sits on. The panel's "Right
    # now" card says "same state as v1.0.0" here, and so must the list.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    store.write_snapshot("home", "a: 2\n", "moved out")
    store.write_snapshot("home", "a: 1\n", "moved home")
    assert counts(store) == {"home": 0}


def test_going_back_to_an_older_version_is_not_unversioned(store):
    # Equal to *any* of the versions counts, not only the newest one:
    # the "Right now" card lists every version holding the state.
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", first)
    store.create_version("home/v1.0.1", "Second", "", second)
    store.write_snapshot("home", "a: 1\n", "went back")
    assert counts(store) == {"home": 0}


def test_a_state_no_version_holds_is_still_counted(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    store.write_snapshot("home", "a: 2\n", "second")
    store.write_snapshot("home", "a: 3\n", "third")
    assert counts(store) == {"home": 2}


def test_another_dashboards_version_with_the_same_text_does_not_count(store):
    # Two dashboards holding identical text: the version belongs to the
    # one it is named for, so the other is still unversioned.
    store.write_snapshot("home", "a: 1\n", "first")
    other = store.write_snapshot("other", "a: 1\n", "first")
    store.create_version("other/v1.0.0", "First", "", other)
    assert counts(store) == {"home": 1, "other": 0}


def test_a_state_read_once_is_not_read_again(store, monkeypatch):
    # Reading what a path holds at a revision is a tree lookup apiece,
    # and the answer never changes. A second call asks for none.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    store.write_snapshot("home", "a: 2\n", "second")
    asked = []
    original = HistoryStore._blob_at

    def counting(repo, path, revision):
        asked.append((path, revision))
        return original(repo, path, revision)

    monkeypatch.setattr(store, "_blob_at", counting)
    assert counts(store) == {"home": 1}
    # The spy is live: the first call did have to read.
    assert asked
    asked.clear()
    assert counts(store) == {"home": 1}
    assert asked == []
