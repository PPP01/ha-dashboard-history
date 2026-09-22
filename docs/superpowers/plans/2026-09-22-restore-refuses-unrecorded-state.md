# Restore Refuses an Unrecorded Live State — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `async_restore_deleted`, `async_restore_state`, and
`async_undo_change` refuse to write when the live state they are about
to overwrite could not be safely recorded first — unless the caller
explicitly says to write anyway.

**Architecture:** `_keep_the_live_state` (`operations.py:235`) already
tries to record the live state before every write and answers with a
note, never a refusal, when it could not. This plan turns that note
into a refusal by default at the three call sites that read it, adds
one new boolean parameter (`override_unrecorded_state`) that restores
the old "write anyway" behaviour on request, threads it through the two
service doors (`services.py`/`services.yaml`, `websocket_api.py`), and
gives the panel a second confirmation step that offers exactly that
override when — and only when — this specific refusal is the reason a
write did not happen.

**Tech Stack:** Python (Home Assistant custom component), `dulwich`,
vanilla JavaScript (`panel.js`, no framework), `pytest` for the
HA-free suite, Node for `panel.js`'s own tests, a throwaway Home
Assistant 2026.8.3 container (`docker/compose.yaml`) for the two test
tiers `operations.py` needs.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`
— Decision 13 (the 2026-09-03 ruling this reverses, in the paragraph
starting "Nachtrag vom 2026-09-03"), and "Offene Punkte" → "Umkehrbarkeit
endet an einem nie aufgezeichneten Stand" (the three options; this plan
builds option 2). GitHub issue
[#18](https://github.com/PPP01/ha-dashboard-history/issues/18) is the
English mirror of that entry and the tracking issue to close once this
ships.

## Global Constraints

- **No shelling out to `git`.** Not touched by this plan — no new git
  operations, only a new decision around an existing one.
- **No monkey-patching Home Assistant internals.** The new test tier for
  `operations.py` (Task 1) fakes this integration's own `snapshot.py`
  functions on the `operations` module object, never anything of
  Home Assistant's — see that task's test file docstring for why that
  is not the same thing.
- **Nothing blocks Home Assistant's startup.** Not touched — this plan
  adds no new startup-path code.
- **`operations.py` is not one of the seven HA-free modules** (it is not
  in the list: `yaml_io.py`, `analyze.py`, `restore.py`, `versions.py`,
  `store.py`, `report.py`, `keys.py`). It imports
  `homeassistant.core`, so plain `python3 -m pytest tests/` cannot
  import it at all — confirmed: `python3 -c "import homeassistant"`
  fails on the development machine. Every test this plan adds for it
  therefore runs inside the throwaway container, at one of the two
  tiers `CLAUDE.md` already documents for exactly this reason.
- **Every service and every WebSocket command requires admin rights.**
  Not touched — the new field rides the same already-admin-gated
  commands.
- **Nothing is written without a preview.** Not weakened — the new
  refusal is stricter than today's behaviour, not looser; the escape
  hatch only ever restores today's behaviour, one call at a time. In
  the panel that means only after a person has already seen the
  refusal, since that is the only door `override_unrecorded_state`
  has there (Task 5). A service or WebSocket caller can set it on the
  very first call, the same as `confirm` itself — this is a contract
  the panel's UI observes by construction, not one the field itself
  enforces.

---

## File Structure

- **Modify:** `custom_components/dashboard_history/operations.py` — new
  helper `_refuse_unrecorded_state`, new parameter on the three write
  operations.
- **Modify:** `custom_components/dashboard_history/services.py` and
  `custom_components/dashboard_history/services.yaml` — new optional
  field on three service schemas.
- **Modify:** `custom_components/dashboard_history/websocket_api.py` —
  new optional field on the same three WebSocket commands.
- **Modify:** `custom_components/dashboard_history/panel.js` — `_confirm`
  gains a retry step; the three callers and the separate "Replace" flow
  (`_openReplace`) pass the override through.
- **Create:** `tests/integration/run_unrecorded_state_refusal.py` — the
  third test tier (container, no live instance), for the decision logic
  itself.
- **Modify:** `tests/integration/run_checks.py` — one new end-to-end
  check against the real running instance.
- **Modify:** `tests/test_panel_behaviour.py` — Node tests for the new
  panel dialog step.
- **Modify:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`
  and `docs/superpowers/status.md` — Decision 23.
- **Modify:** `README.md` — one line that overclaims today, corrected
  once it is true.

---

### Task 1: `operations.py` — refuse, unless overridden

**Files:**
- Modify: `custom_components/dashboard_history/operations.py:235-821`
  (the three write operations and the space between them)
- Create: `tests/integration/run_unrecorded_state_refusal.py`

**Interfaces:**
- Consumes: `_keep_the_live_state(hass, store, key, current) -> str |
  None` (`operations.py:235`, unchanged by this task)
- Produces: `_refuse_unrecorded_state(lost: str | None, override: bool)
  -> dict | None` — `None` means proceed with the write; a dict means
  return it instead, unchanged, as the whole result. Every later task
  in this plan (services, WebSocket, panel) relies on the two keys
  that dict carries: `"applied": False` and `"unrecorded_state": True`,
  alongside an `"error"` string.
- Produces: an additional final parameter, `override_unrecorded_state:
  bool = False`, on `async_restore_deleted`, `async_restore_state`, and
  `async_undo_change` — the name every later task threads through.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/run_unrecorded_state_refusal.py`:

```python
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
```

Note on the mocking helper: `mock.AsyncMock(return_value=...)`, not a
bare coroutine object such as `asyncio.sleep(0, EDITED)`. This
scenario awaits each stubbed function more than once - `async_get_config`
twice, once per call to `async_restore_state` - and a coroutine object
can only be awaited once; an `AsyncMock` call builds a fresh one every
time instead. (The sanity assertion afterwards only reads
`get_config.await_count`; it makes no call of its own.) The `new=`
form is written out explicitly here rather than relying on
`patch.object`'s own async auto-detection (real, since Python 3.8, and
`return_value=EDITED` would likely have worked unchanged) - explicit
because this task should not depend on a reader trusting that
detection rather than seeing the `AsyncMock` in front of them.

- [ ] **Step 2: Run it and confirm it fails for the right reason**

```bash
docker compose -f docker/compose.yaml up -d
docker exec -i dashboard-history-test python3 - < tests/integration/run_unrecorded_state_refusal.py
```

Expected: every check fails or the script raises `AttributeError:
module 'operations' has no attribute '_refuse_unrecorded_state'` — that
is the right failure. If instead it fails with an `ImportError` or a
mocking error unrelated to the missing function, fix the test file
first; a red test for the wrong reason proves nothing.

- [ ] **Step 3: Write the minimal implementation**

Insert this function in `operations.py`, right after
`_keep_the_live_state` (after line 301, before `_as_dict` at line 304):

```python
def _refuse_unrecorded_state(lost: str | None, override: bool) -> dict | None:
    """The refusal Decision 23 asks for, or `None` to proceed with the write.

    `lost` is `_keep_the_live_state`'s report: `None` means the state
    just before this write is safely in the history, and nothing here
    applies - every other write in this module keeps going exactly as
    it always has. Anything else means it is not, and is about to be
    overwritten for good. Decision 23 reverses the 2026-09-03 ruling
    that let that write through anyway with only a note (GitHub issue
    #18): the note used to reach the panel only after the write, when
    the state it warned about no longer existed.

    `override` is that ruling's escape hatch, kept for the reason it
    was written for - a full disk refuses nothing either way, because
    the snapshot could not have been written regardless, and refusing
    there helps nobody at the moment a restore is wanted most. A caller
    that has already seen this refusal and asks again with
    `override=True` gets the write; `lost` is not read again once
    `override` is true; it already did its job by being reported once.

    The exact wording does not depend on `lost`'s own text on purpose:
    `_keep_the_live_state` already answers with the same one sentence
    for every failure it can have (a capture that raised, or a read
    that came back different), so there is no second cause to describe
    here that its own warning log line has not already named.
    """
    if lost is None or override:
        return None
    return {
        "applied": False,
        "error": (
            "what was on the dashboard just before this could not be "
            "recorded, so the write was refused - it would be lost for "
            "good otherwise. Pass override_unrecorded_state to write "
            "anyway despite that."
        ),
        "unrecorded_state": True,
    }
