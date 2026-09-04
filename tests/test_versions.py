"""Tests for version numbers: reading, ordering, counting up."""

import pytest
import versions


def test_a_name_is_read_back():
    assert versions.parse("heizung", "heizung/v1.2.3") == (1, 2, 3)


def test_another_dashboards_version_is_not_ours():
    assert versions.parse("heizung", "solar/v1.2.3") is None


def test_a_hand_made_tag_is_not_a_version():
    assert versions.parse("heizung", "heizung/before-the-rework") is None
    assert versions.parse("heizung", "heizung/v1.2") is None
    assert versions.parse("heizung", "heizung/v1.2.3-beta") is None
    assert versions.parse("heizung", "heizung/v01.2.3") is None


def test_the_default_dashboard_key_works():
    # The default dashboard is stored under "_default"; an underscore is
    # legal in a ref name and must not be treated as a special case.
    assert versions.parse("_default", "_default/v0.0.1") == (0, 0, 1)


def test_ordering_is_numeric_not_alphabetical():
    # The classic: as text, "v1.10.0" sorts below "v1.9.0".
    names = ["heizung/v1.9.0", "heizung/v1.10.0", "heizung/v1.2.0"]
    assert versions.latest("heizung", names) == (1, 10, 0)


def test_unusable_names_do_not_shift_the_count():
    names = ["heizung/v1.0.0", "heizung/hand-made", "solar/v9.9.9"]
    assert versions.latest("heizung", names) == (1, 0, 0)


def test_a_dashboard_without_versions_has_no_latest():
    assert versions.latest("heizung", ["solar/v1.0.0"]) is None


def test_the_three_candidates():
    names = ["heizung/v1.2.3"]
    assert versions.candidates("heizung", names) == {
        "patch": "heizung/v1.2.4",
        "minor": "heizung/v1.3.0",
        "major": "heizung/v2.0.0",
        "current": "heizung/v1.2.3",
    }


def test_the_first_version_counts_from_zero():
    assert versions.candidates("heizung", []) == {
        "patch": "heizung/v0.0.1",
        "minor": "heizung/v0.1.0",
        "major": "heizung/v1.0.0",
        "current": None,
    }


def test_bumping_resets_what_is_below_it():
    assert versions.bump((1, 2, 3), "patch") == (1, 2, 4)
    assert versions.bump((1, 2, 3), "minor") == (1, 3, 0)
    assert versions.bump((1, 2, 3), "major") == (2, 0, 0)


def test_an_unknown_level_is_refused():
    with pytest.raises(ValueError):
        versions.bump((1, 2, 3), "enormous")


class _Named:
    """A stand-in for the store's Version: all `by_number` reads is a name."""

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return self.name


def test_ordering_by_number_is_numeric_not_alphabetical():
    # The same classic as above, now for the whole list rather than the top.
    marks = [_Named(f"heizung/v{n}") for n in ("1.9.0", "1.10.0", "1.2.0")]
    assert [v.name for v in versions.by_number("heizung", marks)] == [
        "heizung/v1.10.0",
        "heizung/v1.9.0",
        "heizung/v1.2.0",
    ]


def test_a_name_that_will_not_parse_sorts_last():
    # Last, not first: a hand-made tag must never look like the newest
    # version, and (-1, -1, -1) is below every real number including 0.0.0.
    marks = [_Named("heizung/hand-made"), _Named("heizung/v0.0.0")]
    assert [v.name for v in versions.by_number("heizung", marks)] == [
        "heizung/v0.0.0",
        "heizung/hand-made",
    ]


def test_another_dashboards_version_sorts_last_too():
    # It parses as a version, just not as one of ours - so it must not
    # decide the order of a list it does not belong to.
    marks = [_Named("solar/v9.9.9"), _Named("heizung/v1.0.0")]
    assert [v.name for v in versions.by_number("heizung", marks)] == [
        "heizung/v1.0.0",
        "solar/v9.9.9",
    ]


def test_ordering_an_empty_list_is_not_an_error():
    assert versions.by_number("heizung", []) == []
