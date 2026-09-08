"""Tests for version numbers: reading, ordering, counting up."""

import pytest
import versions
from datetime import date, datetime, timezone
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


def test_the_highest_numbered_version_is_picked_out():
    marks = [_Named(f"heizung/v{n}") for n in ("1.9.0", "1.10.0", "1.2.0")]
    assert versions.highest("heizung", marks).name == "heizung/v1.10.0"


def test_a_hand_made_tag_is_never_the_highest():
    # `by_number` sorts those last but still hands them back, so the top
    # of that list is a hand-made tag on a dashboard that has no number
    # at all. A caller asking "which version do I compare against" must
    # get None there, not a tag whose name says nothing about order.
    marks = [_Named("heizung/hand-made"), _Named("solar/v9.9.9")]
    assert versions.highest("heizung", marks) is None


def test_a_dashboard_without_versions_has_no_highest():
    assert versions.highest("heizung", []) is None


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


def test_a_winter_evening_is_still_one_day():
    # Berlin is +1 in January, not +2. An implementation that carried a
    # fixed summer offset would push 23:30 into the following day and
    # split an evening in two - and it would pass every other case here.
    assert versions.same_day(_at("2026-01-15T21:00"), _at("2026-01-15T23:30"), BERLIN)


# -- the state a day ended on ------------------------------------------


def test_the_state_before_the_new_day_is_found():
    stamps = [_at("2026-09-04T08:00"), _at("2026-09-03T21:00")]
    assert versions.end_of_previous_day(stamps, BERLIN) == 1


def test_a_burst_of_saves_does_not_hide_the_day_before():
    # Two saves landing in the same moment start two marks, and both read
    # the newest entries when they run rather than the ones their own
    # event was about. Walking back rather than taking the second entry
    # is what keeps yesterday's last state reachable at all.
    stamps = [
        _at("2026-09-04T08:00:01"),
        _at("2026-09-04T08:00:00"),
        _at("2026-09-03T21:00"),
    ]
    assert versions.end_of_previous_day(stamps, BERLIN) == 2


def test_a_window_holding_only_today_ends_no_day():
    stamps = [_at("2026-09-04T08:00"), _at("2026-09-04T07:00")]
    assert versions.end_of_previous_day(stamps, BERLIN) is None


def test_the_first_state_a_dashboard_ever_had_ends_no_day():
    assert versions.end_of_previous_day([_at("2026-09-04T08:00")], BERLIN) is None
    assert versions.end_of_previous_day([], BERLIN) is None


def test_the_night_the_clocks_go_back_ends_no_day_of_its_own():
    # Both of these are 25 October in Berlin, but they fall on two
    # different days in UTC: 01:30 is still CEST and 04:00 is already
    # CET. Bucketing the epoch by 86400 would report that a day ended
    # here, and would do it twice a year.
    stamps = [_at("2026-10-25T04:00"), _at("2026-10-25T01:30")]
    assert versions.end_of_previous_day(stamps, BERLIN) is None


# -- what an automatic version is called, and at what level ------------


def test_a_dashboard_without_a_number_starts_at_major():
    assert versions.automatic_level("heizung", []) == "major"


def test_a_hand_made_tag_alone_is_still_no_number():
    # `candidates` counts up from the highest *number* there is, so a
    # dashboard whose only tag is hand-made would take v0.0.1 as its
    # first automatic version and stay on that track for good.
    assert (
        versions.automatic_level("heizung", ["heizung/wichtig", "heizung/v2.0.0-beta"])
        == "major"
    )


def test_a_numbered_dashboard_counts_on_at_patch():
    assert versions.automatic_level("heizung", ["heizung/v1.0.0"]) == "patch"


def test_another_dashboards_number_does_not_count():
    assert versions.automatic_level("heizung", ["solar/v1.0.0"]) == "major"


# -- a day carries at most one automatic version -----------------------
#
# Two steps, and the split is what makes the rule affordable:
# `marks_since` says which versions are worth a commit read, and
# `day_is_marked` decides from the times that came back. Answered from
# the *day the marked state was recorded on*, never from the title - the
# title used to carry it, and it stopped being able to the moment a
# person could rewrite it.


class _Mark:
    """A stand-in for a version: a name, a state, a time, a description."""

    def __init__(self, revision: str, timestamp: int, description: str):
        self.revision = revision
        self.timestamp = timestamp
        self.description = description


def _auto(revision: str, tagged: str, text: str = "") -> _Mark:
    """An automatic mark, tagged at `tagged`."""
    return _Mark(revision, _at(tagged), versions.automatic_description(text))


DAY = date(2026, 9, 3)


# -- which marks are worth looking up ----------------------------------


def test_a_mark_tagged_on_the_day_itself_is_worth_looking_up():
    mark = _auto("a", "2026-09-03T23:50")
    assert versions.marks_since(DAY, [mark], BERLIN) == [mark]


def test_a_mark_tagged_on_a_later_day_is_too():
    # The ordinary case: a day is marked at the first save of the day
    # after it, so the mark for the 3rd carries a tag time from the 4th.
    mark = _auto("a", "2026-09-04T08:00")
    assert versions.marks_since(DAY, [mark], BERLIN) == [mark]