```

Then wire it into the three write operations. In `async_restore_deleted`
(around line 533), add the parameter and the check:

```python
async def async_restore_deleted(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    position: int,
    confirm: bool = False,
    override_unrecorded_state: bool = False,
) -> dict:
    """Put one disappeared card or view back."""
    _, text, error = await _state_at(hass, store, key, revision)
    if error is not None:
        return {"applied": False, "error": error}
    live = await async_get_config(hass, key)
    plan = await hass.async_add_executor_job(_reinsertion, text, live or {}, position, key)
    if "error" in plan:
        return {"applied": False, "error": plan["error"]}
    diff, explanation = plan["diff"], plan["explanation"]
    if not confirm:
        return {"applied": False, "preview": diff, "explanation": explanation}
    lost = await _keep_the_live_state(
        hass, store, key, plan["live_text"] if live is not None else None
    )
    refusal = _refuse_unrecorded_state(lost, override_unrecorded_state)
    if refusal is not None:
        return refusal
    await async_save_config(hass, key, plan["restored"])
    result = {
        "applied": True,
        "preview": diff,
        "explanation": explanation,
        "restored": plan["item"].label,
    }
    if lost:
        result["note"] = lost
    return result
```

In `async_restore_state` (around line 602), same parameter, and the
check goes in the `else` branch only — a recreated (`missing`) dashboard
has no live state to lose, so there is nothing to refuse:

```python
async def async_restore_state(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
    keep_as_version: dict | None = None,
    override_unrecorded_state: bool = False,
) -> dict:
    ...
    created = False
    note: str | None = None
    if missing:
        ...
        created = True
    else:
        note = await _keep_the_live_state(
            hass, store, key, live_text if live is not None else None
        )
        refusal = _refuse_unrecorded_state(note, override_unrecorded_state)
        if refusal is not None:
            return refusal
    kept = None
    if keep_as_version is not None:
        ...
    await async_save_config(hass, key, target)
    ...
```

In `async_undo_change` (around line 693), the parameter, and the check
merges into the `answer` dict already built by the preview step rather
than replacing it — `answer` may already carry `preview`/`explanation`
when the caller asked for them:

```python
async def async_undo_change(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision: str,
    confirm: bool = False,
    preview: bool = False,
    override_unrecorded_state: bool = False,
) -> dict:
    ...
    if not confirm:
        return answer
    lost = await _keep_the_live_state(
        hass, store, key, live_text if live is not None else None
    )
    refusal = _refuse_unrecorded_state(lost, override_unrecorded_state)
    if refusal is not None:
        return {**answer, **refusal}
    await async_save_config(hass, key, result)
    answer["applied"] = True
    if lost:
        answer["note"] = lost
    return answer
```

- [ ] **Step 4: Run it and confirm it passes**

```bash
docker exec -i dashboard-history-test python3 - < tests/integration/run_unrecorded_state_refusal.py
```

Expected: `17 of 17 checks passed` (five from the decision matrix, four
each from the three write-operation scenarios - `restore_state`,
`restore_deleted`, `undo_change`), `0 Failed`.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/operations.py \
        tests/integration/run_unrecorded_state_refusal.py
git commit -m "Refuse a restore that cannot record the state it replaces

_keep_the_live_state already tries to snapshot the live state before
every write and only ever answers with a note, never a refusal - the
2026-09-03 ruling behind that let the write through regardless, and
the note reached the panel only after the state it warned about was
already gone (issue #18). A new override_unrecorded_state parameter on
the three callers keeps that ruling's escape hatch for the case it was
written for, on request rather than by default.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 2: `services.py` and `services.yaml` — the escape hatch as a field

**Files:**
- Modify: `custom_components/dashboard_history/services.py:75-103,177-190`
- Modify: `custom_components/dashboard_history/services.yaml:76-163`

**Interfaces:**
- Consumes: `override_unrecorded_state: bool = False` on
  `operations.async_restore_deleted`/`async_restore_state`/`async_undo_change`
  (Task 1).
- Produces: the same field, under the same name, reachable from
  Developer Tools → Services and from any automation.

No test of its own — `run_checks.py`'s existing WebSocket checks (Task
4) exercise a schema field of exactly this shape (`vol.Optional(...,
default=False): bool`) for `confirm` already; this task is one
assignment and one schema line per service, verified by the
integration test in Task 4 calling the *service* form is out of scope
(the existing suite only ever calls these through the WebSocket door),
so this task is verified by reading the diff and by Task 4's WebSocket
check passing with the field wired the same way.

- [ ] **Step 1: Add the field to the three service handlers**

In `services.py`, extend the three handlers:

```python
    async def restore_deleted(call: ServiceCall) -> dict:
        return await operations.async_restore_deleted(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            call.data["position"],
            bool(call.data.get("confirm")),
            bool(call.data.get("override_unrecorded_state")),
        )

    async def restore_state(call: ServiceCall) -> dict:
        return await operations.async_restore_state(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            call.data.get("confirm", False),
            call.data.get("keep_as_version"),
            bool(call.data.get("override_unrecorded_state")),
        )

    async def undo_change(call: ServiceCall) -> dict:
        return await operations.async_undo_change(
            hass,
            store,
            call.data["dashboard"],
            call.data["revision"],
            bool(call.data.get("confirm")),
            override_unrecorded_state=bool(call.data.get("override_unrecorded_state")),
        )
```

`undo_change` needs `override_unrecorded_state` passed by keyword: its
positional slot 6 in `async_undo_change` is `preview`, not this field
(see the signature from Task 1) — a positional call here would silently
set `preview` instead.

- [ ] **Step 2: Add the schema field to the three registrations**

```python
        ("restore_deleted", restore_deleted, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Required("position"): int,
            vol.Optional("confirm", default=False): bool,
            vol.Optional("override_unrecorded_state", default=False): bool,
        })),
        ("restore_state", restore_state, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Optional("confirm", default=False): bool,
            vol.Optional("keep_as_version"): KEEP_AS_VERSION,
            vol.Optional("override_unrecorded_state", default=False): bool,
        })),
        ("undo_change", undo_change, DASHBOARD.extend({
            vol.Required("revision"): cv.string,
            vol.Optional("confirm", default=False): bool,
            vol.Optional("override_unrecorded_state", default=False): bool,
        })),
