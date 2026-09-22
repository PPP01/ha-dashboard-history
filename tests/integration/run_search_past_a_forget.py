"""Decision 24: async_search retries its whole sequence past a forget.

Run it:

    docker exec -i dashboard-history-test python3 - < tests/integration/run_search_past_a_forget.py

The third way of checking in this project - see `run_day_marks.py` for
the long version of why it exists, and
`run_unrecorded_state_refusal.py` for the same pattern applied to a
different decision. `operations.py` imports Home Assistant, so plain
`pytest` cannot import it at all. `async_search`'s retry never touches
Home Assistant's live dashboard registry - it wraps `store.list_versions`,
`store.search_changes` and a local helper, all pure `HistoryStore` reads
- so this file does not need a running instance either, unlike
`run_checks.py`'s end-to-end checks.

What is real: a `HistoryStore` built the way `test_store.py` builds
one, real `write_snapshot`/`create_version`/`forget` calls against it.
What is faked, the same way `run_unrecorded_state_refusal.py` fakes it:
`async_get_config`, so `async_search`'s one Home-Assistant-touching
step past the retried part returns something instead of reaching for a
live instance that does not exist here.
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
    """Enough Home Assistant for `async_search` alone.

    `run_unrecorded_state_refusal.py`'s stand-in: `async_add_executor_job`
    runs its function synchronously, right here, which is what lets a
    test simulate an exact interleaving without real threads.
    """

    def __init__(self) -> None:
        self.data: dict = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


async def _retries_past_a_race() -> None:
    """"gone" is written before `KEY`, not after: commit shas are
    content hashes, and forgetting a dashboard only gives a later
    commit a new sha if something about its own tree or its ancestry
    changed. Writing "gone" last would let it be forgotten "for free"
    - nothing downstream of it to rewrite - and the version-tag check
    below would then pass even if async_search never rebuilt `marks`
    at all.
    """
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-search-race-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot("gone", "b: 1\n", "gone first")
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: unique-needle-1")
        revision = store.write_snapshot(KEY, "a: 2\n", f"{KEY}: unique-needle-2")
        store.create_version(f"{KEY}/v1.0.0", "Home", "", revision)
        hass = Hass()

        real_search_changes = HistoryStore.search_changes
        calls: list[int] = []

        def flaky_search_changes(self, key, text, limit=50, versions=None):
            calls.append(1)
            if len(calls) == 1:
                store.forget("gone")  # moves HEAD for real, mid-sequence
                raise KeyError(b"simulated: pruned mid-read")
            return real_search_changes(self, key, text, limit, versions)

        with (
            mock.patch.object(
                HistoryStore, "search_changes", flaky_search_changes
            ),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            result = await operations.async_search(hass, store, KEY, "unique-needle")

        check(
            "async_search retried instead of raising",
            len(calls) == 2,
            f"called {len(calls)} times",
        )
        check(
            "both matches came back",
            len(result["changes"]) == 2,
            str(result),
        )
        check(
            "the version tag is still attached to its change after the retry",
            any(
                any(v["name"] == f"{KEY}/v1.0.0" for v in c.get("versions", []))
                for c in result["changes"]
            ),
            str(result),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _retries_past_a_race_with_missing_commit_error() -> None:
    """Companion to `_retries_past_a_race`, with `MissingCommitError`
    instead of `KeyError` - dulwich's walker raises that one, not a
    subclass of `KeyError`, when an object vanishes mid-walk. Decision
    24 requires both be caught."""
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-search-race-mce-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot("gone", "b: 1\n", "gone first")
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: unique-needle-1")
        hass = Hass()

        real_search_changes = HistoryStore.search_changes
        calls: list[int] = []

        def flaky_search_changes(self, key, text, limit=50, versions=None):
            calls.append(1)
            if len(calls) == 1:
                store.forget("gone")
                raise operations.MissingCommitError(b"simulated: pruned mid-read")
            return real_search_changes(self, key, text, limit, versions)

        with (
            mock.patch.object(
                HistoryStore, "search_changes", flaky_search_changes
            ),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            result = await operations.async_search(hass, store, KEY, "unique-needle")

        check(
            "async_search retried a MissingCommitError instead of raising",
            len(calls) == 2,
            f"called {len(calls)} times",
        )
        check("the match came back", len(result["changes"]) == 1, str(result))
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _retries_a_successful_but_stale_attempt() -> None:
    """A forget that completes entirely between `list_versions` and
    `search_changes` - the guaranteed `await` point between them in
    `attempt()` - raises nothing anywhere. `list_versions`'s own call
    succeeds (with the *old* generation's tags), `search_changes`
    then succeeds too (with the *new* generation's shas, since its own
    walk reads fresh). Trusted only if HEAD read the same right after
    `attempt()` returns as it did when this attempt began - not just
    "nothing raised". See decision 24.
    """
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-search-stale-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot("gone", "b: 1\n", "gone first")
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: unique-needle-1")
        revision = store.write_snapshot(KEY, "a: 2\n", f"{KEY}: unique-needle-2")
        store.create_version(f"{KEY}/v1.0.0", "Home", "", revision)
        hass = Hass()

        real_list_versions = HistoryStore.list_versions
        calls: list[int] = []

        def flaky_list_versions(self, key=None):
            calls.append(1)
            if len(calls) == 1:
                old_versions = real_list_versions(self, key)
                store.forget("gone")  # completes fully - no exception anywhere
                return old_versions
            return real_list_versions(self, key)

        with (
            mock.patch.object(HistoryStore, "list_versions", flaky_list_versions),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            result = await operations.async_search(hass, store, KEY, "unique-needle")

        check(
            "async_search retried a successful-but-stale attempt",
            len(calls) == 2,
            f"called {len(calls)} times",
        )
        check(
            "the version tag is still attached after the retry",
            any(
                any(v["name"] == f"{KEY}/v1.0.0" for v in c.get("versions", []))
                for c in result["changes"]
            ),
            str(result),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _retries_when_checkpoint_present_even_if_head_is_stable() -> None:
    """HEAD alone cannot catch every case - see
    `test_list_changes_retries_when_a_checkpoint_is_present_even_if_head_is_stable`
    in `tests/test_store.py` (Task 1) for the full reasoning. No real
    `forget` runs in this test at all - HEAD never moves - only the
    checkpoint file's mere presence must be enough to distrust the
    result. See decision 24 and issue #27.
    """
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-search-checkpoint-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: unique-needle-1")
        checkpoint = store.path / ".git" / "dashboard_history_forget.json"
        hass = Hass()

        real_list_versions = HistoryStore.list_versions
        calls: list[int] = []

        def flaky_list_versions(self, key=None):
            calls.append(1)
            if len(calls) == 1:
                checkpoint.write_text("{}", encoding="utf-8")
                return real_list_versions(self, key)
            checkpoint.unlink()
            return real_list_versions(self, key)

        with (
            mock.patch.object(HistoryStore, "list_versions", flaky_list_versions),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            result = await operations.async_search(hass, store, KEY, "unique-needle")

        check(
            "async_search retried because a checkpoint was present",
            len(calls) == 2,
            f"called {len(calls)} times",
        )
        check("the result still came back", len(result["changes"]) == 1, str(result))
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _propagates_when_head_did_not_move() -> None:
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-search-nomove-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: unique-needle-1")
        hass = Hass()

        def always_fails(self, key, text, limit=50, versions=None):
            raise KeyError(b"simulated: unrelated corruption")

        raised = False
        with (
            mock.patch.object(HistoryStore, "search_changes", always_fails),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            try:
                await operations.async_search(hass, store, KEY, "unique-needle")
            except KeyError:
                raised = True

        check("an unrelated failure is not swallowed by a retry", raised)
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _raises_when_even_the_last_attempt_stays_unstable() -> None:
    """A `forget` that keeps racing every single attempt, including the
    last, must not have its last, exception-free result handed back
    unchecked - see `test_list_changes_raises_when_even_the_last_attempt_stays_unstable`
    in `tests/test_store.py` (the correction to decision 24's original
    budget paragraph) for the full reasoning. `list_versions` moves
    HEAD on every call here, never raising, so all three attempts stay
    unvalidated and `async_search` raises instead of returning a
    result nothing here ever vouched for.
    """
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-search-unstable-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: unique-needle-1")
        for i in range(5):
            store.write_snapshot(f"gone{i}", "b: 1\n", "gone first")
        hass = Hass()

        real_list_versions = HistoryStore.list_versions
        calls: list[int] = []

        def flaky_list_versions(self, key=None):
            calls.append(1)
            store.forget(f"gone{len(calls) - 1}")  # moves HEAD every single time
            return real_list_versions(self, key)

        raised = None
        with (
            mock.patch.object(HistoryStore, "list_versions", flaky_list_versions),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            try:
                await operations.async_search(hass, store, KEY, "unique-needle")
            except RuntimeError as exc:
                raised = exc

        check(
            "async_search raises once even the last attempt stays unstable",
            raised is not None and "kept racing" in str(raised),
            str(raised),
        )
        check("all three attempts ran", len(calls) == 3, f"called {len(calls)} times")
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _survives_a_race_in_head_resolution_itself() -> None:
    """`current_head()` dereferences `store.resolve("HEAD")`, which can
    itself race the exact prune it exists to detect - see
    `test_current_head_survives_a_key_error_from_resolving_head_itself`
    in `tests/test_store.py` for the sync twin. `store.resolve("HEAD")`
    always fails here; nothing else calls `resolve` in this path, so
    every HEAD observation on both sides of every attempt answers a
    fresh, never-equal sentinel instead of crashing - which means
    nothing ever validates, and `async_search` raises the same way it
    does when HEAD genuinely never settles.
    """
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-search-head-race-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        store.write_snapshot(KEY, "a: 1\n", f"{KEY}: unique-needle-1")
        hass = Hass()

        def always_races(self, revision):
            raise KeyError(b"simulated: HEAD itself pruned mid-resolve")

        raised = None
        with (
            mock.patch.object(HistoryStore, "resolve", always_races),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=None)
            ),
        ):
            try:
                await operations.async_search(hass, store, KEY, "unique-needle")
            except RuntimeError as exc:
                raised = exc

        check(
            "async_search does not crash when HEAD itself cannot be read",
            raised is not None and "kept racing" in str(raised),
            str(raised),
        )
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def main() -> int:
    await _retries_past_a_race()
    await _retries_past_a_race_with_missing_commit_error()
    await _retries_a_successful_but_stale_attempt()
    await _retries_when_checkpoint_present_even_if_head_is_stable()
    await _propagates_when_head_did_not_move()
    await _raises_when_even_the_last_attempt_stays_unstable()
    await _survives_a_race_in_head_resolution_itself()
    print(f"\n{len(_passed)} of {len(_passed) + len(_failed)} checks passed")
    if _failed:
        print("Failed: " + ", ".join(_failed))
        return 1
    return 0


sys.exit(asyncio.run(main()))
