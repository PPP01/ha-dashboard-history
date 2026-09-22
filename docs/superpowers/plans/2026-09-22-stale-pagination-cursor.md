# Stale Pagination Cursor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `before` pagination cursor that a `forget` has since rewritten past is told apart from a cursor that was never valid at all. Paging past it no longer answers `[]` - indistinguishable from "there is nothing older" - but restarts cleanly from the newest page and says so, so the panel can replace its list and explain why, instead of silently hiding the "load older" button over history that still exists. That distinction has to hold even when the `forget` that invalidates a cursor is still running while it is read, not only long afterward - the second and third drafts of this plan were rejected by external review for exactly that reason, twice, at two different layers.

**Architecture:** `forget` gives every surviving commit a fresh sha and prunes the old ones immediately (`grace_period=0` - see decision 24). A `before` cursor handed back on an earlier page names one of those old shas; once a `forget` has rewritten past it, `_resolve` cannot tell "this sha used to be real" from "this sha was never real" - both answer `None`. `HistoryStore` gains a persisted, monotonic `forget_generation()`. Callers that want to be told apart from a genuinely-unknown cursor pass the generation they saw when the cursor was issued as a new, explicitly opt-in `before_generation` parameter; `_indexed_revisions`/`_walked_changes` raise a new `StaleCursorError` only when that parameter is given *and* older than the current generation. Without it, an unresolvable `before` still answers `[]`, exactly as today - the WebSocket command accepts an arbitrary `before` string from anyone with admin rights, not only the panel's own echoed cursor, and an external caller that never adopted the new parameter must not be told "restarted" for what may simply be a typo.

Two concurrency properties turned out not to be free, and both were found only by external review against a first draft that assumed they were:

1. **The generation counter has to be bumped before anything it is meant to signal becomes true, not after - and idempotently, not by a relative `+1`.** `_finish_forget` writes the target generation (computed once, before any ref moves, replayed identically on a crash-then-repair run) as its very first step, strictly before `_garbage_collect_protecting_index` can make any cursor unresolvable. A reader that later finds a cursor unresolvable is then guaranteed, by plain program order, to also observe the bumped generation - regardless of how the existing `_retrying_a_forget_race` HEAD/checkpoint comparison happens to land, which review demonstrated has its own blind spot for a `forget` that completes entirely inside one read.
2. **`operations.async_history` must not read the page and the generation as two independently scheduled, unordered pieces of work.** The two are bundled into one executor call, then the whole thing (together with `list_versions`) is wrapped in the same async retry helper `async_search` already uses for the analogous problem (decision 24) - narrowing, though not by itself perfectly closing, the window in which a `forget` completing at exactly the wrong moment could pair a still-valid cursor with a generation number that has already moved past it.

`operations.async_history` catches `StaleCursorError`, re-runs itself from the top (`before=None`), and marks the answer `restarted: true`; the panel replaces its list instead of appending to it and shows a short, plain notice.

**Tech Stack:** Python 3, `dulwich` 1.2.14 (pinned). `store.py` is one of the seven Home-Assistant-free modules, tested under plain `pytest`. `operations.py` and `websocket_api.py` import `homeassistant`, tested via `docker exec` against the project's test container (no running instance needed for this plan's change - see Task 2). `panel.js` is vanilla JS with no build step, tested by running its own logic under Node (see Task 3).

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`. Not yet recorded there under its own decision number - Task 4 adds it, as decision 25, following the exact form decisions 21-24 already use. Read decision 24 first (paragraph 24, lines 647-676, ending right before `## Fehler- und Randfälle`): it is the closest relative of this change, explains why `forget` rewrites every surviving commit rather than only the forgotten dashboard's own, and explicitly named this issue (#26) as out of scope for itself.

**Out of scope:** the retry-on-a-*concurrent*-`forget` machinery `list_changes` already has (`_retrying_a_forget_race`, decision 24) is not replaced, only reused (Task 2) and, at the store layer, made unnecessary for this specific race by the write-ordering fix in Task 1 rather than patched. `StaleCursorError` is a distinct exception type, never caught by that retry's `except (KeyError, MissingCommitError)`, so it always propagates straight out.

**Known, accepted residual risk - stated rather than hidden, matching how decision 24 documents its own:** Task 2's bundling and retry narrow the window in which `async_history`'s returned `generation` could pair with a slightly different snapshot than its `changes`, but do not mathematically eliminate it - closing it completely would need a single atomic read across two independent pieces of information, which nothing in this codebase does anywhere else either. A `forget` that completes in the handful of Python statements between the bundled read and the retry wrapper's own trust check, repeated identically on every one of `_FORGET_RACE_RETRIES` attempts, would still slip through. Decision 24 accepts the identical residual for its own retries ("rare enough to raise on rather than design a quiet fallback for"); this plan accepts it on the same grounds, at a narrower window than the one review actually found in the first draft.

## Global Constraints

- No shelling out to `git`. `dulwich` only (`CLAUDE.md`, "Hard rules").
- `store.py` must not `import homeassistant`, directly or indirectly - it stays testable under plain `pytest`.
- Blocking work belongs in an executor (`hass.async_add_executor_job`) - Task 2's new bundled helper runs inside a single executor job for exactly this reason, not two.
- Test commands: `python3 -m pytest tests/ -v` for `store.py` (Task 1) and `panel.js` (Task 3); `docker exec -i dashboard-history-test python3 - < tests/integration/run_stale_pagination_cursor.py` for the one piece that touches `operations.py` (Task 2).
- Commit message format (`CLAUDE.md`, "Git"): English, imperative subject, blank line, body wrapped at 72 characters explaining the *why*, referencing issue #26. This applies to every commit in this plan without exception, including Task 4's, which touches only the German design journal - `CLAUDE.md`'s "Git" section states the format for "every commit," with no carve-out for which files a commit happens to touch.

---

## Files touched

| File | Role |
|---|---|
| `custom_components/dashboard_history/store.py` | New `StaleCursorError`, `_FORGET_GENERATION_NAME`, `HistoryStore._forget_generation_path`, `HistoryStore.forget_generation` (public, defensively parsed); checkpoint schema gains an optional `target_generation`; `_write_checkpoint`, `_read_checkpoint`, `_validate_checkpoint_semantics`, `_forget`, `repair_pending_forget`, `_finish_forget` all touched for that; `list_changes`, `_each_change`, `_indexed_revisions`, `_walked_changes` gain a `before_generation` parameter. |
| `custom_components/dashboard_history/operations.py` | New module-level `_changes_and_generation` helper; `async_history` gains a `before_generation` parameter, wraps its combined read in the existing `_retrying_a_forget_race`, catches `StaleCursorError` and restarts. |
| `custom_components/dashboard_history/websocket_api.py` | The `history` command's schema and argument mapping gain `before_generation`. |
| `custom_components/dashboard_history/panel.js` | Remembers `_cursorGeneration` alongside `_cursor`; `_loadOlder` sends it back and replaces the list instead of appending when the answer says `restarted`; `_renderMain` shows a short notice while that is the case. |
| `tests/test_store.py` | New tests for `forget_generation`, `StaleCursorError`, checkpoint schema compatibility and rejection, and the write-ordering guarantee; one existing test (`test_forget_writes_a_checkpoint_before_the_first_ref_moves`) updated for the checkpoint tuple's new shape. |
| `tests/integration/run_stale_pagination_cursor.py` | New tier-3 script (no running instance) covering `operations.async_history`'s restart and its retry under a race. |
| `tests/test_panel_behaviour.py` | New tests for the panel's cursor-generation tracking, its restart handling, and the rendered notice. |
| `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, `docs/superpowers/status.md` | Decision 25 recorded (Task 4). |

No other production file needs to change. `_each_change`'s new parameter is deliberately *not* passed on every call (see Task 1, Step 8) specifically so the eight existing tests in `tests/test_store.py` that monkeypatch `HistoryStore._each_change` wholesale, with its current four-parameter shape, keep working unmodified - a first draft of this plan added the parameter unconditionally and broke every one of them, caught by review.

---

### Task 1: `store.py` - a persisted, race-safe generation, and a distinguishable stale cursor

**Files:**
- Modify: `custom_components/dashboard_history/store.py`
- Modify: `tests/test_store.py` (one existing test's checkpoint tuple unpack)
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `HistoryStore._write_file` (existing, static), `HistoryStore._checkpoint_path` (existing), `HistoryStore._resolve`, `HistoryStore._revision_index` (existing), `HistoryStore._garbage_collect_protecting_index` (existing).
- Produces:
  - `class StaleCursorError(Exception)` - module level, directly above `class HistoryStore:`.
  - `_FORGET_GENERATION_NAME = "dashboard_history_forget_generation"` - module constant, next to `_FORGET_CHECKPOINT_NAME`.
  - `HistoryStore._forget_generation_path(self) -> Path` - new method, mirrors `_checkpoint_path`.
  - `HistoryStore.forget_generation(self) -> int` - new **public** method (needed outside `store.py` too, by Task 2). Returns `0` if the file does not exist yet, or if it exists but cannot be parsed as an int (logged, not raised).
  - `HistoryStore._write_checkpoint(self, key, head, notes, tags, target_generation: int) -> None` - new trailing **required** parameter (the only caller, `_forget`, is updated in the same step).
  - `HistoryStore._read_checkpoint(self) -> tuple[str, bytes | None, dict, dict, int] | None` - return tuple grows from four to five elements. `target_generation` is read leniently: a checkpoint written before this feature existed (missing the key entirely) gets `self.forget_generation() + 1` computed fresh, exactly what would have been stored had the feature existed at write time - not a parse failure.
  - `HistoryStore._validate_checkpoint_semantics(self, repo, key, head, notes, tags, target_generation: int) -> None` - new trailing required parameter; rejects a `target_generation` that is neither the current generation nor exactly one more than it (both are legitimate - see Step 8 for why), the same way it already rejects an invalid sha or ref name.
  - `HistoryStore._finish_forget(self, repo, key, head, notes, tags, target_generation: int, say) -> None` - new parameter inserted before `say` (matching where `head`/`notes`/`tags` already sit); writes `target_generation` as its **first** action, before `_point_head`.
  - `HistoryStore.list_changes(self, key, limit=50, before=None, before_generation: int | None = None) -> list[Change]` - new trailing parameter, defaulted.
  - `HistoryStore._each_change(self, repo, key, limit=50, before=None, before_generation: int | None = None) -> Iterator[Change]` - same, new trailing parameter. Callers decide whether to pass it at all (see Step 8).
  - `HistoryStore._indexed_revisions(self, repo, key, before, before_generation: int | None = None) -> list[str] | None` - same.
  - `HistoryStore._walked_changes(self, repo, key, notes, limit, before, before_generation: int | None = None) -> Iterator[Change]` - same.

- [ ] **Step 1: Write the failing tests for the generation counter**

Add to `tests/test_store.py`, directly after `test_repair_does_nothing_when_no_checkpoint_exists`:

```python
def test_forget_generation_starts_at_zero(store):
    """No `forget` has ever run in a fresh repository."""
    assert store.forget_generation() == 0