```

- [ ] **Step 3: Document the field in `services.yaml`**

Add, right after each of the three `confirm:` field blocks (after line
104 for `restore_deleted`, after line 127 for `restore_state`, after
line 162 for `undo_change`):

```yaml
    override_unrecorded_state:
      description: >-
        Write anyway even though the state on the dashboard right now
        could not be safely recorded first. Without this, such a write
        is refused - the recorded history would otherwise lose the one
        state it could not confirm before overwriting it. Rare: it only
        matters when the repository could not be read or written at the
        exact moment this ran.
      default: false
      selector:
        boolean:
```

- [ ] **Step 4: Verify the schema loads**

```bash
python3 -c "
import ast
ast.parse(open('custom_components/dashboard_history/services.py').read())
"
python3 -c "
import yaml
yaml.safe_load(open('custom_components/dashboard_history/services.yaml'))
print('services.yaml parses')
"
```

Expected: both succeed with no output beyond the print. This is a
syntax check only — `voluptuous` and Home Assistant itself are not
importable on the development machine, so the schema's actual
acceptance is exercised for real in Task 4.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml
git commit -m "Expose override_unrecorded_state on three services

Threads the escape hatch Decision 23 adds through the service door
the same way confirm already reaches operations.py, so an automation
can use it exactly like any other field here.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 3: `websocket_api.py` — the same field for the panel's door

**Files:**
- Modify: `custom_components/dashboard_history/websocket_api.py:112-165`

**Interfaces:**
- Consumes: `override_unrecorded_state: bool = False` (Task 1).
- Produces: the same field on the three WebSocket commands, which
  Task 4's `run_checks.py` addition calls directly, and which
  `panel.js` (Task 5) sends.

- [ ] **Step 1: Add the field to the three command schemas and their `lambda`s**

```python
    _command(
        f"{DOMAIN}/restore_deleted",
        {
            **_DASHBOARD,
            **_REVISION,
            vol.Required("position"): int,
            vol.Optional("confirm", default=False): bool,
            vol.Optional("override_unrecorded_state", default=False): bool,
        },
        operations.async_restore_deleted,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "position": msg["position"],
            "confirm": msg["confirm"],
            "override_unrecorded_state": msg["override_unrecorded_state"],
        },
    ),
    _command(
        f"{DOMAIN}/restore_state",
        {
            **_DASHBOARD,
            **_REVISION,
            vol.Optional("confirm", default=False): bool,
            vol.Optional("keep_as_version"): KEEP_AS_VERSION,
            vol.Optional("override_unrecorded_state", default=False): bool,
        },
        operations.async_restore_state,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "confirm": msg["confirm"],
            "keep_as_version": msg.get("keep_as_version"),
            "override_unrecorded_state": msg["override_unrecorded_state"],
        },
    ),
    _command(
        f"{DOMAIN}/undo_change",
        {
            **_DASHBOARD,
            **_REVISION,
            vol.Optional("confirm", default=False): bool,
            vol.Optional("preview", default=False): bool,
            vol.Optional("override_unrecorded_state", default=False): bool,
        },
        operations.async_undo_change,
        lambda msg: {
            "key": msg["dashboard"],
            "revision": msg["revision"],
            "confirm": msg["confirm"],
            "preview": msg["preview"],
            "override_unrecorded_state": msg["override_unrecorded_state"],
        },
    ),
```

- [ ] **Step 2: Verify it parses**

```bash
python3 -c "
import ast
ast.parse(open('custom_components/dashboard_history/websocket_api.py').read())
"
```

Expected: no output, no error. As in Task 2, real acceptance is
verified in Task 4, where the field is actually exercised against a
running instance.

- [ ] **Step 3: Commit**

```bash
git add custom_components/dashboard_history/websocket_api.py
git commit -m "Expose override_unrecorded_state on three WebSocket commands

Same field as the services gained, for the door the panel uses.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 4: `run_checks.py` — the real refusal, against a real instance

**Files:**
- Modify: `tests/integration/run_checks.py`

**Interfaces:**
- Consumes: the WebSocket commands from Task 3, over a real connection
  (`Socket`, already defined in this file); `CONFIG` (already defined,
  line 48) as the host path to the running instance's configuration
  directory.
- Produces: nothing further tasks consume — this is the end-to-end
  proof the other tiers cannot give, and stops here.

- [ ] **Step 1: Add `REPO_DIRNAME` next to the existing `EVENT_HISTORY_UPDATED` extraction**

Right after the existing block that builds `EVENT_HISTORY_UPDATED`
(after line 47), add the same pattern for the one other constant this
check needs — `run_checks.py` cannot `import` `const.py` either, for
the same reason it does not import `operations.py`: `const.py` imports
`homeassistant.const`.

```python
REPO_DIRNAME = re.search(
    r'^REPO_DIRNAME = "([^"]+)"',
    (
        pathlib.Path(__file__).resolve().parents[2]
        / "custom_components"
        / "dashboard_history"
        / "const.py"
    ).read_text(encoding="utf-8"),
    re.M,
).group(1)
```

- [ ] **Step 2: Add a repository-locking helper near `CONFIG`/`TOKEN_FILE`**

Two earlier approaches were tried against this project's own throwaway
container on 2026-09-22 and both failed, for two different reasons -
recorded here because the second failure is not obvious and a third
attempt should not have to rediscover it:

1. **`chmod`.** Home Assistant runs there as UID 0, and a permission
   bit protects nobody from root, recursive or not.
   `HistoryStore.write_snapshot` went through unchanged under a fully
   `0o500`-locked `.git`.
2. **Renaming `.git` out of the way.** Fixes (1), but breaks something
   this check needs working: `store.resolve(revision)` - called by
   `_state_at`, ahead of every write operation, ahead of
   `_keep_the_live_state` - now fails too, with "unknown revision"
   rather than the refusal this check is about; the guard this plan
   adds is never reached. Worse, a save made while `.git` is missing
   does not just fail - dulwich's own `Repo.init`-on-demand behaviour
   somewhere in this path (confirmed by reproducing it against a
   scratch repository) creates a **new, empty** `.git` in its place,
   which then collides with renaming the original one back: the
   rename-back step itself fails, and the repository is left with the
   original `.git` still hidden under `.git-locked-for-test` and a
   fresh, historyless one live in its place. Not a recoverable lock,
   a corruption.

What works: dulwich's own lock file, the same contention this
integration already anticipates and handles (`store.py` imports and
catches `dulwich.file.FileLocked` for exactly this reason - see the
comment beside `except FileLocked as exc:`). Creating
`.git/index.lock` exclusively before `porcelain.add`/`commit` run
makes them raise `FileLocked`, confirmed against a scratch repository
even as root, while every *read* - `store.resolve`, `store.read_at` -
keeps working unchanged, because reads never touch the index lock.
That is exactly the shape Decision 23 is about: a repository that can
be read but not written.

```python
def _lock_repository(locked: bool) -> None:
    """Make new commits to the repository fail, without touching reads.

    Creates or removes `.git/index.lock` - see the two rejected
    alternatives recorded above this function for why neither `chmod`
    nor renaming `.git` away works here. `os.O_EXCL` makes the create
    fail loudly (`FileExistsError`) if a lock is already there rather
    than silently overwriting one - which would either mean this
    function was called out of order, or that a previous run's lock
    survived (see the note on power loss at the call site below).
    """
    lock_path = CONFIG / REPO_DIRNAME / ".git" / "index.lock"
    if locked:
        os.close(os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
    else:
        lock_path.unlink()
```