def test_a_mark_older_than_the_day_cannot_be_about_it():
    # This is the bound that keeps the reading from growing without
    # limit. A mark is written after its day ended, so one tagged before
    # the day began is about an earlier day and needs no commit read.
    assert versions.marks_since(DAY, [_auto("a", "2026-09-02T23:00")], BERLIN) == []


def test_a_version_somebody_made_is_never_worth_looking_up():
    mark = _Mark("a", _at("2026-09-04T08:00"), "Handed over to the tenant")
    assert versions.marks_since(DAY, [mark], BERLIN) == []


def test_a_lightweight_tag_is_not_either():
    # A hand-made lightweight tag has no message at all, so it has
    # nothing to read a marker out of.
    assert versions.marks_since(DAY, [_Mark("a", _at("2026-09-04T08:00"), "")], BERLIN) == []


def test_the_bound_is_read_in_the_zone_the_user_lives_in():
    # Tagged half past midnight Berlin time on the 4th: the same instant
    # is still the 3rd to UTC. Against the day being asked about, that
    # decides whether the mark is inside the bound or on its edge.
    mark = _auto("a", "2026-09-04T00:30")
    assert versions.marks_since(date(2026, 9, 4), [mark], BERLIN) == [mark]
    assert versions.marks_since(date(2026, 9, 4), [mark], timezone.utc) == []


# -- and whether one of them is this day's -----------------------------


def test_a_day_whose_state_carries_a_mark_is_marked():
    mark = _auto("a", "2026-09-04T08:00")
    times = {"a": _at("2026-09-03T22:00")}
    assert versions.day_is_marked(DAY, [mark], times, BERLIN) is True


def test_a_mark_on_another_day_s_state_leaves_this_one_open():
    mark = _auto("a", "2026-09-04T08:00")
    times = {"a": _at("2026-09-02T22:00")}
    assert versions.day_is_marked(DAY, [mark], times, BERLIN) is False


def test_a_renamed_automatic_version_still_holds_its_day():
    # The reason this reads a timestamp rather than a title. What a
    # person calls the version is their business; which day it marks is
    # not a matter of naming.
    mark = _auto("a", "2026-09-04T08:00", "Before the rework")
    times = {"a": _at("2026-09-03T22:00")}
    assert versions.day_is_marked(DAY, [mark], times, BERLIN) is True


def test_a_mark_whose_state_cannot_be_read_is_not_this_day():
    # A decision, not an oversight - the docstring says which way and
    # why. It happens when the commit was pruned between the listing and
    # the reading, and the other choice would stop a dashboard from ever
    # being marked again.
    mark = _auto("a", "2026-09-04T08:00")
    assert versions.day_is_marked(DAY, [mark], {}, BERLIN) is False


def test_the_day_compared_is_the_one_the_user_lived_through():
    # Half past midnight in Berlin is still the day before to UTC. The
    # mark belongs to the day the person had, exactly as `local_day`
    # decides everywhere else here.
    mark = _auto("a", "2026-09-05T08:00")
    times = {"a": _at("2026-09-04T00:30")}
    assert versions.day_is_marked(date(2026, 9, 4), [mark], times, BERLIN) is True
    assert versions.day_is_marked(date(2026, 9, 3), [mark], times, timezone.utc) is True


def test_nothing_marked_is_not_marked():
    assert versions.day_is_marked(DAY, [], {}, BERLIN) is False


def test_the_day_a_state_falls_on_is_answered_on_its_own():
    # `local_day` is part of the interface, not a private step of
    # `same_day`, and until now only ever reached through it.
    from datetime import date

    assert versions.local_day(_at("2026-09-03T23:59"), BERLIN) == date(2026, 9, 3)
    assert versions.local_day(_at("2026-09-04T00:01"), BERLIN) == date(2026, 9, 4)


def test_a_number_that_was_taken_away_is_offered_again():
    # The conditional half of decision 13, and it needs no production
    # code: `candidates` counts from the highest name it is given, so a
    # name that is gone is a name that no longer counts. Written down
    # because it is a promise the interface makes out loud - the dialog
    # says "its number becomes free again" - and a promise nobody tests
    # is a sentence waiting to become false.
    with_it = ["home/v1.0.0", "home/v1.0.1", "home/v1.0.2"]
    without_it = ["home/v1.0.0", "home/v1.0.1"]
    assert versions.candidates("home", with_it)["patch"] == "home/v1.0.3"
    assert versions.candidates("home", without_it)["patch"] == "home/v1.0.2"


def test_taking_a_lower_number_away_frees_nothing():
    # The other half of the same sentence, and the reason the dialog only
    # says it for the highest version: removing one in the middle changes
    # no candidate at all, so a dialog that promised a free number there
    # would be lying in the ordinary case.
    assert versions.candidates("home", ["home/v1.0.0", "home/v1.0.2"])[
        "patch"
    ] == "home/v1.0.3"
