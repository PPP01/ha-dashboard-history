"""Decision 23: a write that cannot record what it replaces refuses.

Run it:

    docker exec -i dashboard-history-test python3 - < tests/integration/run_unrecorded_state_refusal.py

The third way of checking in this project - see `run_day_marks.py` for
the long version of why it exists. `operations.py` imports Home
Assistant, so plain `pytest` cannot import it at all, and the three
functions this file is about also read Home Assistant's live dashboard
registry through `snapshot.py` (`async_get_config`, `async_known_keys`,
`async_save_config`) - which `run_checks.py` reaches over a real
instance, but cannot make fail on demand. There is no API to break the
one thing Decision 23 is about: a repository that briefly cannot
record the state a write is about to overwrite. `run_checks.py` covers
that scenario for real, by locking the repository itself, in its own
end-to-end check; this file is narrower and does not need a live
instance to make its point.

So the live dashboard registry is faked here instead of reached for
real - the one door this file opens that `run_day_marks.py`'s note
does not cover. `snapshot.py`'s three functions are swapped for
stand-ins on the `operations` module object itself, never on anything
of Home Assistant's, which has no part in this file at all: this is a
test double for three lines this integration wrote, not an interception
of Home Assistant internals. What is real: a `HistoryStore` built the
way `test_store.py` builds one, `write_snapshot` against it, and every
line `operations.py` writes to it in response.

Not shown here: whether `capture.async_capture` genuinely fails on a
full disk (a container has no full disk to give it - `run_checks.py`'s
check locks the repository instead, which is the same failure from the
writer's point of view) and the two one-line assignments in
`services.py`/`websocket_api.py` (`run_checks.py`'s existing checks
already exercise that schema shape for `confirm`).
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
from custom_components.dashboard_history.yaml_io import dump  # noqa: E402

KEY = "home"
RECORDED = {"views": [{"title": "Home", "cards": [{"type": "markdown", "content": "# A"}]}]}
EDITED = {"views": [{"title": "Home", "cards": [{"type": "markdown", "content": "# B"}]}]}

_passed: list[str] = []
_failed: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    """Record one result and say so on the way past. As `run_checks`."""
    (_passed if ok else _failed).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name}{f'  — {detail}' if detail else ''}")
    return ok


class Hass:
    """Enough Home Assistant for `_keep_the_live_state` alone.

    `run_day_marks.py`'s stand-in, with `.data` added: `operations.py`
    reads `hass.data` directly for the capture object, `milestones.py`
    never does. Left empty on purpose - no `"capture"` key means
    `_keep_the_live_state` skips straight to its read-check, which is
    exactly the branch this file is about.
    """

    def __init__(self) -> None:
        self.data: dict = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


async def _restore_scenario() -> None:
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-unrecorded-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        revision = store.write_snapshot(KEY, dump(RECORDED), f"{KEY}: recorded")
        assert revision is not None, "nothing was recorded for the fixture state"
        hass = Hass()

        with (
            mock.patch.object(
                operations, "async_known_keys", new=mock.AsyncMock(return_value={KEY})
            ),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=EDITED)
            ) as get_config,
            mock.patch.object(
                operations, "async_save_config", new=mock.AsyncMock(return_value=None)
            ) as save_config,
        ):
            refused = await operations.async_restore_state(
                hass, store, KEY, revision, confirm=True
            )
            check(
                "restore_state refuses when the live state cannot be recorded",
                refused.get("applied") is False and refused.get("unrecorded_state") is True,
                str(refused),
            )
            check(
                "and nothing was written",
                save_config.await_count == 0,
                f"called {save_config.await_count} times",
            )

            overridden = await operations.async_restore_state(
                hass, store, KEY, revision, confirm=True, override_unrecorded_state=True
            )
            check(
                "the same call with the escape hatch writes anyway",
                overridden.get("applied") is True,
                str(overridden),
            )
            check(
                "and it wrote exactly once",
                save_config.await_count == 1,
                f"called {save_config.await_count} times",
            )
            assert get_config.await_count >= 2, "sanity: the stub was actually read from"
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _restore_deleted_scenario() -> None:
    """Same shape as `_restore_scenario`, for `async_restore_deleted`.

    The gap this project is chasing does not care which of the three
    write operations hits it - a guard added to one and forgotten on
    another would be invisible to `_restore_scenario` alone.
    """
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-unrecorded-deleted-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        full_state = {
            "views": [{"title": "Home", "cards": [
                {"type": "markdown", "content": "# A"},
                {"type": "markdown", "content": "# B"},
            ]}]
        }
        revision = store.write_snapshot(KEY, dump(full_state), f"{KEY}: A and B")
        assert revision is not None, "nothing was recorded for the fixture state"

        # B is missing since, and A carries an edit the recorder never
        # saw either - the gap this scenario is about.
        live_missing_b = {
            "views": [{"title": "Home", "cards": [
                {"type": "markdown", "content": "# A, edited after the fact"},
            ]}]
        }
        plan_check = operations._reinsertion(dump(full_state), live_missing_b, 0, KEY)
        assert "error" not in plan_check, (
            f"scenario setup is wrong - nothing to reinsert: {plan_check}"
        )
        hass = Hass()

        with (
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=live_missing_b)
            ),
            mock.patch.object(
                operations, "async_save_config", new=mock.AsyncMock(return_value=None)
            ) as save_config,
        ):
            refused = await operations.async_restore_deleted(
                hass, store, KEY, revision, 0, confirm=True
            )
            check(
                "restore_deleted refuses when the live state cannot be recorded",
                refused.get("applied") is False and refused.get("unrecorded_state") is True,
                str(refused),
            )
            check(
                "and nothing was written",
                save_config.await_count == 0,
                f"called {save_config.await_count} times",
            )

            overridden = await operations.async_restore_deleted(
                hass, store, KEY, revision, 0, confirm=True, override_unrecorded_state=True
            )
            check(
                "the same call with the escape hatch writes anyway",
                overridden.get("applied") is True,
                str(overridden),
            )
            check(
                "and it wrote exactly once",
                save_config.await_count == 1,
                f"called {save_config.await_count} times",
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _undo_change_scenario() -> None:
    """Same shape again, for `async_undo_change` - the third and last caller."""
    root = Path(tempfile.mkdtemp(prefix="dashboard-history-unrecorded-undo-"))
    try:
        store = HistoryStore(root)
        store.ensure()
        before = {"views": [{"title": "Home", "cards": [{"type": "markdown", "content": "# A"}]}]}
        after = {
            "views": [{"title": "Home", "cards": [
                {"type": "markdown", "content": "# A"},
                {"type": "markdown", "content": "# B"},
            ]}]
        }
        store.write_snapshot(KEY, dump(before), f"{KEY}: A")
        revision = store.write_snapshot(KEY, dump(after), f"{KEY}: A, B added")
        assert revision is not None, "nothing was recorded for the fixture state"

        # B, which this change added, is still there untouched - the
        # undo has something exact to take back - but A carries an
        # edit the recorder never saw, which is the gap this scenario
        # is about.
        live = {
            "views": [{"title": "Home", "cards": [
                {"type": "markdown", "content": "# A, edited after the fact"},
                {"type": "markdown", "content": "# B"},
            ]}]
        }
        hass = Hass()

        with (
            mock.patch.object(
                operations, "async_known_keys", new=mock.AsyncMock(return_value={KEY})
            ),
            mock.patch.object(
                operations, "async_get_config", new=mock.AsyncMock(return_value=live)
            ),
            mock.patch.object(
                operations, "async_save_config", new=mock.AsyncMock(return_value=None)
            ) as save_config,
        ):
            preview = await operations.async_undo_change(
                hass, store, KEY, revision, confirm=False, preview=True
            )
            assert preview.get("available") is True, (
                f"scenario setup is wrong - the undo is not offered: {preview}"
            )

            refused = await operations.async_undo_change(
                hass, store, KEY, revision, confirm=True
            )
            check(
                "undo_change refuses when the live state cannot be recorded",
                refused.get("applied") is False and refused.get("unrecorded_state") is True,
                str(refused),
            )
            check(
                "and nothing was written",
                save_config.await_count == 0,
                f"called {save_config.await_count} times",
            )

            overridden = await operations.async_undo_change(
                hass, store, KEY, revision, confirm=True, override_unrecorded_state=True
            )
            check(
                "the same call with the escape hatch writes anyway",
                overridden.get("applied") is True,
                str(overridden),
            )
            check(
                "and it wrote exactly once",
                save_config.await_count == 1,
                f"called {save_config.await_count} times",
            )
    finally:
        shutil.rmtree(root, ignore_errors=True)


async def _refusal_decision_matrix() -> None:
    """The four cells of `_refuse_unrecorded_state` on their own.

    Behind the scenario above so a failure there is not the first thing
    printed - it is the one worth reading first, since it is closest to
    what a person actually does.
    """
    cases = (
        (None, False, True, "no gap at all, no override needed"),
        (None, True, True, "no gap at all, override asked for anyway"),
        ("a note", False, False, "a gap, no override: refused"),
        ("a note", True, True, "a gap, overridden: proceeds"),
    )
    for lost, override, expect_none, label in cases:
        result = operations._refuse_unrecorded_state(lost, override)
        check(
            f"_refuse_unrecorded_state: {label}",
            (result is None) == expect_none,
            str(result),
        )
    refusal = operations._refuse_unrecorded_state("a note", False)
    check(
        "a refusal carries the marker the panel and the services rely on",
        refusal is not None
        and refusal["applied"] is False
        and refusal["unrecorded_state"] is True
        and isinstance(refusal.get("error"), str)
        and refusal["error"],
        str(refusal),
    )


async def main() -> int:
    await _refusal_decision_matrix()
    await _restore_scenario()
    await _restore_deleted_scenario()
    await _undo_change_scenario()
    print(f"\n{len(_passed)} of {len(_passed) + len(_failed)} checks passed")
    if _failed:
        print("Failed: " + ", ".join(_failed))
        return 1
    return 0


sys.exit(asyncio.run(main()))