**On a crash between creating and removing this lock - a power loss
being the sharpest case, since not even a `finally` block runs then:**
no in-process cleanup can promise anything survives that, for this
lock file or for any of the two rejected alternatives above (a renamed
`.git` would be left renamed just the same way). What is worth having
is a bound on the damage and a self-heal on the next run rather than a
silent, permanent wedge - `index.lock` left behind blocks every write
across every dashboard, forever, until someone or something removes
it. That bound is not a fix: a run that dies mid-lock still needs the
*next* run of this file to notice and clear it, exactly the way
`repair_pending_forget` self-heals a crashed `forget` at the next Home
Assistant start rather than promising the crash cannot happen. Step 3
below opens the check with exactly that self-heal, before anything
else in it runs. `run_checks.py` already imports `os` (line 25) - no
new import needed.

- [ ] **Step 3: Write the failing check**

Add near the other `restore_state` checks (the file's existing style:
a local `async def check_...(access)`, called from `main` the same way
its neighbours are - match whichever calling convention the section
immediately above this one uses):

```python
async def check_an_unrecorded_state_is_refused_and_can_be_overridden(access):
    """Decision 23, against the real thing rather than a fake registry.

    `run_unrecorded_state_refusal.py` proves the decision logic and
    all three write operations in isolation; this proves the one thing
    that cannot be faked - that a repository genuinely unable to
    record a state produces exactly the gap `_keep_the_live_state` is
    meant to catch - and that both answers, refused then overridden,
    come back through the real WebSocket door, plus once through the
    real service door.
    """
    stale_lock = CONFIG / REPO_DIRNAME / ".git" / "index.lock"
    if stale_lock.exists():
        # Bounds the one failure nothing here can prevent: a crash -
        # a power loss being the sharpest case - between this file
        # creating the lock and removing it again. Left in place, it
        # would block every write to every dashboard, forever, not
        # only this check's own next attempt.
        print(
            f"  note: removing a leftover {stale_lock} from an earlier, "
            "interrupted run before continuing"
        )
        stale_lock.unlink()

    key = "dh-unrecorded-gap"

    async def ready(socket) -> None:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        if not any(entry.get("url_path") == key for entry in listed):
            await socket.call("lovelace/dashboards/create", url_path=key, title=key)
            await asyncio.sleep(3)

    async def save(socket, config: dict) -> list:
        await socket.call("lovelace/config/save", url_path=key, config=config)
        return await _wait_until_recorded(socket, key)

    recorded_state = {
        "views": [{"title": "Home", "cards": [{"type": "markdown", "content": "# recorded"}]}]
    }
    never_recorded = {
        "views": [{"title": "Home", "cards": [{"type": "markdown", "content": "# never recorded"}]}]
    }

    async with Socket(access) as socket:
        await ready(socket)
        changes = await save(socket, recorded_state)
        revision = changes[0]["revision"]

        _lock_repository(locked=True)
        try:
            # Bypasses nothing on the Home Assistant side - this is an
            # ordinary save. What is missing is the repository's ability
            # to hear it: `_keep_the_live_state`'s own attempt to record
            # this state, made fresh on the very next call below, fails
            # for as long as the lock stands.
            await socket.call("lovelace/config/save", url_path=key, config=never_recorded)

            refused = await socket.call(
                "dashboard_history/restore_state",
                dashboard=key,
                revision=revision,
                confirm=True,
            )
            check(
                "a restore that cannot record the live state first is refused",
                refused.get("applied") is False and refused.get("unrecorded_state") is True,
                str(refused),
            )
            live = await socket.call("lovelace/config", url_path=key)
            check(
                "and the dashboard is untouched by the refusal",
                live == never_recorded,
                str(live),
            )

            # A refused write must not have side effects either - a
            # version asked for in the same call must not appear, or
            # the escape hatch would need one of its own.
            refused_with_version = await socket.call(
                "dashboard_history/restore_state",
                dashboard=key,
                revision=revision,
                confirm=True,
                keep_as_version={"title": "should never exist"},
            )
            versions_after_refusal = await socket.call(
                "dashboard_history/versions", dashboard=key
            )
            check(
                "a refused restore marks no version either",
                refused_with_version.get("applied") is False
                and not any(
                    v.get("title") == "should never exist"
                    for v in versions_after_refusal.get("versions", [])
                ),
                str(versions_after_refusal),
            )

            overridden = await socket.call(
                "dashboard_history/restore_state",
                dashboard=key,
                revision=revision,
                confirm=True,
                override_unrecorded_state=True,
            )
            check(
                "the same call with the escape hatch writes anyway",
                overridden.get("applied") is True,
                str(overridden),
            )
        finally:
            _lock_repository(locked=False)

        live = await socket.call("lovelace/config", url_path=key)
        check(
            "and the dashboard now holds the restored state",
            live == recorded_state,
            str(live),
        )

        # The everyday case has to survive all of this: a restore with
        # nothing unrecorded in its way needs no override and is not
        # asked to refuse anything. Targets the *earlier* recorded_state
        # revision, not the state just saved - restoring to the state
        # already live answers "already identical" before confirm is
        # even reached (operations.py:628), which would prove nothing
        # about this decision either way.
        await save(socket, never_recorded)
        ordinary = await socket.call(
            "dashboard_history/restore_state",
            dashboard=key,
            revision=revision,
            confirm=True,
        )
        check(
            "an ordinary restore is unaffected and needs no override",
            ordinary.get("applied") is True and "unrecorded_state" not in ordinary,
            str(ordinary),
        )
```

Call it from `main` next to the other `restore_state` checks, wrapped
the same way its neighbours are (`asyncio.run(...)` if that is the
prevailing style at that point in the file).

Then add one call through the *service* door rather than WebSocket, at
the end of `check_an_unrecorded_state_is_refused_and_can_be_overridden`
itself, still inside the `async with Socket(access) as socket:` block
- `key` and `revision` only exist inside that function, so this cannot
sit next to the admin-only checks around line 3346 the way an earlier
draft of this plan said; `run_permissions` (line 3309) is the pattern
to copy from, not the place to add to. That function builds its own
`headers = {"Authorization": f"Bearer {access}"}` from the same
`access: str` every `check_...(access)` function already receives -
`check_an_unrecorded_state_is_refused_and_can_be_overridden` needs the
same line, since nothing defines `headers` inside it otherwise:

```python
        # Same field, the other door: services.py must accept it too,
        # not only websocket_api.py - nothing above this line has
        # called restore_state as a service at all. `headers` is not
        # inherited from anywhere else in this function - built the
        # same way `run_permissions` (line 3309) builds it, from the
        # same `access` token this function already received.
        headers = {"Authorization": f"Bearer {access}"}
        _lock_repository(locked=True)
        try:
            await socket.call("lovelace/config/save", url_path=key, config=never_recorded)
            answer = requests.post(
                f"{BASE}/api/services/dashboard_history/restore_state?return_response",
                headers=headers,
                json={
                    "dashboard": key,
                    "revision": revision,
                    "confirm": True,
                    "override_unrecorded_state": True,
                },
                timeout=30,
            )
            body = answer.json().get("service_response", {})
            check(
                "the service door accepts override_unrecorded_state too",
                answer.status_code == 200 and body.get("applied") is True,
                f"HTTP {answer.status_code} {body}",
            )
        finally:
            _lock_repository(locked=False)
```

