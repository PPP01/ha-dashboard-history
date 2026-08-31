"""Tests for the decisions about dashboard identity and absence.

These three functions used to live inside the modules that import Home
Assistant, where no test could reach them. Two of them had already gone
wrong there, which is why they are here now: the storage-key mapping
confused a dashboard's id with its url_path, and the deletion rule is one
where a mistake wipes every history at once.
"""

import keys


def test_the_id_and_the_url_path_are_kept_apart():
    # Real data from the installation this was built against: url_path
    # "energie-2" is stored under the id "energie_2". Treating them as the
    # same string files one dashboard under two names.
    assert keys.storage_keys([{"id": "energie_2", "url_path": "energie-2"}], "_default") == [
        ("_default", "lovelace"),
        ("energie-2", "lovelace.energie_2"),
    ]


def test_the_default_dashboard_has_a_bare_storage_key():
    # Not "lovelace.lovelace": Home Assistant stores the default dashboard
    # under a plain "lovelace".
    assert keys.storage_keys([], "_default") == [("_default", "lovelace")]


def test_incomplete_registry_entries_are_skipped():
    assert keys.storage_keys([{"id": "x"}, {"url_path": "y"}, {}], "_default") == [
        ("_default", "lovelace")
    ]


def test_a_registry_of_none_is_survivable():
    assert keys.storage_keys(None, "_default") == [("_default", "lovelace")]


def test_a_dashboard_no_longer_known_counts_as_deleted():
    assert keys.deletions_to_record(["a", "b"], {"a"}) == ["b"]


def test_nothing_is_recorded_when_home_assistant_cannot_be_asked():
    # The catastrophic case. "I could not look" must never turn into
    # "all of them are gone".
    assert keys.deletions_to_record(["a", "b"], None) == []


def test_an_extra_dashboard_is_not_a_deletion():
    assert keys.deletions_to_record(["a"], {"a", "b"}) == []


def test_deletions_come_in_a_stable_order():
    assert keys.deletions_to_record(["c", "a", "b"], set()) == ["a", "b", "c"]


def test_a_known_and_tracked_dashboard_is_live():
    assert keys.is_live("a", ["a"], {"a"}) is True


def test_a_tracked_but_unknown_dashboard_is_not_live():
    assert keys.is_live("a", ["a"], {"b"}) is False


def test_nothing_is_declared_gone_when_the_question_cannot_be_answered():
    assert keys.is_live("a", ["a"], None) is True


def test_an_untracked_dashboard_is_not_live():
    assert keys.is_live("a", [], {"a"}) is False


def test_absence_is_not_the_same_question_as_liveness():
    # A dashboard Home Assistant has but we never recorded: not live by our
    # reckoning, but very much not absent. Confusing the two would try to
    # create a dashboard that already exists.
    assert keys.is_live("a", [], {"a"}) is False
    assert keys.is_absent("a", {"a"}) is False


def test_a_dashboard_home_assistant_does_not_have_is_absent():
    assert keys.is_absent("a", {"b"}) is True


def test_nothing_is_absent_when_home_assistant_cannot_be_asked():
    assert keys.is_absent("a", None) is False
