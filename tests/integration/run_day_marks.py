"""Automatic day marks, checked where Home Assistant exists.

Run it:

    docker exec -i dashboard-history-test python3 - < tests/integration/run_day_marks.py

Fed through stdin because only `custom_components/dashboard_history` is
mounted into the container - this file is not in there, and does not
need to be. Not named `test_*` either, for the reason `run_checks.py`
gives: `python3 -m pytest tests/` has to stay runnable without a
container anywhere near it.

The third way of checking in this project, and it exists because of a
gap between the first two. `pytest` cannot reach `milestones.py` at all:
it imports Home Assistant, and the development machine has none. And
`run_checks.py`, which drives a real instance, cannot reach the day mark
either - no API can backdate a commit, so a day boundary cannot be
made from outside. It says so itself, beside the one direction it can
show ("a second change on the same day adds no further version").

What is left over is the wiring: three rules that decide whether a mark
is made, all of them behind a day that ended. This runs it against a
real repository with real tags and a real comparison, and fakes exactly
one thing - the clock, at the single place the calendar reads it
(`list_changes`). A wrong answer here is a wrong answer in a running
installation.

The two runs it makes differ in a single byte, at the end of the day
being marked - same states, same calendar, same walk. That is the
control: on its own, "no second version" could as easily mean the
scenario never called for one.

Three things it does deliberately:

  * It calls `_async_mark_day` directly, a private method. There is no
    other door: the public one is an event on Home Assistant's bus, and
    an instance running enough to have a bus is exactly what is out of
    reach here.
  * It watches the log for anything at ERROR. That path swallows every
    exception on purpose - a missing mark must never break a save - so a
    typo in it looks precisely like the rule working, and a check that
    only counts versions would pass while proving nothing. Shown by
    breaking `same_state` on purpose: the first run still passes, for
    the wrong reason, and only the watcher says so.
  * It carries its own copy of `check` and the tally around it, spelled
    exactly as `run_checks.py` has them. Sharing them is not possible
    the way this file is run - it arrives on stdin, and nothing of
    `tests/` is mounted in the container - so mirroring the sibling is
    worth more than trimming the copy.
"""

from __future__ import annotations

import asyncio
import logging
import shutil
import sys
import tempfile
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, "/config")

from custom_components.dashboard_history import milestones as marking  # noqa: E402
from custom_components.dashboard_history import versions as versioning  # noqa: E402
from custom_components.dashboard_history.store import HistoryStore  # noqa: E402
from homeassistant.util import dt as dt_util  # noqa: E402

DAY = 86400
KEY = "home"
# Three states, and only whether they are equal matters. `A2` is `A`
# with one byte changed: it is what turns the second run into a control
# rather than a second story.
A = "views:\n- title: A\n"
A2 = "views:\n- title: a\n"
B = "views:\n- title: B\n"

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    """Record one result and say so on the way past. As `run_checks`."""
    (_passed if ok else _failed).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{f'  — {detail}' if detail else ''}")
    return ok


class Loud(logging.Handler):
    """Keeps whatever the marking path swallowed."""

    def __init__(self) -> None:
        super().__init__(level=logging.ERROR)
        self.records: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record.getMessage())