- [ ] **Step 4: Run it and confirm it fails for the right reason**

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

Expected: the new checks fail (or the WebSocket call errors on an
unknown field, if Tasks 2-3 have not landed yet in this working copy -
run this only once Tasks 1-3 are committed). If everything else in the
file still passes, the new failures are isolated to this addition.

- [ ] **Step 5: Confirm it passes**

```bash
python3 tests/integration/run_checks.py
```

Expected: the whole file's tally increases by exactly the seven new
checks, all passing, and nothing already there regresses. If the
"untouched by the refusal" check fails, verify `_lock_repository` is
actually reaching the container's real `.git` directory - `CONFIG`
must resolve to the same host path the compose file mounts, which
`docker/README.md` documents. If `.git/index.lock` is left behind
after a failed run, the self-heal at the top of the check clears it on
the next attempt automatically - see Step 6 only if a manual, immediate
cleanup is wanted instead.

- [ ] **Step 6: Clean up if the run failed midway**

Only needed if Step 4 or 5 exited before the check's own `finally` ran
*and* before the self-healing check at the top of the same function
got a chance to run on a later attempt:

```bash
python3 -c "
import pathlib, os
root = pathlib.Path(os.environ.get('HA_TEST_CONFIG', '../ha-dashboard-history-test/config')) / 'dashboard_history'
lock = root / '.git' / 'index.lock'
if lock.exists():
    lock.unlink()
"
```

- [ ] **Step 7: Commit**

```bash
git add tests/integration/run_checks.py
git commit -m "Check Decision 23 against a real running instance

Locks .git/index.lock to reproduce the one failure
_keep_the_live_state exists for without touching Home Assistant -
neither a chmod (this container's Home Assistant runs as root) nor
renaming .git away (breaks store.resolve and can leave a stray, empty
.git behind) survive contact with the real thing. Proves the refusal,
that a refusal marks no version either, the override, and that an
ordinary restore is unaffected - over both the WebSocket and the
service door.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 5: `panel.js` — a second question, only where it applies

**Files:**
- Modify: `custom_components/dashboard_history/panel.js:1853-2072`
  (`_confirm`), `:2124-2225` (`_openReplace`), `:2864-2923` (the three
  `request` callbacks)
- Modify: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `{applied: false, error: string, unrecorded_state: true}`
  from any of the three WebSocket commands (Tasks 1 and 3), exactly
  where every other refusal already arrives (`applied?.error` is
  already the first thing `_confirm` checks).
- Produces: a fourth argument on every `request(confirm, keep,
  dashboard, override)` callback - `_restoreItem`, `_restoreState`,
  `_undoChange` all build one - and a new shared method,
  `_confirmOverride(dialog, message)`, returning whether the person
  chose to write anyway.

- [ ] **Step 1: Write the failing Node test**

Add to `tests/test_panel_behaviour.py`, following the file's existing
`_KEEP_FAILED`/`_run_in_node`/fixture pattern exactly (see lines
905-983 for the closest sibling: same `dialog()`/`press()` shape, same
`_call` stand-in reading `extra`):

Modelled on `_OPEN_REPLACE_BOTH` (lines 6482-6536), not on
`_KEEP_FAILED`: a hand-resolved queue of calls (`calls.push({ type,
extra, resolve })`, resolved one at a time from the test) makes the
exact sequence explicit instead of inferring it from how many
`settle()`s have passed - which of the three refusals below turned out
to matter, since the earlier canned-response version of this test
made the wrong call the one it asserted on. `_reloadAfterWrite` is
stubbed to `async () => null` for the same reason `_OPEN_REPLACE_BOTH`
stubs it: `_confirm` also calls it after a successful write, and
without a stand-in its own request would join the same queue and shift
every index below by one.

```python
_UNRECORDED_OVERRIDE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "simple";
el._changes = [{ revision: "a" }, { revision: "b" }];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();
el._select = async () => {};
el._loadDashboardsQuietly = async () => {};
el._reloadAfterWrite = async () => null;

const dialog = () => el.shadowRoot.querySelector("dialog.confirm");
const preview = { applied: false, preview: "-a\\n+b", explanation: { groups: [], note: "one card removed" } };
const refusal = {
  applied: false,
  error: "what was on the dashboard just before this could not be recorded",
  unrecorded_state: true,
};

// Scenario 1: refused, then told to write anyway.
let calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

el._error = "";
const first = el._restoreState("b", "Back to this version");
await settle();
calls[0].resolve(preview);
await settle();
dialog().close("apply");
await settle();
calls[1].resolve(refusal);
await settle();
const secondDialogBody = dialog().querySelector(".body").innerHTML;
dialog().close("apply");
await settle();
const overrideCall = { type: calls[2]?.type, extra: { ...calls[2]?.extra } };
calls[2].resolve({ applied: true });
await first;

const scenario1 = {
  callCount: calls.length,
  overrideCall,
  secondDialogMentionsIt: secondDialogBody.includes(
    "what was on the dashboard just before this could not be recorded",
  ),
  error: el._error || "",
};

// Scenario 2: refused, and the person backs out instead.
calls = [];
el._error = "";
const second = el._restoreState("b", "Back to this version");
await settle();
calls[0].resolve(preview);
await settle();
dialog().close("apply");
await settle();
calls[1].resolve(refusal);
await settle();
dialog().close("cancel");
await second;

const scenario2 = { callCount: calls.length, error: el._error || "" };

// Scenario 3: an ordinary refusal - no unrecorded_state marker at all
// - must not offer this second question. Only the one specific
// refusal does.
calls = [];
el._error = "";
const third = el._restoreState("b", "Back to this version");
await settle();
calls[0].resolve(preview);
await settle();
dialog().close("apply");
await settle();
calls[1].resolve({ applied: false, error: "some other refusal" });
await third;

const scenario3 = { callCount: calls.length, error: el._error || "" };