def test_forget_increments_the_generation(store):
    """Every completed `forget` moves the counter, regardless of which
    key it targeted - see issue #26."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    assert store.forget_generation() == 0
    store.forget("gone")
    assert store.forget_generation() == 1
    store.write_snapshot("gone2", "b: 2\n", "gone second")
    store.forget("gone2")
    assert store.forget_generation() == 2


def test_a_corrupt_generation_file_is_treated_as_zero(store):
    """A single small metadata file must not take every history read
    down with it. Never written this way by this class - disk
    corruption or manual tampering are not this class's to rule out -
    but the safe fallback is the same either way: treat it as "no
    forget has completed since this file was last trustworthy", which
    the next completed `forget` overwrites with a fresh, valid value
    regardless. See issue #26 and the review that found this missing."""
    generation_path = store.path / ".git" / "dashboard_history_forget_generation"
    generation_path.parent.mkdir(parents=True, exist_ok=True)
    generation_path.write_text("not a number", encoding="utf-8")

    assert store.forget_generation() == 0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k forget_generation -v`
Expected: FAIL - the first two with `AttributeError: 'HistoryStore' object has no attribute 'forget_generation'`, the corruption test also fails once `forget_generation` exists but before its error handling is added (a `ValueError` propagates instead of being caught).

- [ ] **Step 3: Implement the generation counter, defensively read**

In `custom_components/dashboard_history/store.py`, near `_FORGET_CHECKPOINT_NAME` (around line 50), add:

```python
# The name of the file that holds how many times `forget` has ever
# completed against this repository, inside `.git` next to the
# checkpoint. A plain integer as text, written by `_finish_forget` -
# see its own docstring for why that write happens first, before
# anything else in that method, rather than last. Used to tell a
# `before` cursor that was real and has since been rewritten away
# apart from one that was never valid at all - see issue #26.
_FORGET_GENERATION_NAME = "dashboard_history_forget_generation"
```

Add `StaleCursorError` directly above `class HistoryStore:`:

```python
class StaleCursorError(Exception):
    """A `before` cursor cannot be trusted any more.

    Raised only when the caller supplied `before_generation` and a
    `forget` has moved `HistoryStore.forget_generation()` past it -
    `_resolve` failing is then expected, not a sign the cursor was
    ever invalid. Without `before_generation`, the same unresolvable
    `before` still answers `[]`, exactly as before this existed: the
    WebSocket `history` command accepts an arbitrary `before` string
    from any admin caller, not only the panel's own echoed cursor, and
    a caller that never adopted the new parameter must keep getting
    the old, safe answer. See issue #26.
    """
```

Add the two new methods next to `_checkpoint_path` (around line 582):

```python
    def _forget_generation_path(self) -> Path:
        return self.path / ".git" / _FORGET_GENERATION_NAME

    def forget_generation(self) -> int:
        """How many times `forget` has ever completed here.

        `0` for a repository no `forget` has touched yet - including
        one that ran `forget` before this counter existed at all: no
        cursor from that era ever carried a `before_generation` either
        (an old response never had a `generation` field for a client
        to remember), so starting the count at `0` on first use is
        exactly as safe as if the counter had existed all along. Every
        `before_generation` comparison only asks "has a forget
        happened *since* this number was read", never anything about
        the number's absolute size.

        Also `0` if the file exists but cannot be parsed as an int -
        logged rather than raised. Never written this way by
        `_finish_forget` itself, but trusting a garbage value could
        move the counter backwards, which every comparison against it
        assumes never happens; the next completed `forget` overwrites
        it with a fresh, valid value regardless. See issue #26.
        """
        path = self._forget_generation_path()
        if not path.exists():
            return 0
        try:
            return int(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            _LOGGER.exception(
                "Could not read the forget generation counter at %s: %s. "
                "Treating it as 0 until the next completed forget "
                "rewrites it.",
                path,
                exc,
            )
            return 0
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k forget_generation -v`
Expected: PASS (3 tests). `forget_generation` does not increment yet - Step 3 only adds the read side.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Add a defensively-read forget generation counter

A before pagination cursor cannot tell "this commit was never real"
apart from "this commit was real and forget has since rewritten past
it" once it stops resolving - both answer the same way. A persisted,
monotonic generation is the signal a later commit uses to tell them
apart; read defensively from the start, since a single corrupted
metadata file must not take every history read down with it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 6: Write the failing tests for the checkpoint schema and the write-ordering guarantee**

Add to `tests/test_store.py`, directly after the tests from Steps 1 and add `StaleCursorError` to the existing `from store import HistoryStore, RevisionIndex, Version, _as_text` import line:

```python
def test_repair_pending_forget_bumps_the_generation_exactly_once(store, monkeypatch):
    """The crash-recovery path (decision 21) finishes a `forget` through
    the same `_finish_forget` the ordinary path does - and since that
    method now writes the generation as its very *first* step, the
    counter is already at its new value the instant the crash happens,
    before `_point_head` even runs. A naive `+1` on every call would
    double-count this exact scenario: `repair_pending_forget` replays
    `_finish_forget` whole, and a second `+1` for a `forget` that had
    already, if incompletely, run once would be wrong. Reuses the
    crash simulation `test_repair_finishes_an_interrupted_forget`
    already established as realistic. See issue #26 and the review
    that found the original, unconditional `+1` was not idempotent."""
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    home_v2 = store.write_snapshot("home", "a: 2\n", "second")
    store.set_description(home_v2, "a note on the commit that gets rewritten")
    store.create_version("home/v1.0.0", "Home", "", home_v2)

    real_rewrite_tags = HistoryStore._rewrite_tags
    calls = []

    def flaky_rewrite_tags(repo, changed):
        calls.append(changed)
        if len(calls) == 1:
            raise RuntimeError("simulated crash before _rewrite_tags")
        return real_rewrite_tags(repo, changed)

    monkeypatch.setattr(HistoryStore, "_rewrite_tags", staticmethod(flaky_rewrite_tags))

    with pytest.raises(RuntimeError):
        store.forget("gone")

    # Already bumped: the write happens before _point_head, long before
    # the crash point inside _rewrite_tags.
    assert store.forget_generation() == 1

    monkeypatch.setattr(HistoryStore, "_rewrite_tags", staticmethod(real_rewrite_tags))
    store.repair_pending_forget()

    # Not 2: the checkpoint's target_generation is the same value
    # replayed, not a fresh +1.
    assert store.forget_generation() == 1

    # A second repair call must be a pure no-op - the checkpoint is
    # already gone - not a second bump either.
    store.repair_pending_forget()
    assert store.forget_generation() == 1


def test_the_generation_bump_happens_before_any_object_is_pruned(store, monkeypatch):
    """The exact property an external review demonstrated was missing:
    a reader that finds a cursor unresolvable must be able to trust
    that the generation counter already reflects it. Proven directly,
    at the exact point pruning begins, rather than by racing real
    threads - the same kind of exact-point interruption
    `test_forget_writes_a_checkpoint_before_the_first_ref_moves` uses
    for a different guarantee. If this ever regresses - the bump
    moved back to the end of `_finish_forget`, say - `observed` comes
    back `[0]` instead of `[1]`, because pruning would then run before
    the counter reflected this `forget` at all."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    real_gc = HistoryStore._garbage_collect_protecting_index
    observed = []

    def observing_gc(repo):
        observed.append(store.forget_generation())
        return real_gc(repo)

    monkeypatch.setattr(
        HistoryStore, "_garbage_collect_protecting_index", staticmethod(observing_gc)
    )

    store.forget("gone")

    assert observed == [1]


def test_a_checkpoint_with_the_wrong_target_generation_is_rejected(store):
    """A genuine, untampered checkpoint's `target_generation` can only
    ever be the current generation or one more than it - nothing else
    can move the counter while a checkpoint is pending
    (`_refuse_if_forget_pending`), so no third value is reachable
    honestly. `99` against a store where nothing has ever been
    forgotten (current generation `0`) is neither `0` nor `1`, and
    must be rejected the same way an invalid sha or ref name already
    is (decision 21, correction 7). Every other field below is
    deliberately valid, so the only thing that can make this
    checkpoint fail is `target_generation` itself."""
    store.write_snapshot("home", "a: 1\n", "first")
    home_v2 = store.write_snapshot("home", "a: 2\n", "second")

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        json.dumps(
            {
                "key": "home",
                "head": home_v2,
                "notes": {},
                "tags": {},
                "target_generation": 99,
            }
        ),
        encoding="utf-8",
    )

    store.repair_pending_forget()

    assert not checkpoint.exists()
    assert store.forget_generation() == 0
    assert store.read_at("home", "HEAD") == "a: 2\n"


def test_a_legacy_checkpoint_without_target_generation_still_repairs(store):
    """A checkpoint written before this feature existed has no
    `target_generation` key at all - not a parse failure, since
    nothing else could have moved the counter while it sat pending
    either, so computing it fresh at repair time (`current + 1`) is
    exactly what would have been stored had the feature existed at
    write time. See issue #26."""
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    home_v2 = store.write_snapshot("home", "a: 2\n", "second")

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        json.dumps({"key": "gone", "head": home_v2, "notes": {}, "tags": {}}),
        encoding="utf-8",
    )

    store.repair_pending_forget()

    assert not checkpoint.exists()
    assert store.forget_generation() == 1
