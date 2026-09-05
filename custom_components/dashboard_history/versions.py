"""Version numbers and daily marks: reading, ordering, counting up.

Home-Assistant-free on purpose. This is a small calculation that can be
wrong in a way nobody notices for months - `v1.10.0` sorting below
`v1.9.0` is the classic - so it lives where plain pytest reaches it,
rather than in the panel. Same rule as the wording in `analyze.py`.

A version is an annotated git tag named `<key>/v<major>.<minor>.<patch>`.
The dashboard key is part of the name because git tags share a single
namespace: without it, only one dashboard in the whole installation
could ever have a `v1.0.0`.

The day a recorded state belongs to lives here for the same reason. A
calendar day is a small calculation that goes wrong quietly - a time
zone, a change of the clocks, a month name that follows whatever locale
the container was built with - and plain pytest settles all three in
under a second.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from datetime import date, datetime, tzinfo

# Deliberately strict: three plain numbers, no leading zeros, no suffix.
# Anything else is somebody's hand-made tag. Those stay visible, but they
# must never shift the numbering - a tag called `v2.0.0-beta` deciding
# that the next version is 2.0.1 would be a surprise nobody can undo.
_NUMBERS = re.compile(r"^v(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")

LEVELS = ("patch", "minor", "major")


def version_name(key: str, parts: tuple[int, int, int]) -> str:
    """The tag name one dashboard's version carries."""
    major, minor, patch = parts
    return f"{key}/v{major}.{minor}.{patch}"


def parse(key: str, name: str) -> tuple[int, int, int] | None:
    """The three numbers in a tag name, or None if it is not this one's."""
    prefix = f"{key}/"
    if not name.startswith(prefix):
        return None
    match = _NUMBERS.match(name[len(prefix) :])
    if match is None:
        return None
    major, minor, patch = match.groups()
    return (int(major), int(minor), int(patch))


def latest(key: str, names: Iterable[str]) -> tuple[int, int, int] | None:
    """The highest version of one dashboard, or None if it has none.

    Compared as numbers rather than as text. Tuples of ints order the way
    versions are meant to; the strings they came from do not.
    """
    found = [
        parsed for name in names if (parsed := parse(key, name)) is not None
    ]
    return max(found) if found else None


def by_number(key: str, versions: Iterable) -> list:
    """Versions by number, highest first; names that will not parse last.

    Takes anything carrying a `.name` - the store's `Version`, or a
    stand-in in a test. This module knows numbers, not storage.

    Ordered by number rather than by the time the tag was made. The store
    can only know the time, and the two differ as soon as somebody goes
    back and marks an older state: the newer tag then carries the lower
    number, and ordering by time would put it on top of one that contains
    it. A name that will not parse sorts last rather than pretending to
    be version zero.
    """
    return sorted(
        versions, key=lambda v: parse(key, v.name) or (-1, -1, -1), reverse=True
    )


def bump(parts: tuple[int, int, int], level: str) -> tuple[int, int, int]:
    """The next version at one level. Everything below it resets to zero."""
    major, minor, patch = parts
    if level == "major":
        return (major + 1, 0, 0)
    if level == "minor":
        return (major, minor + 1, 0)
    if level == "patch":
        return (major, minor, patch + 1)
    raise ValueError(f"unknown level: {level}")


def candidates(key: str, names: Iterable[str]) -> dict[str, str | None]:
    """The three names the three buttons carry, and the current one.

    Counting always starts from the **highest existing** version, even
    after somebody has gone back to an older one. That keeps the numbers
    monotone, so a new version can never collide with one that is already
    there - and a collision would be a refusal in the middle of a dialog.

    Without a predecessor the count starts at 0.0.0, which puts `0.0.1`,
    `0.1.0` and `1.0.0` on the three buttons. Whoever wants a proper first
    release finds it one click away rather than having to reach for it.
    """
    current = latest(key, names)
    base = current or (0, 0, 0)
    found: dict[str, str | None] = {
        level: version_name(key, bump(base, level)) for level in LEVELS
    }
    found["current"] = version_name(key, current) if current else None
    return found


# -- versions nobody asked for -----------------------------------------

# The first line of the description an automatically made version
# carries. A marker, not a sentence: what a person gets to read is built
# from the flag this sets, so rewording it later fixes every tag that
# already exists rather than only the next one. It stays out of the
# *title*, which the simple mode shows on its own and which has room for
# the date and nothing else.
AUTOMATIC = "dashboard-history: automatic"