console.log(JSON.stringify({ scenario1, scenario2, scenario3 }));
"""


@pytest.fixture(scope="session")
def unrecorded_override(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "unrecorded_override", _UNRECORDED_OVERRIDE)


def test_the_override_dialog_is_offered_only_after_that_specific_refusal(
    unrecorded_override,
):
    assert unrecorded_override["scenario1"]["secondDialogMentionsIt"]


def test_choosing_to_write_anyway_resends_with_the_override_flag(unrecorded_override):
    scenario1 = unrecorded_override["scenario1"]
    # Preview, the refused confirm, and the retry - nothing more.
    assert scenario1["callCount"] == 3
    assert scenario1["overrideCall"]["type"] == "restore_state"
    assert scenario1["overrideCall"]["extra"]["confirm"] is True
    assert scenario1["overrideCall"]["extra"]["override_unrecorded_state"] is True
    assert scenario1["error"] == ""


def test_backing_out_of_the_second_dialog_sends_nothing_further(unrecorded_override):
    scenario2 = unrecorded_override["scenario2"]
    # Preview and the refused confirm only - no third call was made.
    assert scenario2["callCount"] == 2
    assert scenario2["error"] == (
        "what was on the dashboard just before this could not be recorded"
    )


def test_an_ordinary_refusal_is_not_offered_the_override_dialog(unrecorded_override):
    scenario3 = unrecorded_override["scenario3"]
    assert scenario3["callCount"] == 2, "no retry - this refusal carries no unrecorded_state marker"
    assert scenario3["error"] == "some other refusal"
```

The same override retry lives a second time in `_openReplace`, on its
own queue-of-calls convention (`_OPEN_REPLACE_BOTH`, lines 6482-6536:
two preview calls up front, one per candidate, then the write). Add
its own scenario alongside it in the same style:

```python
_OPEN_REPLACE_UNRECORDED = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._changes = [
  { revision: "a", previous: "b", same_as_now: false, timestamp: 20 },
  { revision: "b", previous: "c", same_as_now: false, timestamp: 10 },
];
el.shadowRoot = node();
el._recorded = () => Promise.resolve();
el._reloadAfterWrite = async () => null;

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const done = el._openReplace("a");
await settle();
calls[0].resolve({ preview: "-a\\n+b", explanation: { groups: [], note: "" } });
calls[1].resolve({ preview: "-c\\n+d", explanation: { groups: [], note: "" } });
await settle();

const dialog = el.shadowRoot.querySelector("dialog.replace");
dialog.close("apply");
await settle();
calls[2].resolve({
  applied: false,
  error: "what was on the dashboard just before this could not be recorded",
  unrecorded_state: true,
});
await settle();
const secondDialogBody = dialog.querySelector(".body").innerHTML;
// The candidate picker `_paintReplace` filled in before the first
// Apply must not still be standing beside this question.
const leftoverChoice = dialog.querySelector("[data-replace-choice]").innerHTML;
dialog.close("apply");
await settle();
const overrideCall = { type: calls[3]?.type, extra: { ...calls[3]?.extra } };
calls[3].resolve({ applied: true });
await done;

console.log(JSON.stringify({
  callCount: calls.length,
  secondDialogMentionsIt: secondDialogBody.includes(
    "what was on the dashboard just before this could not be recorded",
  ),
  leftoverChoice,
  overrideCall,
}));
"""


@pytest.fixture(scope="session")
def open_replace_unrecorded(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "open_replace_unrecorded", _OPEN_REPLACE_UNRECORDED
    )


def test_replace_also_offers_to_write_anyway_when_refused_for_it(
    open_replace_unrecorded,
):
    assert open_replace_unrecorded["secondDialogMentionsIt"]
    assert open_replace_unrecorded["leftoverChoice"] == ""
    assert open_replace_unrecorded["callCount"] == 4
    assert open_replace_unrecorded["overrideCall"]["extra"]["override_unrecorded_state"] is True
```

- [ ] **Step 2: Run it and confirm it fails for the right reason**

```bash
python3 -m pytest tests/test_panel_behaviour.py -k unrecorded -v
```

Expected: `node` must be present (the file skips visibly otherwise -
confirm it is not skipping before reading failures as real ones).
Expected failure: the second dialog never reopens, so
`secondDialogBody` still shows the original diff, or the second `_call`
never carries `override_unrecorded_state`.

- [ ] **Step 3: Implement the retry in `_confirm`**

Change `const applied = await this._guard(...)` (line 2005) to `let`,
and add the retry immediately after it (after the block ending at line
2014, before the `kept_as_version` handling at line 2015):

```js
    let applied = await this._guard(async () => {
      const result = await this._call(...request(true, keep, asked));
      await recorded;
      return result;
    }, mine);
    // Decision 23: this specific refusal, and only this one, gets a
    // second question rather than a final answer - it is the one
    // refusal with something a person can do about it on this same
    // screen, right now, having just seen why.
    //
    // `dialog` above is no longer part of the document: `_guard` just
    // rendered around that call - entry and `finally` both call
    // `_render`, same as every other `_guard` - and `_render` replaces
    // the whole shadow root, open `<dialog>` included (`_answerFrom`'s
    // own note says so; this is the first place in `_confirm` that
    // needs a dialog reference *after* a `_guard` call rather than
    // only before one). A fresh lookup is required, and `mine()` is
    // checked again for the same reason `_guard` already checks it -
    // the person may have moved on to another dashboard while the
    // write was in flight.
    if (applied?.unrecorded_state && mine()) {
      const retryDialog = this.shadowRoot.querySelector("dialog.confirm");
      const proceed = await this._confirmOverride(retryDialog, applied.error);
      if (proceed && mine()) {
        const recordedAgain = this._recorded();
        applied = await this._guard(async () => {
          const result = await this._call(...request(true, keep, asked, true));
          await recordedAgain;
          return result;
        }, mine);
      }
    }
```

Add the shared method near `_answerFrom` (after line 2072, the end of
`_confirm`):

```js
  /**
   * Reuses whichever `<dialog>` is asking right now rather than
   * opening a second one on top of it: it is already inert and
   * already where the reader is looking. The caller looks that dialog
   * up fresh immediately before calling this - see the note at the
   * call site in `_confirm` for why the one it had a moment earlier is
   * already gone from the document.
   *
   * Clears every optional block either caller's dialog can carry
   * beside `.body` before asking this question: the keep-as-version
   * fields `_armKeep` fills in for `_confirm`, and the candidate
   * picker `_paintReplace` fills in for `_openReplace`. Both sit
   * outside `.body`, so overwriting `.body`'s own markup does not
   * reach them, and neither caller's normal repaint runs again before
   * this dialog is shown - without this, whichever of the two was
   * standing stays standing, contradicting a question that is
   * supposed to be about nothing but the write itself.
   */
  async _confirmOverride(dialog, message) {
    dialog.querySelector("h2").textContent = "Write anyway?";
    dialog.querySelector(".body").innerHTML = `<p>${escape(message)}</p>`;
    dialog.querySelector(".note").textContent = "";
    this._sayFootnote(dialog, "", []);
    const keepBlock = dialog.querySelector("[data-keep]");
    if (keepBlock) keepBlock.hidden = true;
    const replaceChoice = dialog.querySelector("[data-replace-choice]");
    if (replaceChoice) replaceChoice.innerHTML = "";
    const why = dialog.querySelector(".why");
    if (why) why.textContent = "";
    const applyButton = dialog.querySelector('.actions button[value="apply"]');
    applyButton.hidden = false;
    applyButton.textContent = "Write anyway";
    dialog.querySelector('.actions button[value="cancel"]').textContent = "Cancel";
    dialog.returnValue = "";
    dialog.showModal();
    return (await this._answerFrom(dialog)) === "apply";
  }