```

- [ ] **Step 7: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "generation or checkpoint_with_the_wrong or legacy_checkpoint" -v`
Expected: FAIL - `TypeError` (missing arguments) once `_finish_forget`'s signature changes are half-applied, or assertion failures against the still-unconditional `+1` and still-end-of-function bump, depending on how far Step 8 has landed when this is run. Run it again after Step 8 to confirm the real PASS.

- [ ] **Step 8: Implement the checkpoint schema change, the ordering fix, and `StaleCursorError`**

In `custom_components/dashboard_history/store.py`, change `_write_checkpoint`:

```python
    def _write_checkpoint(
        self,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
        target_generation: int,
    ) -> None:
        """Save what `forget` is about to finish, before any ref moves.

        Five fields, not four: `target_generation` joins `key` for the
        same reason - `_finish_forget` needs a value nothing else
        recomputes later, so a crash-then-repair replay writes the
        exact same generation again instead of counting one completed
        `forget` twice. Written through `_write_file`'s temp-then-
        `os.replace` so an interrupted write of the checkpoint itself
        is never mistaken for a valid one - see decision 21. See also
        issue #26 for why `target_generation` exists at all.
        """
        payload = {
            "key": key,
            "head": head.decode() if head is not None else None,
            "notes": {sha.decode(): text.decode("utf-8") for sha, text in notes.items()},
            "tags": {
                ref.decode("utf-8", "surrogateescape"): (
                    sha.decode() if sha is not None else None
                )
                for ref, sha in tags.items()
            },
            "target_generation": target_generation,
        }
        self._write_file(self._checkpoint_path(), json.dumps(payload))
```

Change `_read_checkpoint`'s return type and add lenient parsing for the new field, right after the existing `tags` block and before the `return`:

```python
    def _read_checkpoint(
        self,
    ) -> (
        tuple[str, bytes | None, dict[bytes, bytes], dict[bytes, bytes | None], int]
        | None
    ):
```

(update the signature line only - the body stays as it is up through building `tags`, then:)

```python
            target_generation_val = payload.get("target_generation")
            if target_generation_val is None:
                # A checkpoint written before this field existed. Safe
                # to compute fresh: nothing else can have moved the
                # counter while this checkpoint sat pending (`forget`
                # itself refuses while one exists), so this is exactly
                # what would have been stored had the feature existed
                # at write time. Not a parse failure - see issue #26.
                target_generation = self.forget_generation() + 1
            elif (
                not isinstance(target_generation_val, int)
                or isinstance(target_generation_val, bool)
            ):
                raise ValueError("target_generation must be an int")
            else:
                target_generation = target_generation_val
            return key, head, notes, tags, target_generation
```

(the existing `except (json.JSONDecodeError, KeyError, TypeError, ValueError, AttributeError) as exc:` block below is unchanged and now also catches a bad `target_generation`.)

Change `_validate_checkpoint_semantics`'s signature and add the new check, right after the existing `head`/`notes`/`tags` checks and before whatever the method currently returns with:

```python
    def _validate_checkpoint_semantics(
        self,
        repo: Repo,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
        target_generation: int,
    ) -> None:
```

(docstring gains one paragraph:)

```python
        `target_generation` must be either the current generation or
        exactly one more than it - never anything else. Both are
        legitimate: `_finish_forget` writes `target_generation` as its
        very first step, before any ref moves, so a crash *after* that
        write (the common case - everything else in `_finish_forget`
        runs later) leaves the counter already equal to the target,
        and a crash *before* it (only possible between `_write_
        checkpoint` in `_forget` and the first line of `_finish_
        forget` itself) leaves the counter one behind it. Nothing else
        can move the counter while a checkpoint is pending - a second
        `forget` refuses outright (`_refuse_if_forget_pending`) - so
        no third value is reachable honestly. Anything else - lower,
        or more than one higher - proves the checkpoint or the counter
        file was corrupted or tampered with, and applying it would
        move the counter backwards or skip a value, breaking the one
        property every `before_generation` comparison relies on: it
        only ever goes up by exactly one per completed `forget`. See
        issue #26 and the review that found the original "always
        exactly current + 1" version of this check would reject the
        ordinary crash-after-the-bump case outright.
```

(add at the end of the method body, after the existing sha/ref checks:)

```python
        current_generation = self.forget_generation()
        if target_generation not in (current_generation, current_generation + 1):
            raise ValueError(
                f"target_generation {target_generation!r} is neither the "
                f"current generation ({current_generation!r}) nor one "
                "more than it"
            )
```

Change `_forget`, right where it currently reads:

```python
        self._write_checkpoint(key, head, note_targets, tag_targets)
        self._finish_forget(repo, key, head, note_targets, tag_targets, say)
        return removed
```

to:

```python
        target_generation = self.forget_generation() + 1
        self._write_checkpoint(key, head, note_targets, tag_targets, target_generation)
        self._finish_forget(
            repo, key, head, note_targets, tag_targets, target_generation, say
        )
        return removed
```

Change `repair_pending_forget`, right where it currently reads:

```python
            checkpoint = self._read_checkpoint()
            if checkpoint is None:
                return
            key, head, notes, tags = checkpoint
            try:
                self._validate_checkpoint_semantics(repo, key, head, notes, tags)
            except ValueError as exc:
```

to:

```python
            checkpoint = self._read_checkpoint()
            if checkpoint is None:
                return
            key, head, notes, tags, target_generation = checkpoint
            try:
                self._validate_checkpoint_semantics(
                    repo, key, head, notes, tags, target_generation
                )
            except ValueError as exc:
```

and, a few lines below, where it currently reads:

```python
            self._index = None
            self._survey = None
            self._finish_forget(repo, key, head, notes, tags, _Progress(None))
```

to:

```python
            self._index = None
            self._survey = None
            self._finish_forget(
                repo, key, head, notes, tags, target_generation, _Progress(None)
            )
```

Change `_finish_forget` - new parameter, and the generation write moves from the end to the very first line of the body:

```python
    def _finish_forget(
        self,
        repo: Repo,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
        target_generation: int,
        say: _Progress,
    ) -> None:
        """Move every ref to its planned target, then clean up.

        Shared by the call that just computed `head`/`notes`/`tags` and
        by `repair_pending_forget`, which reads the same five values
        back from the checkpoint after an interruption - see decision
        21. Every step here is safe to redo: `_point_head` sets a ref
        outright, `_rewrite_notes` rebuilds `refs/notes/commits` whole
        from `notes` every time, `_rewrite_tags` merges `tags` into
        whatever tags exist now, and `_drop_from_index` and
        `garbage_collect` already tolerated being run more than once
        before this existed. The checkpoint is deleted last, deliberately
        - if anything below raises, it stays in place and the next
        attempt starts this method over rather than guessing which
        parts already happened. Callers cannot collide while doing so:
        both the original call and any repair run under the one lock
        `HistoryStore` now shares per repository path (decision 21,
        correction 4).

        `target_generation` is written first of all, before anything
        else - not recomputed here, but the exact value `_forget`/
        `repair_pending_forget` already settled on before this call, so
        a replay after a crash writes the same absolute value again
        rather than a relative `+1` that would double-count a rerun.
        Writing it here, first, rather than at the end where the
        checkpoint deletion already is, closes a gap an external
        review demonstrated: `_garbage_collect_protecting_index` below
        is what actually makes an old `before` cursor unresolvable, and
        a reader that finds one unresolvable must be able to trust
        that the counter already reflects it - which only holds if the
        write happens strictly before the prune, never after. Written
        this early, that ordering holds regardless of anything the
        surrounding `_retrying_a_forget_race` HEAD/checkpoint
        comparison does or does not catch on its own. See issue #26.
        """
        self._write_file(self._forget_generation_path(), str(target_generation))
        self._point_head(repo, head)
        self._rewrite_notes(repo, notes)
        self._rewrite_tags(repo, tags)
        self._drop_from_index(repo, key)

        # Rewriting refs only makes the old objects unreachable; the blobs
        # and commits stay on disk, and `resolve` still finds them. Without
        # this, "forgotten for good" would be a claim the repository
        # contradicts. The grace period is zero on purpose - the usual
        # fourteen days protect objects another writer may be building, and
        # the only other writer here is this class, holding the lock this
        # method runs under. That leaves one gap a grace period cannot
        # close: a *past* writer, no longer holding anything, whose
        # `write_snapshot` staged a blob and then failed before
        # `porcelain.commit` - the index still names it, no ref ever did.
        # `_garbage_collect_protecting_index` closes that one. See issue
        # #25.

        # No counting here: the collection walks the object store on its
        # own and reports nothing back. A phase name without numbers is
        # still worth saying - it is a fifth of the wait.
        say("cleaning", 0, 0)
        self._garbage_collect_protecting_index(repo)

        # The rewrite above moves refs without passing dulwich a message,
        # so none of it adds a reflog line - but every ordinary commit
        # before it did, and those lines outlive the objects they name:
        # the collection just above only prunes what refs and notes point
        # to. Nothing in this project reads `.git/logs` (it exists for
        # git's own tooling, which this integration never shells out to),
        # so there is nothing to preserve - and dulwich recreates whatever
        # reflog file it next needs to write to. See issue #21.
        #
        # Only a missing directory is tolerated here - the ordinary case,
        # since a freshly created repository has no reflog yet. Anything
        # else (no permission, a read-only filesystem) is a real failure
        # and stays visible instead of vanishing behind `ignore_errors`.
        # Decision 21 made this safe to leave as a logged-and-swallowed
        # failure rather than something that must also be resumable: the
        # checkpoint is still deleted below either way, since nothing in
        # this project reads the reflog and there is therefore nothing
        # left to repair.
        try:
            shutil.rmtree(self.path / ".git" / "logs")
        except FileNotFoundError:
            pass
        except OSError:
            _LOGGER.exception("Could not clear the reflog after forgetting %s", key)
        self._checkpoint_path().unlink(missing_ok=True)
```

Now update `tests/test_store.py`'s `test_forget_writes_a_checkpoint_before_the_first_ref_moves` (the one existing test that destructures `_read_checkpoint()`'s return value) for the new five-element tuple - change:

```python
    key, head, notes, tags = store._read_checkpoint()
    assert key == "gone"
    assert head is not None
    assert "gone" not in store.list_all_dashboards()
```

to:

```python
    key, head, notes, tags, target_generation = store._read_checkpoint()
    assert key == "gone"
    assert head is not None
    assert target_generation == 1
    assert "gone" not in store.list_all_dashboards()
```

- [ ] **Step 9: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: PASS - the *whole* file, not only the new tests. This is the step that would have caught the checkpoint-schema regression a first draft of this plan introduced: over a dozen existing tests hand-write a checkpoint JSON payload directly (`checkpoint.write_text(json.dumps({...}))`) to test one specific validation failure each, none of them including `target_generation` - if that field were required rather than falling back to a computed value, every one of those tests would fail for the wrong reason (`KeyError`/`ValueError` on the missing field, masking whatever they actually test). Confirm none of them regressed before moving on.

- [ ] **Step 10: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Write the forget generation before pruning, not after

An external review demonstrated that bumping the counter at the end
of _finish_forget left a window in which a cursor could already be
unresolvable while the counter still read the old value - a reader
landing in that window would answer [] instead of raising a stale-
cursor error, exactly the bug this counter exists to prevent. Moved
to the very first step, and persisted in the checkpoint so a crash-
then-repair replay writes the identical value instead of double-
counting. See issue #26.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 11: Write the failing tests for `StaleCursorError` itself**

Add to `tests/test_store.py`, directly after the tests from Step 6:

```python
def test_stale_before_generation_raises(store):
    """A `before` cursor issued before a `forget` rewrote past it, used
    afterward with the generation it was issued at, must not be
    mistaken for a cursor that was never valid. "gone" is written
    before "home", not after - forgetting a dashboard only gives a
    later commit a new sha if something about its own tree or its
    ancestry changed (same reasoning as decision 24's own tests). See
    issue #26."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "home change 1")
    older_revision = store.write_snapshot("home", "a: 2\n", "home change 2")
    store.write_snapshot("home", "a: 3\n", "home change 3")
    generation_at_read_time = store.forget_generation()
    store.forget("gone")

    with pytest.raises(StaleCursorError):
        store.list_changes(
            "home", before=older_revision, before_generation=generation_at_read_time
        )


def test_stale_before_generation_raises_via_the_walked_fallback(store, monkeypatch):
    """The same guard, in `_walked_changes` - reached whenever
    `_revision_index` cannot answer (an empty repository, or here,
    forced) rather than through the built index. Same technique
    `test_survey_answers_empty_if_head_is_pruned_mid_read` and
    `test_previous_change_answers_none_if_pruned_mid_walk` already use
    to force a method past the index onto its walk branch, applied
    here to `_indexed_revisions`/`_walked_changes` instead."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "home change 1")
    older_revision = store.write_snapshot("home", "a: 2\n", "home change 2")
    generation_at_read_time = store.forget_generation()
    store.forget("gone")
    monkeypatch.setattr(HistoryStore, "_revision_index", lambda self, repo: None)

    with pytest.raises(StaleCursorError):
        store.list_changes(
            "home", before=older_revision, before_generation=generation_at_read_time
        )


def test_an_unresolvable_cursor_without_a_generation_still_yields_nothing(store):
    """An external caller that never adopted `before_generation` - the
    WebSocket API accepts an arbitrary `before` string from anyone
    with admin rights, not only the panel's own echoed cursor - keeps
    getting the old, safe answer even after a `forget` has run. See
    issue #26."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    store.forget("gone")

    assert store.list_changes("home", before="f" * 40) == []


def test_an_unresolvable_cursor_at_the_current_generation_still_yields_nothing(store):
    """A generation that is not older than the current one proves
    nothing went stale - the cursor was simply never a real revision."""
    store.write_snapshot("home", "a: 1\n", "first")
    current_generation = store.forget_generation()

    assert (
        store.list_changes(
            "home", before="f" * 40, before_generation=current_generation
        )
        == []
    )
```