class Rewound(HistoryStore):
    """A store whose recorded states can sit on an earlier day.

    Only `list_changes` is touched, because that is where the calendar
    gets its input. Everything the rules actually compare - the tree, the
    blobs, the tags - is the real thing at the real revision.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(path)
        self.shifts: dict[str, int] = {}

    def list_changes(self, key, limit=50, before=None):
        found = super().list_changes(key, limit, before)
        return [
            replace(c, timestamp=c.timestamp - self.shifts.get(c.revision, 0))
            for c in found
        ]


class Hass:
    """Enough Home Assistant for the two calls this path makes."""

    async def async_add_executor_job(self, func, *args):
        return func(*args)


class Entry:
    """Enough of a config entry: the marking only reads its options."""

    options: dict = {}


async def scenario(where: Path, states) -> list[str]:
    """Write `states`, lay the floor, then mark the day that ended.

    `states` are (text, days ago) pairs, oldest first, and the last one
    is always today - a mark needs a day to close. Answers the version
    numbers the dashboard carries afterwards.
    """
    store = Rewound(where)
    for text, ago in states:
        revision = store.write_snapshot(KEY, text, f"{KEY}: {text.strip()}")
        assert revision is not None, f"nothing was recorded for {text!r}"
        store.shifts[revision] = ago * DAY

    made = marking.Milestones(Hass(), store, Entry())
    await made.async_lay_the_floor()

    await made._async_mark_day(KEY)
    return sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))


async def main() -> int:
    # The zone of a process that is not a running Home Assistant is
    # whatever the module was left holding. Said out loud, so the day
    # boundaries below are the ones this file describes.
    dt_util.DEFAULT_TIME_ZONE = dt_util.UTC

    loud = Loud()
    logging.getLogger("custom_components.dashboard_history").addHandler(loud)

    print("\n  -- Eine Marke, die nichts anbietet, entsteht nicht --")
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-day-marks-"))
    try:
        # A card moved out and moved home again: yesterday ends on the
        # very state the floor already marks.
        back_and_forth = [(A, 2), (B, 1), (A, 1), (B, 0)]
        quiet = await scenario(root / "one", back_and_forth)
        check(
            "a day ending on the state the highest version holds gets no mark",
            quiet == ["v1.0.0"],
            str(quiet),
        )

        print("\n  -- Und eine, die etwas anbietet, entsteht weiterhin --")
        # The same four states on the same two days, and the day ends one
        # byte away from what the floor holds.
        one_byte_apart = [(A, 2), (B, 1), (A2, 1), (B, 0)]
        marked = await scenario(root / "two", one_byte_apart)
        check(
            "and one byte of difference at that day's end earns one",
            marked == ["v1.0.0", "v1.0.1"],
            str(marked),
        )

        print("\n  -- Eine aufgehobene Tagesmarke kommt wieder --")
        # Decision 18 says this out loud rather than preventing it, and
        # the dialog in the panel repeats the sentence. Which makes it a
        # promise, and a promise about a rule that runs once a day is
        # worth a check: the alternative reading - "removed means gone" -
        # is the one a person will have.
        where = root / "three"
        store = Rewound(where)
        for text, ago in [(A, 2), (B, 1), (A2, 1), (B, 0)]:
            revision = store.write_snapshot(KEY, text, f"{KEY}: {text.strip()}")
            assert revision is not None
            store.shifts[revision] = ago * DAY
        made = marking.Milestones(Hass(), store, Entry())
        await made.async_lay_the_floor()
        await made._async_mark_day(KEY)
        marked = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
        if check(
            "the day was marked to begin with", marked == ["v1.0.0", "v1.0.1"], str(marked)
        ):
            store.remove_version(KEY, f"{KEY}/v1.0.1")
            gone = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
            check("and taking the mark away leaves it gone", gone == ["v1.0.0"], str(gone))
            # The same call the next save would make. Nothing else
            # changed: same states, same calendar, same walk.
            await made._async_mark_day(KEY)
            again = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
            check(
                "and the next save marks that day again",
                again == ["v1.0.0", "v1.0.1"],
                str(again),
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)

        print("\n  -- Und die von gestern kommt beim nächsten Speichern heute wieder --")
        # The case a pytest-only rule got wrong on 2026-09-09, and the
        # only place it can be shown: yesterday's mark is written by the
        # FIRST save of today, so states from today already sit behind
        # it. Remove it, save AGAIN THE SAME DAY, and it is back - more
        # states on today do not push the window past yesterday.
        #
        # `run_checks.py` cannot reach this: no API backdates a commit,
        # so there is no way to make a yesterday from outside. And
        # `pytest` cannot reach `_async_mark_day` at all. This is what
        # the third way is for.
        where = root / "four"
        store = Rewound(where)
        for text, ago in [(A, 1), (B, 1), (A2, 0)]:
            revision = store.write_snapshot(KEY, text, f"{KEY}: {text.strip()}")
            assert revision is not None
            store.shifts[revision] = ago * DAY
        made = marking.Milestones(Hass(), store, Entry())
        await made.async_lay_the_floor()
        await made._async_mark_day(KEY)
        marked = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
        if check(
            "yesterday is marked by the first save of today",
            marked == ["v1.0.0", "v1.0.1"],
            str(marked),
        ):
            # Which of the two sits on yesterday's last state - the floor
            # is on the oldest state, the day mark on the newest of
            # yesterday. Taking the day mark is the case; taking the
            # floor is a different one.
            ends = store.list_changes(KEY, 20)
            yesterday_last = next(
                c.revision for c in ends
                if versioning.local_day(c.timestamp, dt_util.DEFAULT_TIME_ZONE)
                < versioning.local_day(ends[0].timestamp, dt_util.DEFAULT_TIME_ZONE)
            )
            mark = next(
                v for v in store.list_versions(KEY) if v.revision == yesterday_last
            )
            # And the prediction, before it is taken away: it must say
            # this one comes back. A False here is the under-warning the
            # dialog would then read as "permanent".
            told = versioning.would_be_marked_again(
                mark.revision, ends, int(ends[0].timestamp + 3600),
                dt_util.DEFAULT_TIME_ZONE,
            )
            check("and the preview says it would come back", told is True, str(told))
            store.remove_version(KEY, mark.name)
            gone = sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))
            check(
                "taking it away leaves it gone",
                mark.name.split("/")[-1] not in gone,
                str(gone),
            )
            # One more save on the SAME day - the shape that was got
            # wrong. Not a new day: that case is the section above.
            again = store.write_snapshot(KEY, B, f"{KEY}: {B.strip()}")
            assert again is not None
            store.shifts[again] = 0
            await made._async_mark_day(KEY)
            back = [
                v for v in store.list_versions(KEY) if v.revision == yesterday_last
            ]
            check(
                "and the next save the same day marks yesterday again",
                bool(back),
                str(sorted(v.name.split("/")[-1] for v in store.list_versions(KEY))),
            )

    check(
        "and nothing was swallowed on the way",
        not loud.records,
        "; ".join(loud.records),
    )

    print(f"\n{len(_passed)} von {len(_passed) + len(_failed)} Prüfungen bestanden")
    if _failed:
        print("Fehlgeschlagen: " + ", ".join(_failed))
    return 1 if _failed else 0


sys.exit(asyncio.run(main()))