```

Verify while implementing this step whether `dialog.replace` also
carries a `.why` block or anything else beside `[data-replace-choice]`
that `_paintReplace` fills in outside `.body` (`dialogs.js:71`
mentions one) - clear it here too if so, the same way
`[data-replace-choice]` is cleared above.

Give the three `request` callbacks their fourth argument
(`_restoreItem` around line 2864, `_restoreState` around line 2876,
`_undoChange` around line 2902):

```js
  _restoreItem(revision, item) {
    this._confirm(
      `Put back: ${item.label}`,
      (confirm, keep, dashboard, override = false) => [
        "restore_deleted",
        {
          dashboard, revision, position: item.position, confirm,
          override_unrecorded_state: override,
        },
      ],
      false,
      { applyLabel: "Put back" },
    );
  }

  _restoreState(revision, title) {
    return this._confirm(
      title,
      (confirm, keep, dashboard, override = false) => [
        "restore_state",
        {
          dashboard,
          revision,
          confirm,
          override_unrecorded_state: override,
          ...(keep ? { keep_as_version: keep } : {}),
        },
      ],
      true,
      { applyLabel: title },
    );
  }

  _undoChange(revision) {
    const change = this._changeAt(revision);
    const made = change ? this._madeSince(change) : null;
    const kept =
      made ? ` and keeps the ${made} change${made === 1 ? "" : "s"} made since` : "";
    this._confirm(
      "Undo this change",
      (confirm, keep, dashboard, override = false) => [
        "undo_change",
        {
          dashboard, revision, confirm, preview: !confirm,
          override_unrecorded_state: override,
        },
      ],
      false,
      {
        intro: `Puts this change back${kept}.`,
        applyLabel: "Undo this change",
      },
    );
  }
```

And the same retry in `_openReplace` (the "Replace" flow, which calls
`restore_state` directly rather than through `_confirm`) — change
`const applied` at line 2198 to `let`, and insert the same block after
it, before `const failedKeep` at line 2208:

```js
    let applied = await this._guard(async () => {
      const result = await this._call("restore_state", {
        dashboard: asked,
        revision: target.revision,
        confirm: true,
        ...(keep ? { keep_as_version: keep } : {}),
      });
      await recorded;
      return result;
    }, mine);
    // Same reasoning as `_confirm`'s retry: `dialog` above is gone
    // from the document once `_guard` has rendered around this call,
    // so the retry looks up `dialog.replace` fresh rather than reusing
    // the reference this function already holds.
    if (applied?.unrecorded_state && mine()) {
      const retryDialog = this.shadowRoot.querySelector("dialog.replace");
      const proceed = await this._confirmOverride(retryDialog, applied.error);
      if (proceed && mine()) {
        const recordedAgain = this._recorded();
        applied = await this._guard(async () => {
          const result = await this._call("restore_state", {
            dashboard: asked,
            revision: target.revision,
            confirm: true,
            override_unrecorded_state: true,
            ...(keep ? { keep_as_version: keep } : {}),
          });
          await recordedAgain;
          return result;
        }, mine);
      }
    }
```

Confirmed while writing this plan (`dialogs.js:45`): `dialog.replace`
carries the same four selectors `_confirmOverride` reads - `h2`,
`.body`, `.note`, and both `.actions button[value=...]` - so no second,
explicit element-lookup argument is needed. What it carries *beside*
those - `[data-replace-choice]` and a `.why` block, both outside
`.body` per `dialogs.js:71` - is exactly what the note on
`_confirmOverride` above already accounts for.

- [ ] **Step 4: Run it and confirm it passes**

```bash
python3 -m pytest tests/test_panel_behaviour.py -k unrecorded -v
python3 -m pytest tests/test_panel_behaviour.py -v
```

Expected: the three new tests pass, and nothing already in this file
regresses — in particular the existing `_restoreState`/keep-as-version
tests around lines 850-1170, since `_confirm`'s ordinary (non-refused)
path must produce byte-identical behaviour to before this task.

- [ ] **Step 5: Exercise it in a real browser**

Per this project's own rule for frontend changes: type-checking and
the Node suite verify shape, not the feel of it.

```bash
docker compose -f docker/compose.yaml up -d
```

Open the panel, trigger a restore against the `dh-unrecorded-gap`
dashboard from Task 4 while the repository is locked - reuse Task 4's
`_lock_repository(locked=True)` from a Python shell against the same
`HA_TEST_CONFIG` path (a permission change has no effect here: this
container's Home Assistant runs as root, confirmed while writing Task
4). Confirm the first dialog, see the new "Write anyway?" question,
and check both outcomes (write anyway; cancel and see nothing
happened). Call `_lock_repository(locked=False)` again afterwards.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/panel.js \
        tests/test_panel_behaviour.py
git commit -m "Offer to write anyway when a restore is refused for it

_confirm and the Replace flow both reuse the same open dialog for a
second question, asked only when the refusal is this one and nothing
else - every other refusal still just stands.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

### Task 6: Documentation — Decision 23

**Files:**
- Modify: `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`
- Modify: `docs/superpowers/status.md`
- Modify: `README.md:19`

**Interfaces:** None — prose only, no code consumes this task.

- [ ] **Step 1: Add Decision 23 to the spec**

Insert right before `## Fehler- und Randfälle` (currently line 635),
after Decision 22 ends:

```markdown
23. **`_keep_the_live_state`s Fehlbetrag verweigert jetzt das Schreiben, statt es nur zu vermerken.** *(Löst den unter »Offene Punkte« festgehaltenen Fund vom 2026-09-17, GitHub-Issue [#18](https://github.com/PPP01/ha-dashboard-history/issues/18), im Sinne von Weg (2) aus jenem Eintrag.)*

    Die Festlegung vom 2026-09-03 (oben bei Entscheidung 13) lautete: Gelingt es `_keep_the_live_state` nicht, den gerade noch lebenden Stand vorher aufzuzeichnen, wird trotzdem geschrieben, und der Fehlbetrag kommt als Hinweis zurück — der das Panel aber erst *nach* dem Schreiben erreicht, wenn der Stand, vor dem er warnt, bereits fort ist. Das kehrt diese Festlegung um: **Gelingt das Aufzeichnen nicht, wird nicht geschrieben** — außer die aufrufende Seite verlangt es ausdrücklich.

    **Der Notausgang bleibt, aus demselben Grund, aus dem er 2026-09-03 gebraucht wurde.** Der volle Datenträger ist der Fall, an dem die alte Festlegung sich maß: Dort liest sich alles und schreibt sich nichts, und eine endgültige Verweigerung nützte in dem Moment niemandem, in dem die Wiederherstellung am dringendsten gebraucht wird. Ein neuer Parameter `override_unrecorded_state` (Vorgabe `false`) an `async_restore_deleted`, `async_restore_state` und `async_undo_change` — den drei einzigen Aufrufern von `_keep_the_live_state` — lässt den Schreibvorgang trotzdem zu; der Fehlbetrag wird dann, wie bisher, als `note` mitgeteilt statt das Schreiben zu verhindern.

    **Die Verweigerung trägt ein eigenes Merkmal**, `unrecorded_state: true`, neben der gewohnten `error`-Zeile — nicht nur ein Text, weil das Panel zwischen dieser Ablehnung und jeder anderen unterscheiden muss: Nur hier bietet es den Notausgang an, jede andere Ablehnung bleibt eine, die stehenbleibt. Der Dialog stellt dazu, wo bisher nach »Apply« geschlossen wurde, eine zweite Frage — dasselbe `<dialog>`-Element, neu beschriftet — und schreibt nur, wenn dort ein zweites Mal ausdrücklich zugestimmt wird.

    **Zwei Prüfebenen, aus demselben Grund wie bei Entscheidung 22: `operations.py` importiert Home Assistant und ist damit für `pytest` unsichtbar, und die drei betroffenen Funktionen lesen zusätzlich Home Assistants Dashboard-Registrierung, die nur eine laufende Instanz hat.** `tests/integration/run_unrecorded_state_refusal.py` (dritter Weg, ohne laufende Instanz, mit einer um eine echte `HistoryStore` herum gefälschten Registrierung) prüft die Entscheidungslogik aller drei Schreiboperationen für sich — verweigert ohne, schreibt mit `override_unrecorded_state`. `run_checks.py` (zweiter Weg, echte Instanz) legt dafür kurzzeitig `.git/index.lock` an, bevor eine zweite Änderung gespeichert wird — dieselbe Sperrdatei, die `dulwich` bei einer gleichzeitigen Schreiboperation selbst anlegt, und die dieses Projekt schon an anderer Stelle als `FileLocked` abfängt —, und prüft beide Antworten über den echten WebSocket- und einmal auch über den Dienst-Aufruf. **Zwei einfachere Wege scheiterten zuerst:** Eine reine Rechteänderung schützt vor root nicht — am Prüfstand bestätigt lief Home Assistant dort als UID 0, ein rekursiv auf `0o500` gesetztes `.git` ließ `write_snapshot` unverändert durch. `.git` versuchsweise umzubenennen behob das, brach aber `store.resolve` noch vor dem neuen Schutz (»unknown revision« statt der erwarteten Ablehnung) und ließ dulwich beim nächsten Speichern ein neues, leeres `.git` anlegen — das Zurückbenennen scheiterte danach an genau diesem neuen Verzeichnis. Die Sperrdatei betrifft nur das Schreiben und lässt Lesen unangetastet, trifft also genau den Fall, um den es hier geht.

    **Nicht angefasst:** `_keep_the_live_state` selbst, die den Fehlbetrag weiterhin genauso ermittelt wie zuvor — nur was die drei Aufrufer mit einem gemeldeten Fehlbetrag tun, ändert sich.
```