- [ ] **Step 12: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "stale_before_generation or unresolvable_cursor" -v`
Expected: FAIL - `_indexed_revisions`/`_walked_changes` still answer `[]` unconditionally, so the two `pytest.raises(StaleCursorError)` tests fail with `Failed: DID NOT RAISE`.

- [ ] **Step 13: Implement `StaleCursorError`, threaded through the four methods - without changing `_each_change`'s call shape for anyone who has monkeypatched it**

In `custom_components/dashboard_history/store.py`, change `list_changes`:

```python
    def list_changes(
        self,
        key: str,
        limit: int | None = 50,
        before: str | None = None,
        before_generation: int | None = None,
    ) -> list[Change]:
        """Every recorded state of one dashboard, newest first.

        `limit=None` walks the whole history. `before` starts the walk one
        step past that revision - the entry it names is not repeated, so a
        caller can page without stitching duplicates together. A cursor
        rather than an offset because an offset drifts: save while somebody
        is paging and every later page shifts by one.

        A `before` that is no change of this dashboard - another
        dashboard's commit, HEAD - starts the walk at the newest change
        older than it. An unknown `before` yields nothing: asking about a
        revision that is gone is not an error, and `matching_revisions`
        takes the same line - *unless* `before_generation` is given and
        older than `forget_generation()` right now, in which case this
        raises `StaleCursorError` instead: the cursor was real once, and a
        `forget` has since rewritten past it. Leave `before_generation`
        out (the default) to keep the old, unconditional `[]` - the
        WebSocket API accepts an arbitrary `before` from any admin
        caller, not only a cursor this method itself handed out, and an
        omitted generation means "I cannot tell, answer as before." See
        issue #26.

        A list, and the signature says so: every caller here wants one,
        and a page of fifty is a list whatever it is built from. The
        walk underneath is `_each_change`, which hands them over one at
        a time; the slice is what turns the extra look-ahead entry back
        into the page that was asked for.

        Rebuilt whole, up to `_FORGET_RACE_RETRIES` times, if a
        concurrent `forget` pruned a commit this walk already held a
        revision for - see `_retrying_a_forget_race` and decision 24.
        `StaleCursorError` is a different exception entirely and is
        never caught by that retry - it means a `forget` already
        finished, not one racing this read.
        """
        repo = self._repo()
        if repo is None:
            return []

        def build() -> list[Change]:
            # `before_generation` is passed on only when it is actually
            # set, not unconditionally as a fifth positional argument -
            # several existing tests replace `_each_change` wholesale
            # with a four-parameter stand-in to simulate a race
            # (decision 24), and every one of them calls this with
            # `before_generation=None`. Passing a value they were never
            # written to accept would break all of them for a feature
            # they do not exercise. See issue #26 and the review that
            # caught this.
            if before_generation is None:
                found = self._each_change(repo, key, limit, before)
            else:
                found = self._each_change(repo, key, limit, before, before_generation)
            # Sliced after the walk, so the extra entry did its one job -
            # being the predecessor of the last one - and then goes.
            return list(found) if limit is None else list(islice(found, limit))

        return self._retrying_a_forget_race(repo, build)
```

Change `_each_change`:

```python
    def _each_change(
        self,
        repo: Repo,
        key: str,
        limit: int | None = 50,
        before: str | None = None,
        before_generation: int | None = None,
    ) -> Iterator[Change]:
        """The same walk as `list_changes`, one `Change` at a time.

        Every entry the walk produces, including the look-ahead one -
        the caller decides how many it wants. `list_changes` slices;
        `search_changes` stops as soon as it has enough matches, and
        that is the whole reason this is a generator.

        The saving is real because dulwich's walker is lazy too, so
        nothing behind the point a caller stops at is ever read.
        Measured on 2026-09-05 against a repository of 1002 commits over
        five dashboards, 201 of them this dashboard's: walked to the end
        it cost 468 ms as a generator and 481 ms as the list it used to
        build, the same within the noise - the laziness is free even
        when it saves nothing. A search that stops at its first ten
        matches cost 24.5 ms against 470 ms, and one that stops at the
        first, 5.0 ms.

        One entry is held back at a time, and that is what `previous`
        costs: an entry cannot be handed out until the next one is
        known, because the next one *is* its predecessor. The last entry
        of the walk has nobody behind it and answers None, which is what
        "the oldest recorded state" means.

        Takes `repo` from its caller rather than opening its own: both
        callers now need it themselves too, for `_retrying_a_forget_race`
        (decision 24) - a second `Repo(...)` here would only cost an
        extra file handle for nothing.
        """
        notes = self.descriptions()
        revisions = self._indexed_revisions(repo, key, before, before_generation)
        if revisions is not None:
            for position, revision in enumerate(revisions):
                following = (
                    revisions[position + 1]
                    if position + 1 < len(revisions)
                    else None
                )
                yield _change(repo[revision.encode()], notes, following)
            return
        yield from self._walked_changes(
            repo, key, notes, limit, before, before_generation
        )
```

Change `_indexed_revisions`:

```python
    def _indexed_revisions(
        self,
        repo: Repo,
        key: str,
        before: str | None,
        before_generation: int | None = None,
    ) -> list[str] | None:
        """One dashboard's revisions from the index, newest first.

        Three answers, and the difference between two of them matters:
        a list is what to hand out, the empty list is "nothing to hand
        out", and None is "the index cannot answer this" - only then
        does the caller walk.

        Raises `StaleCursorError` instead of the usual `[]` when
        `before` does not resolve, `before_generation` was given, and
        it is older than `forget_generation()` right now - see
        `list_changes`'s docstring and issue #26.
        """
        index = self._revision_index(repo)
        if index is None:
            return None
        revisions = index.by_key.get(key, [])
        if before is None:
            return revisions
        resolved = self._resolve(repo, before)
        if resolved is None:
            if (
                before_generation is not None
                and before_generation < self.forget_generation()
            ):
                raise StaleCursorError(before)
            # An unknown `before` yields nothing, as the docstring of
            # `list_changes` promises - not a walk that finds plenty.
            return []
        at = index.order.get(resolved)
        if at is None:
            # Resolves, but is not in this walk: outside the index's
            # reach, so let the walk answer it.
            return None
        return [r for r in revisions if index.order[r] > at]
```

Change `_walked_changes`:

```python
    def _walked_changes(
        self,
        repo: Repo,
        key: str,
        notes: dict,
        limit: int | None,
        before: str | None,
        before_generation: int | None = None,
    ) -> Iterator[Change]:
        """`_each_change` the long way, by walking the history itself.

        What this class did everywhere until the index arrived, kept for
        the one question the index cannot answer: a `before` naming a
        commit that is not in the walk at all. A cursor from a history
        that has since been rewritten is such a commit - it still
        resolves, and the walk from it still has ancestors to hand back.

        Raises `StaleCursorError` under the same condition
        `_indexed_revisions` does, for the same reason - see its
        docstring and issue #26.
        """
        # Both paths: a rename touches only the metadata, and a change
        # that is recorded but never shown is the worst of both.
        paths = [f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()]
        walk: dict = {"paths": paths}
        cursor: bytes | None = None
        if before is not None:
            resolved = self._resolve(repo, before)
            if resolved is None:
                if (
                    before_generation is not None
                    and before_generation < self.forget_generation()
                ):
                    raise StaleCursorError(before)
                return
            # `include` walks *from* that commit and hands the commit
            # itself back first - but only if it touches these paths. A
            # cursor from another dashboard is not in the list at all,
            # so the first entry is dropped only when it *is* the cursor.
            # Same guard as `previous_change`.
            cursor = resolved.encode()
            walk["include"] = [cursor]
        if limit is not None:
            # One more than asked for, so the last entry handed out
            # knows its predecessor. With a cursor, two more: the cursor
            # entry is dropped again below, and when the cursor names a
            # commit of some other dashboard there is nothing to drop -
            # one entry more than needed is read, never one too few.
            walk["max_entries"] = limit + 2 if cursor is not None else limit + 1
        try:
            walker = repo.get_walker(**walk)
        except KeyError:
            # No HEAD yet: an empty repository has no history to walk.
            # Measured: dulwich resolves `include` while the walker is
            # built, so this arrives here and not halfway through.
            return
        held = None
        first = True
        for entry in walker:
            if first:
                first = False
                if cursor is not None and entry.commit.id == cursor:
                    continue
            if held is not None:
                # The next entry of this same walk. The walk is already
                # filtered on this dashboard's paths, so it is this
                # dashboard's own predecessor and never the commit's
                # parent, which may belong to somebody else entirely.
                yield _change(held.commit, notes, _as_text(entry.commit.id))
            held = entry
        if held is not None:
            yield _change(held.commit, notes, None)