# Spelled out rather than left to strftime("%B"). That follows the C
# locale of whatever container Home Assistant runs in, so the same tag
# would read "September" on one installation and something else on the
# next - and a version name that depends on the machine is not a name.
_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def automatic_description(text: str = "") -> str:
    """The description an automatically made version carries."""
    return f"{AUTOMATIC}\n{text}".rstrip() if text else AUTOMATIC


def read_description(text: str) -> tuple[str, bool]:
    """A stored description as (what a person wrote, was it automatic).

    The marker is taken out rather than shown. Reported as a field, it is
    something the interface can act on; reported as prose, it is a line
    of machine talk in the middle of somebody's own words.
    """
    head, _, rest = text.partition("\n")
    if head.strip() == AUTOMATIC:
        return rest.strip(), True
    return text.strip(), False


def local_day(timestamp: int, zone: tzinfo) -> date:
    """The calendar day a recorded state falls on, where the user lives.

    Not UTC, and the design record says so in as many words. A save at
    half past midnight in Berlin is the next day to the person who made
    it and the same day to UTC; the daily version is named after the day
    *they* had.
    """
    return datetime.fromtimestamp(timestamp, zone).date()


def same_day(one: int, other: int, zone: tzinfo) -> bool:
    """Whether two recorded states fall on the same local calendar day.

    Compared as dates, not as a difference in seconds. A day is not
    86400 seconds wherever the clocks change: the Sunday in March has
    23 hours and the one in October has 25, and both are one day to
    everybody living through them.
    """
    return local_day(one, zone) == local_day(other, zone)


def day_title(timestamp: int, zone: tzinfo) -> str:
    """What an automatic daily version is called: `3 September 2026`."""
    when = datetime.fromtimestamp(timestamp, zone)
    return f"{when.day} {_MONTHS[when.month - 1]} {when.year}"


def end_of_previous_day(stamps: Sequence[int], zone: tzinfo) -> int | None:
    """Where in a run of recorded states the day before ends, or None.

    `stamps` is newest first, as `list_changes` hands them over. The
    answer is the index of the first entry that falls on an earlier day
    than the newest one - the state that day ended on.

    Walked back rather than read off the second entry, and that is the
    whole point of this function. A mark is started from an announcement
    and does its reading when it *runs*, not when it was announced: two
    saves landing within milliseconds start two marks that both see both
    writes. Taking the second entry, both would see [today, today], find
    one day, and stop - and the last state of the day before, one row
    further down, would never be marked by anything, ever. Silent and
    permanent, since no later save reaches back to it.

    None has two meanings, and neither is an error: the newest state is
    the first this dashboard ever had, or every state handed over belongs
    to the same day. The second is the edge of whatever window the caller
    read, and the caller is the one that knows how wide it was.
    """
    if len(stamps) < 2:
        return None
    return next(
        (at for at in range(1, len(stamps)) if not same_day(stamps[at], stamps[0], zone)),
        None,
    )


def automatic_level(key: str, names: Iterable[str]) -> str:
    """The level an automatic version is made at: `major` or `patch`.

    Major when the dashboard carries no *number* yet, so that its first
    automatic version is `v1.0.0` and not `v0.0.1`. `candidates` counts
    up from the highest number there is, and with none there the patch
    candidate is `v0.0.1`; a later pass would then find a version, leave
    the dashboard alone, and strand it on the v0.0.x track for good.

    Read off `latest` rather than off the list, because the list
    deliberately carries hand-made and unreadable names too - a
    dashboard whose only tag is `heizung/wichtig` has no number.
    """
    return "patch" if latest(key, names) is not None else "major"


def automatic_days(marks: Iterable[tuple[str, str]]) -> set[str]:
    """Which days already carry an automatic version, by title.

    `marks` are `(title, description)` pairs, as a dashboard's versions
    hand them over. A day gets at most one automatic version: the simple
    mode shows a list of nothing but titles, and two rows reading
    `5 September 2026` with two different buttons under them cannot be
    told apart by the person that mode exists for.

    Only automatic ones count. What somebody wrote themselves is their
    own name for a state, even in the unlikely event that it reads like
    a date.
    """
    return {title for title, text in marks if title and read_description(text)[1]}
