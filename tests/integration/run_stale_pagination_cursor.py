"""Issue #26: async_history restarts instead of silently truncating.

Run it:

    docker exec -i dashboard-history-test python3 - < tests/integration/run_stale_pagination_cursor.py

The third way of checking in this project - see
`tests/integration/run_search_past_a_forget.py` for the pattern this
follows and the long version of why it exists. `operations.py` imports
Home Assistant, so plain `pytest` cannot import it at all.
`async_history`'s restart never touches Home Assistant's live dashboard
registry beyond the one call it already made before this plan, so this
file does not need a running instance either, unlike `run_checks.py`'s
end-to-end checks.

What is real: a `HistoryStore` built the way `test_store.py` builds
one, real `write_snapshot`/`forget` calls against it, and the real
`operations.async_history`. What is faked, the same way
`run_search_past_a_forget.py` fakes it: `async_get_config`, so the one
Home-Assistant-touching step returns something instead of reaching for
a live instance that does not exist here.
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from unittest import mock

sys.path.insert(0, "/config")

from custom_components.dashboard_history import operations  # noqa: E402
from custom_components.dashboard_history.store import HistoryStore  # noqa: E402

KEY = "home"

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    """Record one result and say so on the way past. As `run_checks`."""
    (_passed if ok else _failed).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{f'  — {detail}' if detail else ''}")
    return ok


class Hass:
    """Enough Home Assistant for `async_history` alone."""

    def __init__(self) -> None:
        self.data: dict = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


async def _restarts_after_a_forget_moved_past_the_cursor() -> None:
    """"gone" is written before `KEY`'s commits, not after - forgetting
    a dashboard only gives a later commit a new sha if something about
    its own tree or ancestry changed (same reasoning as decision 24's
    own tests, and `test_stale_before_generation_raises` in
    `tests/test_store.py`)."""
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-stale-cursor-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot("gone", "b: 1\n", "gone first")
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: change 1")
        store.write_snapshot(KEY, "a: 2\n", f"{KEY}: change 2")
        store.write_snapshot(KEY, "a: 3\n", f"{KEY}: change 3")
        hass = Hass()

        with mock.patch.object(
            operations, "async_get_config", new=mock.AsyncMock(return_value=None)
        ):
            first_page = await operations.async_history(hass, store, KEY, limit=2)
            check(
                "the first page has a cursor to page past",
                first_page["next_cursor"] is not None,
                str(first_page),
            )
            cursor = first_page["next_cursor"]
            generation = first_page["generation"]

            store.forget("gone")  # rewrites every surviving commit, cursor included

            second_page = await operations.async_history(
                hass, store, KEY, limit=2, before=cursor, before_generation=generation
            )

        check(
            "the response says it restarted",
            second_page.get("restarted") is True,
            str(second_page),
        )
        check(
            "it came back with the newest page, not an empty one",
            len(second_page["changes"]) == 2,
            str(second_page),
        )
        check(
            "the newest change is the most recent one written",
            second_page["changes"][0]["message"] == f"{KEY}: change 3",
            str(second_page),
        )
        check(
            "the generation moved forward",
            second_page["generation"] == generation + 1,
            str(second_page),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _keeps_answering_nothing_for_a_cursor_without_a_generation() -> None:
    """A caller that never adopted `before_generation` - any direct
    WebSocket caller with admin rights, not only the panel - must not
    be told the history restarted. It gets the same `[]` an unknown
    cursor has always produced."""
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-stale-cursor-nogen-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot("gone", "b: 1\n", "gone first")
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: change 1")
        hass = Hass()

        store.forget("gone")

        with mock.patch.object(
            operations, "async_get_config", new=mock.AsyncMock(return_value=None)
        ):
            result = await operations.async_history(
                hass, store, KEY, limit=50, before="f" * 40
            )

        check(
            "no restart is claimed",
            result.get("restarted") is False,
            str(result),
        )
        check("the page is simply empty", result["changes"] == [], str(result))
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _retries_when_a_forget_completes_between_the_page_and_its_generation() -> None:
    """The gap an external review found in a first draft: `list_changes`
    and `forget_generation` used to be two independently scheduled
    executor jobs under one `asyncio.gather`, with no ordering between
    them at all. A `forget` completing in that gap could pair a cursor
    that was still valid at read time with a generation number that
    had already moved past it - a client remembering that pairing
    would then see its *next* stale-cursor check silently pass ([])
    instead of raising, because the remembered generation was already
    "too high" relative to the page it travelled with. Now bundled
    into one executor hop (`_changes_and_generation`) and wrapped in
    the same retry `async_search` already uses (decision 24); this
    proves the retry actually fires when a forget completes squarely
    inside that hop, using the identical technique
    `run_search_past_a_forget.py`'s
    `_retries_a_successful_but_stale_attempt` already established."""
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-race-gen-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot("gone", "b: 1\n", "gone first")
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: change 1")
        store.write_snapshot(KEY, "a: 2\n", f"{KEY}: change 2")
        hass = Hass()

        real_list_changes = HistoryStore.list_changes
        calls: list[int] = []

        def flaky_list_changes(self, key, limit=50, before=None, before_generation=None):
            calls.append(1)
            found = real_list_changes(self, key, limit, before, before_generation)
            if len(calls) == 1:
                store.forget("gone")  # completes fully, in the gap, no exception
            return found

        with (
            mock.patch.object(HistoryStore, "list_changes", flaky_list_changes),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            result = await operations.async_history(hass, store, KEY, limit=2)

        check(
            "async_history retried a successful-but-stale attempt",
            len(calls) == 2,
            f"called {len(calls)} times",
        )
        check(
            "the result still came back with real data",
            len(result["changes"]) == 2,
            str(result),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def main() -> int:
    await _restarts_after_a_forget_moved_past_the_cursor()
    await _keeps_answering_nothing_for_a_cursor_without_a_generation()
    await _retries_when_a_forget_completes_between_the_page_and_its_generation()
    print(f"\n{len(_passed)} of {len(_passed) + len(_failed)} checks passed")
    if _failed:
        print("Failed: " + ", ".join(_failed))
        return 1
    return 0


sys.exit(asyncio.run(main()))