```

- [ ] **Step 14: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: PASS - the full file. This confirms, among everything else, that all eight pre-existing tests monkeypatching `_each_change` (`test_list_changes_retries_a_read_that_raced_forget` and its neighbors) are completely unaffected, because `list_changes`'s `build()` never passes them a fifth argument.

- [ ] **Step 15: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Raise a distinguishable error for a forgotten-past cursor

Without a generation to compare against, an unresolvable before
cursor and one that was simply never valid looked identical - both
answered []. A caller now opts in with before_generation to be told
apart; without it, the old, safe answer is unchanged, since the
WebSocket command accepts an arbitrary before string from any admin
caller. See issue #26.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `operations.py`/`websocket_api.py` - restarting instead of truncating, without splitting one snapshot across two unordered reads

**Files:**
- Modify: `custom_components/dashboard_history/operations.py`
- Modify: `custom_components/dashboard_history/websocket_api.py`
- Test: `tests/integration/run_stale_pagination_cursor.py` (new)

**Interfaces:**
- Consumes: `HistoryStore.list_changes(..., before_generation=...)`, `HistoryStore.forget_generation()` (both from Task 1), `StaleCursorError` (from Task 1, imported into `operations.py`), the existing `operations._retrying_a_forget_race` (decision 24).
- Produces:
  - `operations._changes_and_generation(store, key, limit, before, before_generation) -> tuple[list, int]` - new module-level helper, run inside one executor job.
  - `operations.async_history(hass, store, key, limit=50, before=None, before_generation=None) -> dict` - new trailing parameter; every returned dict now also carries `"generation": int` and `"restarted": bool`.
  - The `dashboard_history/history` WebSocket command accepts an optional `before_generation` alongside `before`.

- [ ] **Step 1: Write the failing integration script**

Create `tests/integration/run_stale_pagination_cursor.py`:

```python
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
```

Count the `check(...)` calls above before relying on any specific "N of N" expectation later in this task: as written, there are 5 in the first scenario, 2 in the second, and 2 in the third - 9 total. If a later edit changes that count, update Step 5's expectation to match rather than trust this number blindly.

- [ ] **Step 2: Run the script to verify it fails**

Run: `docker exec -i dashboard-history-test python3 - < tests/integration/run_stale_pagination_cursor.py`
Expected: the first scenario fails with a `TypeError` (`async_history` does not accept `before_generation` yet) or, once Task 1 alone is in place, with the response not carrying `"restarted"`/`"generation"` at all.

- [ ] **Step 3: Implement the bundled read and the restart in `async_history`**

In `custom_components/dashboard_history/operations.py`, change the import line:

```python
from .store import HistoryStore, StaleCursorError, Version, _FORGET_RACE_RETRIES
```

Add a new module-level helper, near `_marks_by_revision`/`_rendered` (around line 200, before `async_history`):

```python
def _changes_and_generation(
    store: HistoryStore,
    key: str,
    limit: int,
    before: str | None,
    before_generation: int | None,
) -> tuple[list, int]:
    """`list_changes` and `forget_generation`, read from one executor hop.

    Deliberately not two independent jobs under the same
    `asyncio.gather` `list_versions` already runs alongside this one:
    two independent jobs can land on two different threads with no
    ordering between them at all, and a `forget` completing entirely
    in that gap could pair a still-valid cursor with a generation
    number from a `forget` that had not touched it yet - only for that
    same `forget` to be the one that later prunes it, leaving a
    cursor whose remembered generation is already too high to ever
    catch it as stale. Reading both here, sequentially, in one thread,
    does not eliminate that window on its own - nothing this side of
    `_retrying_a_forget_race` below does - but narrows it from
    "however long the executor takes to schedule a second job" to two
    adjacent Python statements, and that retry still catches a
    `forget` spanning even this narrower gap, the same way it already
    catches one spanning `async_search`'s own two calls. See issue
    #26 and the review that found the wider version of this gap.
    """
    changes = store.list_changes(key, limit, before, before_generation)
    return changes, store.forget_generation()
```

Change `async_history`'s signature and body:

```python
async def async_history(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    limit: int = 50,
    before: str | None = None,
    before_generation: int | None = None,
) -> dict:
    """The recorded states of one dashboard, newest first.

    Each entry says whether it holds exactly what the dashboard holds now
    (`same_as_now`). That is worked out rather than assumed, and the
    difference matters: normally the newest entry *is* the current state,
    but after a change made at Home Assistant's back - a restored backup, a
    hand-edited storage file - it is not, and will not be until the next
    start. A panel that simply crowned the top entry would be wrong exactly
    when being right matters.

    It also answers the question a repetitive history raises. Moving a card
    up and down leaves several entries with byte-identical content and, since
    the messages are generated, identical wording: seven reading "2 moved",
    every second one the state in front of you.

    Each entry also names the versions that sit on it, if any. The panel
    builds its sections from that, so it never has to join two calls
    together - a join in the panel is logic in the panel.

    It also says what day it is here, spelled the way an automatic
    version spells it. The dialog in front of a restore offers to keep
    the state being replaced and fills the title in with today's date;
    computed in the browser that is the *browser's* today, and near
    midnight from a laptop in another time zone it is a different day
    from the one this installation would have written. Two names for one
    day in a list that shows nothing but names is precisely the
    confusion the simple mode cannot survive.

    Carried here rather than anywhere else because the panel already has
    this answer in its hand at the moment it needs the string: the
    restore dialog is opened from a history row. `next_versions` is the
    other candidate and would be fresher still, but the keep block of
    the restore dialog does not call it - it needs no numbering, only a
    title. And `history` is re-read whenever the dashboard changes or is
    switched, so the string cannot age past a panel nobody is touching.

    Every answer also carries `generation` - read together with `changes`
    in `_changes_and_generation`, not as an independent job, and the
    whole combined read retried as one sequence (`_retrying_a_forget_
    race`, decision 24) alongside `list_versions` - so a caller paging
    further can hand `generation` back as `before_generation` on its
    next request. If `before` names a commit a `forget` has since
    rewritten past, and `before_generation` proves it (older than the
    generation right now), this restarts from the newest page instead
    of raising - `restarted` says so, so the caller can replace what it
    is showing rather than append to it. See issue #26.
    """

    async def attempt() -> tuple[list, dict]:
        (changes, generation), versions = await asyncio.gather(
            hass.async_add_executor_job(
                _changes_and_generation,
                store,
                key,
                limit + 1,
                before,
                before_generation,
            ),
            hass.async_add_executor_job(store.list_versions, key),
        )
        return changes, {"versions": versions, "generation": generation}

    try:
        # One more than asked for: its presence answers "is there anything
        # older?", and it costs one commit rather than a second query.
        changes, extra = await _retrying_a_forget_race(hass, store, attempt)
    except StaleCursorError:
        restarted = await async_history(hass, store, key, limit)
        restarted["restarted"] = True
        return restarted
    versions = extra["versions"]
    generation = extra["generation"]
    more = len(changes) > limit
    changes = changes[:limit]
    marks = _marks_by_revision(versions)
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None:
        # Changes *and* versions in one pass: the comparison is by blob
        # id, and a second call would open the same repository again.
        # The versions join in because the badge would otherwise depend
        # on how far somebody has paged - the finding this project is for.
        wanted = [c.revision for c in changes] + [v.revision for v in versions]
        if wanted:
            same = await hass.async_add_executor_job(
                _same_as_live, store, key, wanted, live
            )
    rendered = _rendered(changes, marks, same)
    matching_versions = [
        _version_dict(v)
        for v in versioning.by_number(key, versions)
        if v.revision in same
    ]
    return {
        "changes": rendered,
        # The cursor for the next page: the oldest change handed out.
        # None means there is nothing older - the panel then leaves the
        # button out rather than fetching an empty page.
        "next_cursor": rendered[-1]["revision"] if more and rendered else None,
        "generation": generation,
        # Only ever true on the branch above, which returns early - a
        # plain field rather than an absent key, so a caller can check
        # it without a second `"restarted" in result`.
        "restarted": False,
        "matching_versions": matching_versions,
        # The installation's own today, not the browser's. Read at the
        # moment of answering and through the same function the
        # automatic versions use, so a title somebody accepts unchanged
        # is spelled exactly like the ones already in the list.
        "today": versioning.day_title(
            int(dt_util.utcnow().timestamp()), dt_util.DEFAULT_TIME_ZONE
        ),
    }
```

- [ ] **Step 4: Wire `before_generation` through the WebSocket command**

In `custom_components/dashboard_history/websocket_api.py`, change the `history` command's schema and argument mapping:

```python
    _command(
        f"{DOMAIN}/history",
        {
            **_DASHBOARD,
            # At least one: with zero there is no oldest entry to point
            # from, and the answer would claim there is nothing older.
            vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1)),
            vol.Optional("before"): vol.Any(None, str),
            # See issue #26: without this, a cursor a forget has since
            # rewritten past cannot be told apart from one that was
            # never valid, and paging would silently look finished.
            vol.Optional("before_generation"): vol.Any(None, int),
        },
        operations.async_history,
        lambda msg: {
            "key": msg["dashboard"],
            "limit": msg["limit"],
            "before": msg.get("before"),
            "before_generation": msg.get("before_generation"),
        },
    ),
```

- [ ] **Step 5: Run the script to verify it passes**

Run: `docker exec -i dashboard-history-test python3 - < tests/integration/run_stale_pagination_cursor.py`
Expected: `9 of 9 checks passed` (or whatever the actual count from Step 1 turned out to be - see the note there).

- [ ] **Step 6: Run the plain pytest suite too, to catch anything Task 1 missed**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (some cases against real dashboards skip visibly without `DASHBOARD_HISTORY_REAL_STORAGE`/`tests/.real-storage` - see `CLAUDE.md`, "Tests").

- [ ] **Step 7: Commit**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        tests/integration/run_stale_pagination_cursor.py
git commit -m "$(cat <<'EOF'
Restart pagination instead of truncating past a forget

A before cursor a forget has rewritten past used to answer with an
empty page, indistinguishable from "nothing older exists" - hundreds
of older commits could still be sitting there under new shas. async_
history now restarts from the newest page and says restarted: true,
so a caller can show that instead of quietly hiding "load older". The
page and its generation are read from one executor hop, retried as one
sequence alongside list_versions (decision 24) rather than as two
independently scheduled jobs, closing a second gap review found: a
forget completing between two unordered reads could otherwise pair a
still-valid cursor with a generation number already past it.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: `panel.js` - replacing the list instead of appending to it

**Files:**
- Modify: `custom_components/dashboard_history/panel.js`
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `history.generation` and `history.restarted` from a `"history"` WebSocket answer (Task 2).
- Produces: `this._cursorGeneration`, `this._historyRestarted` - new instance fields on the panel custom element.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_panel_behaviour.py`, directly after `test_a_late_answer_for_a_row_no_longer_open_is_dropped`/`test_the_page_stays_busy_while_an_earlier_request_is_still_in_flight` (near `_HARNESS`, so it sits next to the other small, single-purpose harnesses):