Then update the "Offene Punkte" entry itself (currently lines 841-845):
strike the finding and its "Drei Wege"/"Stand der Willensbildung"
paragraphs, and append the resolution, following the exact pattern
Entscheidung 22's own "Gelöst am..." sentence used for its own prior
open point:

```markdown
- ~~**Umkehrbarkeit endet an einem nie aufgezeichneten Stand.** *(Gefunden am 2026-09-17 bei einem Review von Entscheidung 20. Betrifft Entscheidung 13, nicht Vorhaben K — K fasst `operations.py` nicht an.)* Hört der Rekorder einen Speichervorgang nicht — gespeichert während des HA-Starts, Ablagedatei von außen bearbeitet, Rekorder einmal gescheitert —, steht der Stand auf dem Dashboard in keinem Commit. Jede schreibende Operation versucht ihn vorher nachzutragen (`_keep_the_live_state`, `operations.py:235`), und das gelingt fast immer. **Gelingt es nicht, wird trotzdem geschrieben** (Festlegung vom 2026-09-03, oben bei Entscheidung 13), und dieser Stand ist damit endgültig fort. Der Hinweis darauf erreicht das Panel erst *nach* dem Schreiben (`panel.js:1650`). Es müssen zwei seltene Dinge zusammentreffen — eine Lücke im Verlauf und ein in diesem Moment nicht schreibbares Repository —, aber solange es möglich ist, stimmt der Satz »über jede Operation außer `forget` lässt sich sagen: umkehrbar« nicht.~~

  ~~**Drei Wege liegen ausgearbeitet vor, keiner ist gewählt:** (1) *Vorher warnen*...~~ ~~**Stand der Willensbildung (2026-09-17):** ...~~ **Gelöst am [DATUM DER UMSETZUNG] durch Entscheidung 23** (GitHub-Issue [#18](https://github.com/PPP01/ha-dashboard-history/issues/18)), im Sinne von Weg (2): Das Schreiben wird verweigert, sobald der Fehlbetrag nicht leer ist, mit einem ausdrücklichen Notausgang für genau den Fall, für den die alte Festlegung gebraucht wurde.
```

Replace `[DATUM DER UMSETZUNG]` with the actual date this task is
committed on (`date +%Y-%m-%d`) — the one deliberately open value in
this task, since a plan cannot know in advance which day it is carried
out.

- [ ] **Step 2: Update `status.md`**

Bump the `Stand:` date at the top of the file to the same date used
above. Replace the open-point bullet (currently lines 57-62):

```markdown
- ~~**Umkehrbarkeit endet an einem nie aufgezeichneten Stand.** *(Gefunden am
  2026-09-17.)* Misslingt das Nachtragen des lebenden Stands, wird trotzdem
  geschrieben, und ein Stand, den der Rekorder nie gehört hat, ist damit fort.
  Betrifft Entscheidung 13, nicht Vorhaben K.~~ **Behoben am [DATUM]**
  (Entscheidung 23, GitHub-Issue #18). Ein neuer Parameter
  `override_unrecorded_state` (Vorgabe `false`) an den drei Aufrufern von
  `_keep_the_live_state` kehrt die Festlegung vom 2026-09-03 um: Ohne ihn
  wird nicht mehr geschrieben, wenn der lebende Stand nicht vorher gesichert
  werden konnte — vorher wurde trotzdem geschrieben, mit einem Hinweis, der
  das Panel erst nach dem Schreiben erreichte. Der alte Notausgang bleibt,
  jetzt ausdrücklich statt stillschweigend: Wer ihn setzt, bekommt exakt das
  frühere Verhalten für diesen einen Aufruf.
```

- [ ] **Step 3: Correct the one README line this makes true**

`README.md:19` currently reads:

```markdown
- **Full safety net:** Automatic safety snapshots before any restore operation, ensuring you can always undo a rollback.
```

This was inaccurate in two directions at once, not only the one this
plan fixes: it implies a fresh snapshot is taken on every restore
(most of the time there is nothing to do - the state is already the
newest recorded entry, see `_keep_the_live_state`'s own docstring),
and "ensuring you can always undo a rollback" was the exact claim
issue #18 found a hole in. Replace with a description of what actually
happens - a check, caught up only if it is missing, refused by default
if it cannot be confirmed either way:

```markdown
- **Full safety net:** Before any restore, the current state is confirmed to be in the recorded history — caught up automatically if the recorder missed it — and a restore that cannot confirm this is refused by default, so a rollback can always itself be undone.
```

- [ ] **Step 4: Verify the edits render correctly**

```bash
git diff --check docs/superpowers/specs/2026-08-30-dashboard-history-design.md \
                  docs/superpowers/status.md \
                  README.md
```

Expected: no output (no trailing whitespace, no missing newline at EOF).

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-08-30-dashboard-history-design.md \
        docs/superpowers/status.md \
        README.md
git commit -m "Document Decision 23: restore refuses an unrecorded state

Records the resolution of the open point from 2026-09-17 (issue #18)
in the spec and status.md, and tightens the one README line that
overclaimed this until now.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## After This Plan

Once all six tasks are merged and pushed: comment on and close GitHub
issue [#18](https://github.com/PPP01/ha-dashboard-history/issues/18)
with a summary and the commit range, the same way issues #22 and #25
were closed in this project's history — that is a wrap-up action for
whoever merges this, not a task with its own tests.
