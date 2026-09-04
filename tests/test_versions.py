"""Tests for version numbers: reading, ordering, counting up."""

import pytest
import versions
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


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


# -- the day a state belongs to ----------------------------------------

BERLIN = ZoneInfo("Europe/Berlin")


def _at(text: str, zone=BERLIN) -> int:
    """A local wall-clock time as the epoch seconds a commit would hold."""
    return int(datetime.fromisoformat(text).replace(tzinfo=zone).timestamp())


def test_two_states_on_one_local_day_are_one_day():
    assert versions.same_day(_at("2026-09-03T08:00"), _at("2026-09-03T23:59"), BERLIN)


def test_midnight_starts_a_new_day():
    assert not versions.same_day(
        _at("2026-09-03T23:59"), _at("2026-09-04T00:01"), BERLIN
    )


def test_the_day_is_the_users_day_and_not_utc():
    # 23:30 UTC is already the next day in Berlin. Judged in UTC these two
    # states fall on one day; judged where the person lives, on two. The
    # daily version is named after the day *they* had.
    morning = _at("2026-09-03T07:00", timezone.utc)
    late = _at("2026-09-03T23:30", timezone.utc)
    assert versions.same_day(morning, late, timezone.utc)
    assert not versions.same_day(morning, late, BERLIN)


def test_the_clocks_going_forward_do_not_split_a_day():
    # 2026-03-29: Berlin skips 02:00-03:00. A day is still one day.
    assert versions.same_day(_at("2026-03-29T01:30"), _at("2026-03-29T03:30"), BERLIN)


def test_the_clocks_going_back_do_not_join_two_days():
    # 2026-10-25: Berlin lives 02:00-03:00 twice. Two days stay two.
    assert not versions.same_day(
        _at("2026-10-25T02:30"), _at("2026-10-26T02:30"), BERLIN
    )


def test_the_title_is_the_day_it_marks():
    assert versions.day_title(_at("2026-09-03T21:15"), BERLIN) == "3 September 2026"


def test_the_title_follows_the_local_day_too():
    stamp = _at("2026-09-03T22:15", timezone.utc)
    assert versions.day_title(stamp, timezone.utc) == "3 September 2026"
    assert versions.day_title(stamp, BERLIN) == "4 September 2026"


def test_the_month_is_english_whatever_the_container_thinks():
    # Deliberately not strftime("%B"), which follows the C locale of
    # whatever container Home Assistant runs in - the same tag would then
    # read differently on two installations.
    assert versions.day_title(_at("2026-01-09T12:00"), BERLIN) == "9 January 2026"
    assert versions.day_title(_at("2026-12-31T12:00"), BERLIN) == "31 December 2026"


# -- versions nobody asked for -----------------------------------------


def test_an_automatic_version_says_that_it_is_one():
    assert versions.read_description(versions.automatic_description()) == ("", True)


def test_a_persons_own_description_is_not_marked():
    assert versions.read_description("Before the heating rework") == (
        "Before the heating rework",
        False,
    )


def test_the_marker_is_never_shown_to_anybody():
    # It is bookkeeping. A list that prints its own bookkeeping is one
    # nobody trusts.
    text = versions.automatic_description("The last state of that day.")
    assert versions.read_description(text) == ("The last state of that day.", True)
    assert versions.AUTOMATIC not in versions.read_description(text)[0]


def test_an_empty_description_is_nobodys_words():
    assert versions.read_description("") == ("", False)