```python
_HARNESS_STALE_CURSOR = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a", message: "1 card added", timestamp: 1 }];
el._cursor = "a";
el._cursorGeneration = 0;

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const older = el._loadOlder();
await settle();
calls[0].resolve({
  changes: [{ revision: "z", message: "9 cards moved", timestamp: 9 }],
  next_cursor: null,
  generation: 1,
  restarted: true,
});
await older;

console.log(JSON.stringify({
  sentBeforeGeneration: calls[0].extra.before_generation,
  changes: el._changes.map((c) => c.revision),
  cursor: el._cursor,
  cursorGeneration: el._cursorGeneration,
  restarted: el._historyRestarted,
}));
"""


@pytest.fixture(scope="module")
def stale_cursor_outcome(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "stale-cursor", _HARNESS_STALE_CURSOR)


def test_load_older_sends_the_remembered_generation(stale_cursor_outcome):
    assert stale_cursor_outcome["sentBeforeGeneration"] == 0


def test_a_restarted_answer_replaces_the_list_instead_of_appending(
    stale_cursor_outcome,
):
    # Not ["a", "z"] - the stale "a" is gone, the server sent the newest
    # page whole rather than a continuation of what was already shown.
    assert stale_cursor_outcome["changes"] == ["z"]


def test_a_restarted_answer_updates_the_cursor_and_is_remembered(
    stale_cursor_outcome,
):
    assert stale_cursor_outcome["cursor"] is None
    assert stale_cursor_outcome["cursorGeneration"] == 1
    assert stale_cursor_outcome["restarted"] is True


_HARNESS_ORDINARY_LOAD_OLDER = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "a", message: "1 card added", timestamp: 1 }];
el._cursor = "a";
el._cursorGeneration = 0;
el._historyRestarted = true; // left over from an earlier restart

const calls = [];
el._call = (type, extra) =>
  new Promise((resolve) => calls.push({ type, extra, resolve }));

const older = el._loadOlder();
await settle();
calls[0].resolve({
  changes: [{ revision: "b", message: "2 moved", timestamp: 2 }],
  next_cursor: null,
  generation: 0,
  restarted: false,
});
await older;

console.log(JSON.stringify({
  changes: el._changes.map((c) => c.revision),
  restarted: el._historyRestarted,
}));
"""


@pytest.fixture(scope="module")
def ordinary_load_older_outcome(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "ordinary-load-older", _HARNESS_ORDINARY_LOAD_OLDER
    )


def test_an_ordinary_answer_still_appends_and_clears_a_stale_restart_notice(
    ordinary_load_older_outcome,
):
    assert ordinary_load_older_outcome["changes"] == ["a", "b"]
    assert ordinary_load_older_outcome["restarted"] is False


_HARNESS_RESTART_NOTICE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el._dashboards = [{ key: "dash", title: "Dash", exists: true }];
el._versions = [];
el._verOpen = new Set();
el._changes = [{ revision: "a", message: "1 card added", versions: [], timestamp: 1 }];
el._cursor = "a";
el._historyRestarted = false;
const withoutNotice = el._renderMain();
el._historyRestarted = true;
const withNotice = el._renderMain();

console.log(JSON.stringify({
  withoutNotice: withoutNotice.includes("History changed while loading"),
  withNotice: withNotice.includes("History changed while loading"),
}));
"""


@pytest.fixture(scope="module")
def restart_notice_outcome(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "restart-notice", _HARNESS_RESTART_NOTICE)


def test_the_restart_notice_only_renders_while_it_applies(restart_notice_outcome):
    assert restart_notice_outcome["withoutNotice"] is False
    assert restart_notice_outcome["withNotice"] is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest tests/test_panel_behaviour.py -k "stale_cursor or restart_notice" -v`
Expected: FAIL - `calls[0].extra.before_generation` is `undefined`, the "restarted" scenario's `changes` comes back as `["a", "z"]` (appended) rather than `["z"]`, and `_renderMain()` never mentions the notice text at all.

- [ ] **Step 3: Track the generation and restart the list in `_loadOlder`**

In `custom_components/dashboard_history/panel.js`, in `_select` (around line 1363), where the paging state is reset for a newly picked dashboard, add two lines next to `this._cursor = null;`:

```js
    this._cursor = null;
    this._cursorGeneration = null;
    this._historyRestarted = false;
```

A little further down, where the first page's answer is unpacked (around line 1393-1395), add tracking for the generation next to `this._cursor`:

```js
    this._changes = history ? history.changes || [] : [];
    this._cursor = history ? history.next_cursor ?? null : null;
    this._cursorGeneration = history ? history.generation ?? null : null;
```

Change `_loadOlder` (around line 1412):

```js
  /**
   * Fetch the page below the one that is showing, and append it - or,
   * if a `forget` has rewritten past the cursor since it was issued,
   * replace the list with the newest page the server restarted from
   * instead. See issue #26: silently appending an empty page would
   * look exactly like "nothing older exists", when hundreds of older
   * commits could still be sitting there under new shas.
   *
   * Appended, never substituted, on the ordinary path: the button says
   * "load older", and a list that got shorter after pressing it would
   * be a lie told by a label. The claim ticket is the same one
   * `_select` uses, so a page that arrives after somebody has picked
   * another dashboard is dropped rather than stitched under a
   * stranger's history.
   */
  async _loadOlder() {
    if (!this._cursor || !this._selected) return;
    // A second press while the first page is still on its way asks for
    // exactly the same page again. Nothing breaks - the claim ticket
    // drops the loser, so the list is right either way - but the button
    // invites the double click more than anything else here does: it
    // sits at the bottom of a list, nothing about it changes while it
    // works, and the page it fetches is the slowest read the ordinary
    // path makes. Every other guarded action is one click on one row,
    // and answering "the others behave like this too" would be
    // answering about a different button.
    if (this._loadingOlder) return;
    const mine = this._claim("changes");
    const asked = this._cursor;
    const askedGeneration = this._cursorGeneration;
    this._loadingOlder = true;
    try {
      const result = await this._guard(
        () =>
          this._call("history", {
            dashboard: this._selected,
            limit: PAGE,
            before: asked,
            before_generation: askedGeneration,
          }),
        mine,
      );
      if (!mine() || !result) return;
      if (result.restarted) {
        this._changes = result.changes || [];
      } else {
        this._changes = this._changes.concat(result.changes || []);
      }
      this._historyRestarted = Boolean(result.restarted);
      this._cursor = result.next_cursor ?? null;
      this._cursorGeneration = result.generation ?? null;
      this._render();
    } finally {
      // In a `finally`, so a failure lets the button work again. A flag
      // that stuck after one refused request would leave the rest of
      // the history unreachable for as long as the page is open.
      this._loadingOlder = false;
    }
  }
```

- [ ] **Step 4: Show a short notice while a restart just happened**

In `_renderMain` (around line 3586), where `older` is built, add a notice right above it:

```js
    const restartedNotice = this._historyRestarted
      ? `<p class="muted">History changed while loading — showing the newest entries again.</p>`
      : "";
    const older = this._cursor
      ? `<div class="older">
           <button class="act ghost" data-older="1">Load older changes</button>
         </div>`
      : "";
    return topBar + behind + parts.join("") + restartedNotice + older;
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest tests/test_panel_behaviour.py -v`
Expected: PASS (the whole file - confirms the new fields do not disturb any existing scenario). If `node` is not installed, these are skipped visibly rather than passing quietly; install it or run this step where it is available before treating the task as done.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Replace the history list on a restarted page, not append to it

A page answered with restarted: true holds the newest entries, not a
continuation of what was already loaded - concatenating it under the
old list would have interleaved two unrelated ranges of history. The
panel now replaces the list and remembers the cursor's generation so
the next "load older" can prove whether it is still fresh, and shows
a short notice while that is the reason the list just changed. See
issue #26.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: Record decision 25 in the design spec and `status.md`

**Files:**
- Modify: `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`
- Modify: `docs/superpowers/status.md`

**Interfaces:**
- Consumes: nothing code-level: this task is documentation only, following the exact form decisions 21-24 already use in the same file.

- [ ] **Step 1: Add decision 25 to the spec**

In `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, decision 24 runs from line 647 to line 676 inclusive, ending immediately before the `## Fehler- und Randfälle` heading at line 677 - it is *not* just the numbered paragraph plus two follow-ups, it is four indented paragraphs after the numbered one. Insert decision 25 directly after line 676 (the paragraph beginning "Vier weitere Stellen dereferenzieren..."), immediately before `## Fehler- und Randfälle`:

