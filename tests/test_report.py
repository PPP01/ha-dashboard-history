"""Tests for the report a tester can send back."""

import pytest
import report
from store import DashboardFacts, Measurement

SECRET = "0123456789abcdef0123456789abcdef"

FACTS = Measurement(
    revisions=3,
    oldest=1740873600,   # 2025-03-02 00:00:00 UTC
    newest=1758153600,   # 2025-09-18 00:00:00 UTC
    newest_key="wohnzimmer",
    versions=2,
    dashboards=(
        DashboardFacts("wohnzimmer", 2, 268341, 2, 1740873600, 1758153600, False),
        DashboardFacts("heizung-keller", 1, 4012, 0, 1740873600, 1740873600, True),
    ),
    bytes_allocated=9629696,
    # 8627657 + 555111 = 9182768, which is what `bytes_logical` answers.
    # It is a property now rather than a field, because it was exactly
    # that sum and nothing else - and a stored sum is a sum that can
    # drift from its parts.
    bytes_git_logical=8627657,
    bytes_worktree_logical=555111,
    loose_objects=18,
    packs=1,
)


def built(**kwargs):
    settings = dict(daily_versions=True, measured_at=1758196800.0, stale=False)
    settings.update(kwargs)
    return report.build(FACTS, SECRET, **settings)


def test_the_four_blocks_are_all_there():
    body = built()
    assert set(body) == {
        "schema", "measured_at", "stale",
        "environment", "settings", "totals", "dashboards",
    }


def test_totals_carry_every_field_of_the_contract():
    totals = built()["totals"]
    assert totals["dashboards_live"] == 1
    assert totals["dashboards_gone"] == 1
    assert totals["dashboards_ever"] == 2
    assert totals["revisions"] == 3
    assert totals["versions"] == 2
    assert totals["bytes_logical"] == 9182768
    assert totals["bytes_allocated"] == 9629696
    assert totals["loose_objects"] == 18
    assert totals["packs"] == 1


def test_dates_are_days_and_carry_no_time_of_day():
    body = built()
    assert body["totals"]["oldest"] == "2025-03-02"
    assert body["totals"]["newest"] == "2025-09-18"
    for row in body["dashboards"]:
        assert "T" not in row["first"] and "T" not in row["last"]


def test_measured_at_is_the_only_timestamp_and_is_utc():
    assert built()["measured_at"].endswith("+00:00")


def test_an_empty_history_reports_honest_zeros():
    body = report.build(
        Measurement(), SECRET, daily_versions=False, measured_at=1758196800.0, stale=False
    )
    assert body["dashboards"] == []
    assert body["totals"]["revisions"] == 0
    assert body["totals"]["dashboards_ever"] == 0
    assert body["totals"]["oldest"] is None
    assert body["environment"]["dulwich"]


def test_never_measured_is_not_the_same_as_measured_and_empty():
    body = report.build(
        None, SECRET, daily_versions=False, measured_at=None, stale=True
    )
    assert body["measured_at"] is None
    assert body["stale"] is True
    # No totals at all, rather than a block of zeros: a reader must be
    # able to tell "nothing recorded" from "nothing measured yet".
    assert body["totals"] == {}
    assert body["dashboards"] == []
    # The two fields that answer something even here.
    assert body["environment"]["dulwich"]
    assert "yaml_c_loader" in body["environment"]


def test_dashboards_are_sorted_by_revisions_and_flag_the_gone_ones():
    rows = built()["dashboards"]
    assert rows[0]["revisions"] == 2
    assert rows[0]["gone"] is False
    assert rows[1]["gone"] is True


# -- the ids -----------------------------------------------------------


def test_the_same_key_and_secret_give_the_same_id():
    assert report.dashboard_id("home", SECRET) == report.dashboard_id("home", SECRET)


def test_a_different_key_gives_a_different_id():
    assert report.dashboard_id("home", SECRET) != report.dashboard_id("away", SECRET)


def test_a_different_secret_gives_a_different_id_for_the_same_key():
    other = "ffffffffffffffffffffffffffffffff"
    assert report.dashboard_id("home", SECRET) != report.dashboard_id("home", other)


def test_an_id_is_eight_hex_characters():
    found = report.dashboard_id("home", SECRET)
    assert len(found) == 8
    assert all(c in "0123456789abcdef" for c in found)


# -- the one that keeps this file shareable ----------------------------


def _every_string(value):
    """Every string anywhere in the structure, keys included.

    The twin of `_strings` in `tests/integration/run_checks.py`, and
    that file says why the two are copies rather than one import. **If
    you change one, change the other** - between them they carry the
    only promise this initiative makes about what leaves the house.
    """
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _every_string(item)
    elif isinstance(value, list):
        for item in value:
            yield from _every_string(item)
    elif isinstance(value, str):
        yield value


def test_no_dashboard_name_survives_into_the_report():
    body = built()
    haystack = "\n".join(_every_string(body))
    for name in ("wohnzimmer", "heizung-keller"):
        assert name not in haystack, f"{name!r} leaked into the report"