```markdown
25. **Ein `before`-Cursor, den ein `forget` inzwischen überholt hat, wird nicht mehr still zu `[]` - er lässt die Seite neu beginnen und sagt das auch.** *(Nachgetragen am 2026-09-22, löst GitHub-Issue [#26](https://github.com/PPP01/ha-dashboard-history/issues/26) - bei der Umsetzung von Entscheidung 24 gefunden und dort bewusst zurückgestellt, weil es eine andere, produktseitige Frage ist: nicht ob ein Lesevorgang abstürzt, sondern was Blättern bedeuten soll, wenn die Historie darunter umgeschrieben wurde.)*

    `forget` gibt jedem überlebenden Commit eine neue Sha und entfernt die alten sofort (`grace_period=0`, Entscheidung 24). Ein `before`-Cursor aus einer früheren Seite nennt eine dieser alten Shas. Löst sie sich nicht mehr auf, kann `_resolve` nicht unterscheiden, ob sie nie gültig war oder ob genau dieses `forget` sie überholt hat - beides ergibt `None`. `HistoryStore` führt dafür eine persistierte, monoton steigende `forget_generation()`.

    Wer unterschieden werden will, reicht die Generation, die beim Ausstellen des Cursors galt, als neuen, ausdrücklich optionalen Parameter `before_generation` zurück. `_indexed_revisions`/`_walked_changes` werfen die neue `StaleCursorError` nur dann, wenn dieser Parameter mitgegeben wurde *und* älter ist als die aktuelle Generation. Ohne ihn bleibt die Antwort unverändert `[]` - der WebSocket-Befehl `dashboard_history/history` nimmt ein beliebiges `before` von jedem Aufrufer mit Admin-Rechten entgegen, nicht nur den vom Panel selbst zurückgegebenen Cursor, und ein externer Aufrufer, der den neuen Parameter nie übernommen hat, darf für einen möglichen Tippfehler nicht fälschlich einen Neustart der Seite gemeldet bekommen. Ein erstes Design ohne dieses Detail - ein einfacher, dauerhafter Boolean »irgendein `forget` ist schon einmal gelaufen« - wäre an genau dieser Stelle zu grob gewesen und wurde vor der Umsetzung durch ein externes Review verworfen.

    **Zwei Nebenläufigkeits-Lücken, beide erst durch externes Review gefunden, keine im ersten Entwurf.** Erstens: Der Generation-Zähler wird in `_finish_forget` als *allererster* Schritt geschrieben, bevor überhaupt ein Ref sich bewegt - nicht, wie zunächst entworfen, am Ende, kurz vor dem Löschen des Checkpoints. Ein Lesevorgang, der einen Cursor unauflösbar vorfindet, muss sich darauf verlassen können, dass der Zähler das schon zeigt; das gilt nur, wenn das Schreiben nachweislich vor dem eigentlichen Prunen passiert, unabhängig davon, was der bestehende `_retrying_a_forget_race`-Vergleich (HEAD plus Checkpoint, Entscheidung 24) davon mitbekommt - ein Review zeigte an einem konkreten Ablauf, dass dieser Vergleich allein hier eine Lücke lässt. Der Wert selbst ist dabei nicht mehr ein einfaches `+1`, sondern ein im Checkpoint mitgeführtes, festes Ziel: Ein durch Absturz unterbrochenes und danach wiederholtes `_finish_forget` schreibt so denselben Wert erneut, statt denselben abgeschlossenen `forget` doppelt zu zählen. Zweitens: `operations.async_history` liest die Seite und die Generation nicht mehr als zwei unabhängig geplante, ungeordnete Executor-Aufgaben, sondern gebündelt in einem Aufruf, und die gesamte Sequenz (zusammen mit `list_versions`) läuft durch dieselbe Wiederholung wie `async_search` (Entscheidung 24) - sonst hätte ein `forget`, das genau zwischen den beiden ungeordneten Lesevorgängen vollständig durchläuft, einem noch gültigen Cursor eine bereits zu hohe Generation mitgeben können, die eine spätere Prüfung fälschlich als »nicht veraltet« durchgehen lässt.

    **Ein schmales, bewusst hingenommenes Restrisiko bleibt, genau wie bei Entscheidung 24 selbst:** Die Bündelung in `operations.py` verengt das Zeitfenster, schließt es aber nicht mathematisch - ein `forget`, das exakt zwischen der gebündelten Lesung und der anschließenden Vertrauensprüfung durchläuft, und das bei jedem der `_FORGET_RACE_RETRIES` Versuche identisch, würde immer noch hindurchrutschen. Entscheidung 24 nimmt denselben Rest schon für ihre eigenen Wiederholungen hin (»selten genug, um lieber abzubrechen als eine stille Rückfalllösung zu entwerfen«) - diese Entscheidung übernimmt dieselbe Abwägung, an einem deutlich engeren Fenster als dem, das das Review am ersten Entwurf tatsächlich fand.

    `operations.async_history` fängt `StaleCursorError`, ruft sich selbst mit `before=None` neu auf und markiert die Antwort mit `restarted: true`; jede Antwort trägt außerdem `generation` für die nächste Anfrage. Das Panel ersetzt seine Liste in diesem Fall, statt sie zu verlängern, und zeigt einen kurzen Hinweis, statt den »Load older changes«-Knopf einfach verschwinden zu lassen - ein Verhalten, das sich sonst nicht von »keine ältere Historie vorhanden« unterschieden hätte, obwohl darunter weiterhin Hunderte Commits stehen können.
```

- [ ] **Step 2: Update `status.md`**

In `docs/superpowers/status.md`, in the "Bekannte offene Punkte" section (the bulleted list starting after the line "Aus der Spec, Abschnitt »Offene Punkte«..."), add a new bullet directly after the D3 entry ("Löschen und schnelles Wiederanlegen...") and before the D6 entry, matching the exact struck-through-then-resolved form the D1/checkpoint entries above it already use:

```markdown
- ~~**Ein `before`-Paginierungs-Cursor überlebt kein `forget`, das über ihn hinaus umschreibt.** *(Gefunden bei der Umsetzung von Entscheidung 24, GitHub-Issue [#26](https://github.com/PPP01/ha-dashboard-history/issues/26), dort bewusst zurückgestellt.)* `_indexed_revisions` antwortete für einen inzwischen geprunten Cursor genauso wie für einen nie gültigen: mit `[]`, ununterscheidbar von »keine ältere Historie mehr vorhanden«, obwohl darunter weiterhin Hunderte Commits unter neuen Shas stehen konnten.~~ **Behoben am 2026-09-22** (Entscheidung 25). Eine persistierte, monoton steigende `forget_generation()` und ein optionaler Parameter `before_generation` unterscheiden jetzt die beiden Fälle; `operations.async_history` startet die Seite bei einem veralteten Cursor neu und meldet `restarted: true`, statt still zu verkürzen.
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-30-dashboard-history-design.md docs/superpowers/status.md
git commit -m "$(cat <<'EOF'
Record decision 25 in the design journal

The design journal under docs/superpowers/ stays German by the
project's own convention (see CLAUDE.md, "Language"); this plan
records the decision this branch implements in the same place
decisions 21-24 already live.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-review notes

- **Spec coverage:** every element of the approved design (generation counter, its write-ordering and idempotency, `StaleCursorError`, its two call sites, `async_history`'s bundled read and restart, the WebSocket schema, the panel's replace-not-append handling and its rendered notice, and recording the decision) has a task. No gaps found on this pass.
- **Backward compatibility, re-verified against the actual test tree, not assumed:** every new store-layer parameter defaults to `None`/absent. `list_changes`'s call to `_each_change` is conditional specifically because a direct search confirmed eight existing tests in `tests/test_store.py` monkeypatch `_each_change` with its current four-parameter shape (`test_list_changes_retries_a_read_that_raced_forget` and seven neighbors) - an earlier draft of this plan added the parameter unconditionally and would have broken all eight, caught only by actually grepping for every override rather than trusting the one or two a first review pass happened to notice. Similarly, `_read_checkpoint`'s new `target_generation` field falls back to a computed value rather than raising when absent, because a second search found over a dozen existing tests hand-write checkpoint JSON without it, each testing an unrelated validation failure that a required field would otherwise mask.
- **Type consistency:** `before_generation: int | None = None` is spelled identically across `list_changes`, `_each_change`, `_indexed_revisions`, `_walked_changes` (Task 1), `async_history`/`_changes_and_generation` (Task 2), and the WebSocket schema's `vol.Any(None, int)` (Task 2); the response fields `generation`/`restarted`/`next_cursor` are named identically wherever Task 2 and Task 3 refer to them. `_finish_forget`'s new `target_generation` parameter sits in the same position (before `say`) at both of its two call sites.
- **Concurrency claims are demonstrated, not asserted:** Task 1 includes a test (`test_the_generation_bump_happens_before_any_object_is_pruned`) that fails immediately if the write-ordering fix ever regresses, rather than relying on the prose argument alone. Task 2's third integration scenario exercises the specific gap review found, using the same interruption technique `run_search_past_a_forget.py` already established for the analogous `async_search` race, rather than a scenario invented for this plan alone.
