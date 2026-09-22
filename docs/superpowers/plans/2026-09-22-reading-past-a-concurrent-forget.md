# Reading Past a Concurrent `forget` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A read that races a concurrent `forget` rebuilds its answer against the new state instead of crashing with an unhandled `KeyError`/`MissingCommitError` - and never silently returns a result that mixes two different generations of the repository either, even when nothing raises at all. The handful of single-object reads with the same, narrower exposure fail the same way an unknown revision already does today.

**Architecture:** `forget` gives every surviving commit from the earliest touched point a fresh sha and prunes the old ones immediately (`grace_period=0`). A read that pulled its revision list before that rewrite holds shas that stop existing mid-read. `_each_change` (two callers: `list_changes`, `search_changes`) is the one place this reaches a caller unhandled, and the only one that loops over many revisions - so it gets a shared retry primitive that discards a failed attempt entirely and rebuilds the whole answer fresh, rather than resuming mid-walk (already-yielded entries can't be taken back, and old shas wouldn't match the new generation anyway). That primitive trusts a result - success or failure - only if HEAD read the same both before and after the whole rebuild *and* no `forget` checkpoint is on disk at that point: a `forget` that completes entirely between two separate reads inside one build never raises anything, and a read starting after HEAD already settled but before notes/tags catch up sees a HEAD that never moves during its own execution at all, so HEAD alone cannot catch either case. Four other reads dereference a resolved revision exactly once, right after resolving it; they get a matching one-line guard instead, answering exactly as they already do for an unknown revision. `operations.async_search` owns a second copy of the same race, one layer up and across the sync/async boundary, because it holds onto `versions` across the store call - it gets the identical two-signal trust rule, on its own side of that boundary.

**Tech Stack:** Python 3, `dulwich` 1.2.14 (pinned). `store.py` is one of the seven Home-Assistant-free modules, tested under plain `pytest`. `operations.py` imports `homeassistant` and is tested via `docker exec` against the project's test container (no running instance needed for this plan's change).

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, decision 24. Read that section before starting - it explains why the fix is a full rebuild rather than a resume, why a plain HEAD-moved check is not sufficient on its own, why the checkpoint file closes the remaining gap, why `search_changes` splits into two cases, and which findings were deliberately left out (issue #26, a `before` pagination cursor not surviving *any* `forget`, race or not - out of scope here). Where this plan and decision 24 disagree, the spec is binding.

**Out of scope, tracked separately:** issue [#26](https://github.com/PPP01/ha-dashboard-history/issues/26) - a `before` cursor from an earlier page does not resolve any more once a `forget` has rewritten past it, whether or not a race was involved. `_indexed_revisions` already answers that with `[]`, indistinguishable from "no more history." This plan's retry does not change that answer and is not meant to - it is a different, product-level question (what should "load more" do) that needs its own design pass.

## Global Constraints

- No shelling out to `git`. `dulwich` only (`CLAUDE.md`, "Hard rules").
- `store.py` must not `import homeassistant`, directly or indirectly - it stays testable under plain `pytest`.
- Blocking work belongs in an executor (`hass.async_add_executor_job`) - already true for every call this plan touches in `operations.py`; nothing here changes that.
- Test commands: `python3 -m pytest tests/ -v` for everything in `store.py`; `docker exec -i dashboard-history-test python3 - < tests/integration/run_search_past_a_forget.py` for the one piece that touches `operations.py` (see Task 4 for why this tier, not a live instance, is enough).
- Commit message format (`CLAUDE.md`, "Git"): English, imperative subject, blank line, body wrapped at 72 characters explaining the *why*, referencing issue #20. Every commit ends with `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>` (see the git log of commits `93c2ab3`, `1f302f2` for the exact form this project uses even when a different agent executes the plan).

---

## Files touched

| File | Role |
|---|---|
| `custom_components/dashboard_history/store.py` | New `_FORGET_RACE_RETRIES` constant, `HistoryStore._current_head`, `HistoryStore.forget_in_progress` (public), and `HistoryStore._retrying_a_forget_race`; `_each_change`'s signature; `list_changes`, `search_changes`, `commit_times`, `list_dashboards`, `survey`, `previous_change` all get narrower or wider guards. |
| `custom_components/dashboard_history/operations.py` | `async_search` gains its own retry, wrapping `list_versions` + `search_changes` + `marks` together. |
| `tests/test_store.py` | New tests for the retry primitive, both `_each_change` callers, and the four narrow guards. |
| `tests/integration/run_search_past_a_forget.py` | New tier-3 script (no running instance) covering `operations.async_search`'s retry. |

No other file needs to change.

---

### Task 1: The shared retry primitive, wired into `list_changes`

**Files:**
- Modify: `custom_components/dashboard_history/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `HistoryStore._repo`, `HistoryStore._resolve`, `HistoryStore._checkpoint_path` (all existing).
- Produces:
  - Module constant `_FORGET_RACE_RETRIES = 3` (top of `store.py`, near the other module-level constants - if there are none yet, place it directly above the `HistoryStore` class definition).
  - `HistoryStore._current_head(self, repo: Repo) -> object` - new method. Returns whatever `self._resolve(repo, "HEAD")` returns, or a fresh, never-equal-to-anything-else `object()` if that itself raised `KeyError`/`MissingCommitError`.
  - `HistoryStore.forget_in_progress(self) -> bool` - new **public** method (needed outside `store.py` too, by Task 4). Whether `self._checkpoint_path().exists()`.
  - `HistoryStore._retrying_a_forget_race(self, repo: Repo, build: Callable[[], list[Change]]) -> list[Change]` - new method. Trusts a result - success or failure - only if HEAD read the same both before and after `build()` ran *and* `forget_in_progress()` is false at that point; otherwise rebuilds, up to the fixed budget.
  - `HistoryStore._each_change(self, repo: Repo, key: str, limit: int | None = 50, before: str | None = None) -> Iterator[Change]` - **signature change**: `repo` is now the first parameter after `self`, required, no longer resolved internally. Every other task and every existing caller must pass it explicitly from here on.
  - `HistoryStore.list_changes(self, key: str, limit: int | None = 50, before: str | None = None) -> list[Change]` - same signature, new retry behavior.

First, add an import the tests below need. In `tests/test_store.py`, change:

```python
import dulwich.refs
```

to:

```python
import dulwich.refs
from dulwich.errors import MissingCommitError
```

(Task 2 and Task 3 also need this; adding it here, where it is first used, means neither has to touch this line again.)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, directly after `test_forgetting_removes_the_dashboard_from_the_history` (so it sits next to the other `forget`-based tests):

```python
def test_list_changes_retries_a_read_that_raced_forget(store, monkeypatch):
    """A read that hits the known KeyError/MissingCommitError race - a
    concurrent `forget` pruning a commit this read already had a
    revision list for - rebuilds against the moved HEAD instead of
    raising. See decision 24.

    `_each_change` is monkeypatched rather than dulwich itself: the
    real race needs true thread concurrency to reproduce on demand
    (the issue's own report: four instrumented runs did not recur).
    This drives the same two facts a real race would - a `KeyError`
    reaching `list_changes`, and HEAD having genuinely moved by the
    time it does - deterministically, the same way
    `test_forget_writes_a_checkpoint_before_the_first_ref_moves`
    interrupts a real `forget` at an exact point instead of guessing
    at timing.

    "gone" is written *before* "home", not after: `forget` gives every
    commit a fresh sha only if something about its own content or its
    ancestry changed. Commit shas are content hashes - a commit written
    after "gone" is forgotten has nothing to rewrite (nothing pointed
    at it, its own tree never held "gone.yaml"), so writing "gone"
    last would forget it "for free," without a single sha of "home"'s
    ever changing - and the retry this test means to exercise would
    pass even if `list_changes` never rebuilt anything at all.
    """
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")  # moves HEAD for real, out from under this read
            raise KeyError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert len(calls) == 2


def test_list_changes_does_not_retry_when_head_is_unchanged(store, monkeypatch):
    """If HEAD never moved, the known race cannot explain the error -
    something else is broken, and that must stay visible, not get
    silently retried into looking fine. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    calls: list[int] = []

    def always_fails(self, repo, key, limit=50, before=None):
        calls.append(1)
        raise KeyError(b"simulated: unrelated corruption")
        yield  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setattr(HistoryStore, "_each_change", always_fails)

    with pytest.raises(KeyError):
        store.list_changes("home")
    assert len(calls) == 1


def test_list_changes_gives_up_after_the_retry_budget(store, monkeypatch):
    """A read that keeps racing a `forget` on every single attempt still
    terminates - the retry budget is a hard cap, not a promise that a
    third attempt will succeed. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    for i in range(5):
        store.write_snapshot(f"gone{i}", "b: 1\n", "gone first")
    calls: list[int] = []

    def always_races(self, repo, key, limit=50, before=None):
        calls.append(1)
        store.forget(f"gone{len(calls) - 1}")  # moves HEAD every single time
        raise KeyError(b"simulated: perpetual race")
        yield  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setattr(HistoryStore, "_each_change", always_races)

    with pytest.raises(KeyError):
        store.list_changes("home")
    assert len(calls) == 3


def test_list_changes_returns_empty_when_the_watched_dashboard_is_forgotten_mid_read(
    store, monkeypatch
):
    """No special case: if the dashboard being read is itself forgotten
    by the concurrent `forget` racing it, the rebuilt answer is the
    same empty list an unknown key already produces today - confirmed
    during design, not just asserted. See decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("home")
            raise KeyError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    assert store.list_changes("home") == []
    assert len(calls) == 2


def test_list_changes_is_unaffected_when_nothing_races_it(store):
    """The ordinary path - no exception, ever - must produce exactly
    what it did before this change. A guard against the retry
    machinery changing behavior for the overwhelming majority of
    calls that never hit the race at all."""
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]


def test_list_changes_retries_a_read_that_raced_forget_with_missing_commit_error(
    store, monkeypatch
):
    """The same race can surface as `MissingCommitError` instead of
    `KeyError` - dulwich's walker raises that one, not a subclass of
    `KeyError`, when an object vanishes mid-walk. Decision 24 requires
    both be caught; this is the companion to
    `test_list_changes_retries_a_read_that_raced_forget` that would go
    unnoticed if a future edit narrowed the caught exceptions to just
    `KeyError`."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")
            raise MissingCommitError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert len(calls) == 2


def test_list_changes_retries_a_successful_read_if_head_moved_during_it(
    store, monkeypatch
):
    """A `build()` that raises nothing can still be stale: `_each_change`
    reads `descriptions()` and the revision list as two separate steps,
    and a `forget` that runs to completion entirely between them mixes
    generations without either individual read ever failing. Trusted
    only if HEAD read the same right after `build()` returns as it did
    right before this attempt began - not just "no exception was
    raised". See decision 24.
    """
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")  # completes fully, no exception here at all
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert len(calls) == 2


def test_list_changes_retries_when_a_checkpoint_is_present_even_if_head_is_stable(
    store, monkeypatch
):
    """HEAD alone cannot catch every case: a read starting after
    `_point_head` already ran, but before `_rewrite_notes`/
    `_rewrite_tags` finish, sees a HEAD that never moves during its
    own execution at all (issue #27). The checkpoint file (decision
    21) is present for the whole span of `_finish_forget`, not just
    the instant HEAD moves, and catches this case instead. No real
    `forget` runs in this test at all - HEAD never moves - only the
    checkpoint's mere presence must be enough to distrust the result.
    See decision 24.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=50, before=None):
        calls.append(1)
        if len(calls) == 1:
            checkpoint.write_text("{}", encoding="utf-8")
            yield from real_each_change(self, repo, key, limit, before)
            return
        checkpoint.unlink()
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    changes = store.list_changes("home")

    assert [c.message for c in changes] == ["second", "first"]
    assert len(calls) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "test_list_changes" -v`

Expected: 2 of the 8 PASS already, for two different reasons that both stop mattering once Step 3 lands. `test_list_changes_is_unaffected_when_nothing_races_it` passes because nothing about the ordinary path is broken yet. `test_list_changes_does_not_retry_when_head_is_unchanged` also passes already, but only by coincidence: `list_changes` has no retry of any kind yet, so its fake raises once, `list_changes` does not catch it, `pytest.raises(KeyError)` catches it at the test boundary, and `len(calls) == 1` holds trivially - the same shape "no retry happened" takes whether there is no retry mechanism at all or a correct one that examined HEAD and rightly declined. The other 6 FAIL - not for the reason they will once this task is done. `_each_change`'s current signature is still `(self, key, limit=50, before=None)`, with no `repo` parameter, while `list_changes`'s current body still calls it as `self._each_change(key, limit, before)` - the monkeypatched fakes below (written against the *new*, `repo`-first signature) either bind the wrong parameters entirely or, where a fake falls through to `real_each_change(self, repo, key, limit, before)` (5 arguments against the *old* `_each_change`'s 4), raise `TypeError` outright. Do not spend time predicting the exact resulting exception for any of the 6; the point of this step is only that they fail somehow, for a reason Step 3 makes moot by aligning `list_changes`'s call and `_each_change`'s signature with what the fakes already assume.

- [ ] **Step 3: Write the minimal implementation**

In `store.py`, add the module constant near the top, directly above the `HistoryStore` class definition:

```python
_FORGET_RACE_RETRIES = 3
```

Add three new methods directly after `_each_change` (which Step 3 also modifies, below), before `_walked_changes`:

```python
    def _current_head(self, repo: Repo) -> object:
        """HEAD right now, or a value that never equals a previous
        observation if reading it itself raced a `forget`.

        `_resolve` dereferences an object internally (`obj = repo[sha]`
        near its end), unguarded - a `forget` that prunes exactly what
        it is about to read can make even this fail with the same two
        exceptions `_retrying_a_forget_race` exists to survive.
        Answering `None` for that would be wrong: two failed
        observations would then compare equal to each other, and a
        real, ongoing race would go undetected. A fresh `object()`
        compares equal to nothing but itself. See decision 24.
        """
        try:
            return self._resolve(repo, "HEAD")
        except (KeyError, MissingCommitError):
            return object()

    def forget_in_progress(self) -> bool:
        """Whether an earlier `forget` has not finished cleaning up yet.

        The same checkpoint file write paths already refuse against
        (`_refuse_if_forget_pending`, decision 21) - reads use it too
        now, to know when a result might mix two generations of the
        repository. Present for the *whole* span of `_finish_forget`,
        from before HEAD moves to after garbage collection - catches
        a read that starts after HEAD already settled but before
        notes/tags catch up, which a HEAD comparison alone cannot see
        (issue #27). Public: `operations.async_search`'s own retry
        (decision 24) reads it too, from outside this module.
        """
        return self._checkpoint_path().exists()

    def _retrying_a_forget_race(
        self, repo: Repo, build: Callable[[], list[Change]]
    ) -> list[Change]:
        """Run `build`, rebuilding it whole if it raced a `forget`.

        `build` must read everything it needs itself, fresh, every time
        it runs - a retry here discards whatever a failed attempt had
        already produced rather than resuming it. Necessary, not just
        cautious: `forget` gives every surviving commit downstream of
        the earliest touched point a new sha (`_forget`, `store.py`),
        so a walk resumed at the point it broke would not even be a
        valid continuation of the same answer, let alone a correct one.

        A result is trusted - whether `build()` raised or returned
        normally - only if, checked right after, HEAD reads the same
        as it did when this attempt began *and* `forget_in_progress()`
        is false. Checking only on failure would miss a `forget` that
        completes entirely between two separate reads inside one
        `build()` (`descriptions()` then the walk, in `_each_change`;
        `list_versions()` then `search_changes()`, one layer up in
        `operations.py`) - neither individually raises, so nothing
        would ever trigger a retry, yet the result quietly mixes two
        generations. The checkpoint check catches what HEAD alone
        cannot: a read that starts after HEAD already moved but before
        notes or tags catch up sees a HEAD that never moves again
        during its own execution at all. See decision 24.

        Commit shas are content hashes over tree and parents, so HEAD
        can never cycle back to a value already seen; combined with
        the fixed budget below, this always terminates regardless of
        how unsettled the repository stays.
        """
        head = self._current_head(repo)
        for _ in range(_FORGET_RACE_RETRIES - 1):
            try:
                found = build()
            except (KeyError, MissingCommitError):
                moved = self._current_head(repo)
                if moved == head and not self.forget_in_progress():
                    raise
                head = moved
                continue
            moved = self._current_head(repo)
            if moved == head and not self.forget_in_progress():
                return found
            head = moved
        return build()
```

Modify `_each_change` to accept `repo` instead of resolving it itself:

```python
    def _each_change(
        self, repo: Repo, key: str, limit: int | None = 50, before: str | None = None
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
        revisions = self._indexed_revisions(repo, key, before)
        if revisions is not None:
            for position, revision in enumerate(revisions):
                following = (
                    revisions[position + 1]
                    if position + 1 < len(revisions)
                    else None
                )
                yield _change(repo[revision.encode()], notes, following)
            return
        yield from self._walked_changes(repo, key, notes, limit, before)
```

Modify `list_changes`:

```python
    def list_changes(
        self, key: str, limit: int | None = 50, before: str | None = None
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
        takes the same line.

        A list, and the signature says so: every caller here wants one,
        and a page of fifty is a list whatever it is built from. The
        walk underneath is `_each_change`, which hands them over one at
        a time; the slice is what turns the extra look-ahead entry back
        into the page that was asked for.

        Rebuilt whole, up to `_FORGET_RACE_RETRIES` times, if a
        concurrent `forget` pruned a commit this walk already held a
        revision for - see `_retrying_a_forget_race` and decision 24.
        """
        repo = self._repo()
        if repo is None:
            return []

        def build() -> list[Change]:
            found = self._each_change(repo, key, limit, before)
            # Sliced after the walk, so the extra entry did its one job -
            # being the predecessor of the last one - and then goes.
            return list(found) if limit is None else list(islice(found, limit))

        return self._retrying_a_forget_race(repo, build)
```

`_each_change`'s new `repo` parameter has one other call site - `search_changes`, inside its own `for change in self._each_change(key, None):` line. `search_changes` gets its *full* treatment (the retry, the `versions`-ownership split) in Task 2 - but leaving its call unpatched until then would call `_each_change` with `key` where `repo` is now expected, breaking every existing `search_changes` test for the length of this one commit. Keep the suite green in the meantime with the smallest possible change - adapt the call, nothing else. `search_changes` never opened `repo` itself before (it went through `_each_change`'s own, now-removed `self._repo()` call); it needs to now, guarded the same way every other method here already guards it - a bare `self._repo()` inline, with no `None` check, would turn a missing repository from today's quiet `[]` into a crash for the length of this one commit. Replace:

```python
        needle = text.strip().casefold()
        if not needle:
            return []
        if versions is None:
```

with:

```python
        needle = text.strip().casefold()
        if not needle:
            return []
        repo = self._repo()
        if repo is None:
            return []
        if versions is None:
```

and replace:

```python
        for change in self._each_change(key, None):
```

with:

```python
        for change in self._each_change(repo, key, None):
```

(Both of these exact lines are replaced again, as part of a larger change, in Task 2 - expected, not a conflict.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k "test_list_changes" -v`

Expected: all PASS - the eight new tests from Step 1, plus every pre-existing `test_list_changes_*` test.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -v`

Expected: everything that passed before still passes, `search_changes`'s existing tests included - the transitional fix above is exactly what keeps them green until Task 2 gives `search_changes` its own retry.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Retry a history read that raced a concurrent forget

_each_change dereferences a revision list built from whatever HEAD
was current when the read started. forget gives every surviving
commit downstream of the earliest touched point a fresh sha and
prunes the old ones immediately - a read caught mid-walk holds shas
that stop existing before it finishes, and list_changes crashed with
an unhandled KeyError (issue #20). Retried whole, never resumed:
already-yielded entries can't be taken back, and old shas wouldn't
match the new generation regardless.

A result is trusted only if HEAD read the same both before and after
the whole rebuild, and no forget checkpoint is on disk at that point
- not just "nothing raised". Neither individually catches a forget
that completes entirely between two separate reads inside one build
(descriptions() then the walk here; list_versions() then
search_changes(), one layer up in Task 4), or a read that starts
after HEAD already settled but before notes/tags catch up (issue
#27) - together they do. The HEAD read itself is protected the same
way, since _resolve dereferences an object internally and can race
the exact prune it exists to detect.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: `search_changes` - retry when it owns its inputs, propagate when it does not

**Files:**
- Modify: `custom_components/dashboard_history/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: `_FORGET_RACE_RETRIES`, `HistoryStore._retrying_a_forget_race`, `HistoryStore._each_change(self, repo, key, limit, before)` (all from Task 1).
- Produces: `HistoryStore.search_changes(self, key: str, text: str, limit: int = 50, versions: list[Version] | None = None) -> list[Change]` - same signature, new retry behavior for the `versions is None` case, and a *removed* implicit safety net for the `versions` explicitly-supplied case (it now propagates `KeyError`/`MissingCommitError` instead of ever crashing silently-wrong - see the step below for why).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, directly after the eight tests from Task 1:

```python
def test_search_changes_retries_when_it_fetches_its_own_versions(store, monkeypatch):
    """search_changes owns `versions` when the caller does not supply
    it - it can safely rebuild everything, the same way list_changes
    does. See decision 24.

    "gone" is written before "home", not after - see
    `test_list_changes_retries_a_read_that_raced_forget`'s docstring
    for why writing it last would let this pass without `home`'s own
    shas ever actually changing.
    """
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first unique-needle")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=None, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")
            raise KeyError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    found = store.search_changes("home", "unique-needle")

    assert [c.message for c in found] == ["first unique-needle"]
    assert len(calls) == 2


def test_search_changes_retries_with_missing_commit_error_too(store, monkeypatch):
    """Companion to `test_search_changes_retries_when_it_fetches_its_own_versions`,
    with `MissingCommitError` instead of `KeyError` - see
    `test_list_changes_retries_a_read_that_raced_forget_with_missing_commit_error`
    in Task 1 for why both need their own coverage."""
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.write_snapshot("home", "a: 1\n", "first unique-needle")

    real_each_change = HistoryStore._each_change
    calls: list[int] = []

    def flaky_each_change(self, repo, key, limit=None, before=None):
        calls.append(1)
        if len(calls) == 1:
            store.forget("gone")
            raise MissingCommitError(b"simulated: pruned mid-read")
            yield  # pragma: no cover - unreachable, keeps this a generator
        yield from real_each_change(self, repo, key, limit, before)

    monkeypatch.setattr(HistoryStore, "_each_change", flaky_each_change)

    found = store.search_changes("home", "unique-needle")

    assert [c.message for c in found] == ["first unique-needle"]
    assert len(calls) == 2


def test_search_changes_does_not_retry_when_the_caller_supplied_versions(
    store, monkeypatch
):
    """search_changes does not own a caller-supplied `versions` list and
    must not silently rebuild around it: a retry here would return
    changes carrying new shas while the caller's own `versions` (and
    anything the caller derives from it, such as
    operations.async_search's `marks`) still names the old ones -
    every version match in the result would fail with no signal that
    anything went wrong. See decision 24 and issue #20's review."""
    revision = store.write_snapshot("home", "a: 1\n", "first unique-needle")
    store.create_version("home/v1.0.0", "Home", "", revision)
    versions = store.list_versions("home")
    calls: list[int] = []

    def always_fails(self, repo, key, limit=None, before=None):
        calls.append(1)
        raise KeyError(b"simulated: pruned mid-read")
        yield  # pragma: no cover - unreachable, keeps this a generator

    monkeypatch.setattr(HistoryStore, "_each_change", always_fails)

    with pytest.raises(KeyError):
        store.search_changes("home", "unique-needle", versions=versions)
    assert len(calls) == 1


def test_search_changes_is_unaffected_when_nothing_races_it(store):
    """The ordinary path - both with and without a caller-supplied
    `versions` - must produce exactly what it did before this
    change."""
    store.write_snapshot("home", "a: 1\n", "first unique-needle")

    assert [c.message for c in store.search_changes("home", "unique-needle")] == [
        "first unique-needle"
    ]
    versions = store.list_versions("home")
    assert [
        c.message for c in store.search_changes("home", "unique-needle", versions=versions)
    ] == ["first unique-needle"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "test_search_changes" -v`

Expected: two of the four PASS already, for reasons that stop being coincidental once Step 3 lands. `test_search_changes_is_unaffected_when_nothing_races_it` passes because Task 1's transitional fix already made `search_changes` call `_each_change` correctly - nothing about the ordinary path needs Step 3 at all. `test_search_changes_does_not_retry_when_the_caller_supplied_versions` also passes already, but only by coincidence: `search_changes` has no retry logic of any kind yet, so "does not retry when given `versions`" trivially holds the same way "does not retry" would hold for *any* input right now. `test_search_changes_retries_when_it_fetches_its_own_versions` and its `MissingCommitError` companion both FAIL - each expects a matched, retried result, but with no retry yet, `flaky_each_change`'s first-call exception propagates straight out of `search_changes` unhandled instead. All four take on their intended meaning once Step 3 lands.

- [ ] **Step 3: Write the minimal implementation**

Replace `search_changes` in `store.py`:

```python
    def search_changes(
        self,
        key: str,
        text: str,
        limit: int = 50,
        versions: list[Version] | None = None,
    ) -> list[Change]:
        """Recorded states of one dashboard whose words hold `text`.

        The whole history, not the page a caller happens to hold, and
        that is the entire point. The panel searches what it has loaded
        first because that answers without a round trip; it asks this
        only when that found nothing, and at that moment "nothing" has
        to mean nothing - not "nothing among the newest twenty-five".

        Matched against four things, ignoring case: the generated
        message, a person's own description, and the title, description
        and number of every version sitting on that state. One word
        finds either kind, because somebody searching for words they
        remember writing does not remember which of the two places they
        wrote them in.

        Of a version's name only the number counts - `home/v1.0.0` is
        searched as `v1.0.0`. The namespace is the dashboard's own key,
        and that is also the word a person uses for the dashboard, so
        searching it would make every version of it a hit for a word
        that says nothing.

        The panel matches the same four things over what it has already
        loaded, so that the common search costs no round trip, and asks
        this only when that found nothing. Two copies of one rule:
        `tests/test_panel_assets.py` reads both sides and compares the
        fields, so adding one here alone goes red rather than quiet.

        One difference between the copies is real. Case is folded here
        and only lowercased there, because JavaScript has no casefold:
        `strasse` finds a row saying `Straße` in this method and misses
        it in the panel. That is the harmless direction - a miss up
        there escalates and arrives here, which then finds it - and it
        is the only harmless one, because a hit up there that this
        method would not have made stands as the whole answer with
        nothing to correct it.

        An empty search finds nothing rather than everything. It is the
        state of a search box somebody has just cleared, and answering
        it with the whole history is the opposite of what that means.

        `versions` is this dashboard's tag list, for a caller that has
        already read it. `operations.async_search` has: it needs the
        same list to say which versions sit on the rows it hands back,
        and without this it read it once and this method read it again,
        two scans of the same tags for one answer. Left out, the list is
        read here as before, which is what every test and every other
        caller relies on.

        Retried whole, like `list_changes`, when this method fetched
        `versions` itself - it owns every input and a rebuild is safe.
        When `versions` came from the caller, retrying here would not
        be: `operations.async_search` also derives its own `marks` from
        that same list, outside this method's reach, and a rebuild here
        would hand back new shas against `marks` still naming the old
        ones - every version match failing with nothing to say why. The
        error propagates unhandled in that case instead; the one caller
        that supplies `versions` retries its own whole sequence around
        this call. See decision 24.
        """
        needle = text.strip().casefold()
        if not needle:
            return []
        repo = self._repo()
        if repo is None:
            return []
        given_versions = versions is not None

        def build() -> list[Change]:
            active_versions = versions if given_versions else self.list_versions(key)
            marks: dict[str, list[Version]] = {}
            for version in active_versions:
                marks.setdefault(version.revision, []).append(version)
            found: list[Change] = []
            # The walk is unbounded and is the expensive part: measured at
            # roughly half a second per thousand commits. It runs in an
            # executor, and only after a local search found nothing.
            #
            # `_each_change` rather than `list_changes(key, None)`, so the
            # limit bounds the work and not only the answer. Built as a list
            # first, the whole history of the dashboard was materialised
            # before the first comparison was made - the `break` below then
            # only stopped the reading of something already in memory.
            for change in self._each_change(repo, key, None):
                words = [change.message, change.description]
                for version in marks.get(change.revision, []):
                    # The description as a reader sees it. Stored, it can
                    # carry the marker that says a version was made
                    # automatically, and that marker is words: searching
                    # `automatic`, `history` or `dashboard` would otherwise
                    # return every automatically versioned state, for a
                    # sentence nobody wrote and nobody is shown. Every other
                    # way out of here strips it; this was the one that did
                    # not.
                    said, _ = versioning.read_description(version.description)
                    words += [
                        version.name.rsplit("/", 1)[-1],
                        version.title,
                        said,
                    ]
                if needle in "\n".join(words).casefold():
                    found.append(change)
                    if len(found) >= limit:
                        break
            return found

        if given_versions:
            return build()
        return self._retrying_a_forget_race(repo, build)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k "test_search_changes" -v`

Expected: all PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -v`

Expected: everything passes, including every pre-existing `search_changes`/`list_changes` test untouched by this plan.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Split search_changes's retry on who owns its versions list

search_changes shares _each_change's race (issue #20) through its
own caller, list_changes's Task 1 fix. When it fetches versions
itself it owns every input and can rebuild the same way; when a
caller supplies versions - only operations.async_search does, to
avoid a second tag scan - a rebuild here would return new shas
against a versions list the caller still holds at the old ones,
and every match would fail with nothing to say why. Propagates
unhandled in that case instead, so the caller can retry its own
whole sequence.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Four single-dereference reads get the same guard an unknown revision already produces

**Files:**
- Modify: `custom_components/dashboard_history/store.py`
- Test: `tests/test_store.py`

**Interfaces:**
- Consumes: nothing new - each fix is local to its own method.
- Produces: `HistoryStore.commit_times`, `HistoryStore.list_dashboards`, `HistoryStore.survey`, `HistoryStore.previous_change` - all unchanged signatures, each with one narrower failure mode closed.

No retry machinery here: each of these dereferences a `_resolve`-returned sha exactly once, immediately after resolving it - unlike `_each_change`, there is nothing to loop over and nothing a silent skip could desynchronize. Each gets a plain guard answering exactly what it already answers for a revision that never resolved.

Every test below fakes `HistoryStore._resolve` (and, where relevant, `HistoryStore._revision_index`) to return a value deterministically instead of letting the method under test call the real one. This is deliberate, not a shortcut: `_resolve` itself reads the same object more than once internally (once resolving the candidate, once more following a possible tag chain), and `_revision_index` can call `_resolve` again on top of that - patching `Repo.__getitem__`/`Repo.get_walker` to fail by call count would require counting through all of that correctly, and silently starts testing the wrong line the moment any of those internals change shape. Faking the resolve step to a known-good value and then failing the *one* dereference each test is actually about is exact regardless of what `_resolve`/`_revision_index` do internally.

First, add the one remaining import this task's tests need - `MissingCommitError` was already added in Task 1 (its own `MissingCommitError`-based tests need it earlier), so only `RevisionIndex` is missing here. In `tests/test_store.py`, change:

```python
from store import HistoryStore, Version, _as_text
```

to:

```python
from store import HistoryStore, RevisionIndex, Version, _as_text
```

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, directly after the tests from Task 2:

```python
def test_commit_times_skips_a_revision_pruned_between_resolve_and_read(
    store, monkeypatch
):
    """A concurrent `forget`'s prune can land between `_resolve`
    succeeding and the very next line reading `commit_time` - see
    decision 24. Left out, exactly like a revision that never resolved
    at all (the method's own docstring already promises that)."""
    revision = store.write_snapshot("home", "a: 1\n", "first")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: revision)
    )
    real_getitem = Repo.__getitem__

    def broken_getitem(self, name):
        if name == revision.encode():
            raise KeyError(name)
        return real_getitem(self, name)

    monkeypatch.setattr(Repo, "__getitem__", broken_getitem)

    assert store.commit_times([revision]) == {}


def test_list_dashboards_answers_empty_if_head_is_pruned_mid_read(store, monkeypatch):
    """Same race, HEAD's own tree instead of a revision's commit_time -
    see decision 24. Answers the same as no HEAD at all."""
    store.write_snapshot("home", "a: 1\n", "first")
    head = store.resolve("HEAD")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: head)
    )
    real_getitem = Repo.__getitem__

    def broken_getitem(self, name):
        if name == head.encode():
            raise KeyError(name)
        return real_getitem(self, name)

    monkeypatch.setattr(Repo, "__getitem__", broken_getitem)

    assert store.list_dashboards() == []


def test_survey_answers_empty_if_head_is_pruned_mid_read(store, monkeypatch):
    """Same race as `list_dashboards`, in `survey`'s own HEAD-tree
    access - the one before its already-guarded blob-reading loop.
    `_revision_index` is faked to a minimal, valid, empty index so
    this reaches the exact line under test without depending on what
    dulwich's walker touches internally while building a real one. See
    decision 24."""
    store.write_snapshot("home", "a: 1\n", "first")
    head = store.resolve("HEAD")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: head)
    )
    fake_index = RevisionIndex(head, {}, {}, set(), {})
    monkeypatch.setattr(HistoryStore, "_revision_index", lambda self, repo: fake_index)
    real_getitem = Repo.__getitem__

    def broken_getitem(self, name):
        if name == head.encode():
            raise KeyError(name)
        return real_getitem(self, name)

    monkeypatch.setattr(Repo, "__getitem__", broken_getitem)

    survey = store.survey()
    assert survey.names == []
    assert survey.live == set()


def test_previous_change_answers_none_if_pruned_mid_walk(store, monkeypatch):
    """`previous_change`'s walk branch (an unindexed revision) consumes
    a dulwich `Walker`, which can raise `MissingCommitError` - not a
    `KeyError` - if an object it needs vanishes mid-walk. See decision
    24. Answers `None`, exactly like a revision that is not a change of
    this dashboard at all.

    `_revision_index` is faked to `None` ("index not ready") so
    `previous_change` falls through to its walk branch unconditionally,
    instead of needing a real rewritten-history fixture to construct a
    revision genuinely outside the index's reach.
    """
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    monkeypatch.setattr(
        HistoryStore, "_resolve", staticmethod(lambda repo, rev: first)
    )
    monkeypatch.setattr(HistoryStore, "_revision_index", lambda self, repo: None)

    def broken_get_walker(self, **kwargs):
        raise MissingCommitError(first.encode())

    monkeypatch.setattr(Repo, "get_walker", broken_get_walker)

    assert store.previous_change("home", first) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "test_commit_times_skips_a_revision_pruned or test_list_dashboards_answers_empty_if_head_is_pruned or test_survey_answers_empty_if_head_is_pruned or test_previous_change_answers_none_if_pruned_mid_walk" -v`

Expected: all four FAIL - each with the injected `KeyError`/`MissingCommitError` propagating out of the store method uncaught, instead of the guarded fallback.

- [ ] **Step 3: Write the minimal implementation**

In `commit_times`, replace:

```python
        repo = self._repo()
        if repo is None:
            return {}
        found: dict[str, int] = {}
        for revision in dict.fromkeys(revisions):
            resolved = self._resolve(repo, revision)
            if resolved is None:
                continue
            # `_resolve` promises a commit at the end of the search, so
            # this reaches for `commit_time` without a second guard.
            found[revision] = repo[resolved.encode()].commit_time
        return found
```

with:

```python
        repo = self._repo()
        if repo is None:
            return {}
        found: dict[str, int] = {}
        for revision in dict.fromkeys(revisions):
            resolved = self._resolve(repo, revision)
            if resolved is None:
                continue
            try:
                found[revision] = repo[resolved.encode()].commit_time
            except KeyError:
                # Resolved a moment ago, pruned by a concurrent `forget`
                # since - see decision 24. Left out, same as a revision
                # that never resolved: the docstring above already
                # promises that.
                continue
        return found
```

In `list_dashboards`, replace:

```python
        repo = self._repo()
        if repo is None:
            return []
        head = self._resolve(repo, "HEAD")
        if head is None:
            return []
        tree = repo[repo[head.encode()].tree]
        return sorted(
            entry.path.decode()[: -len(".yaml")]
            for entry in tree.items()
            if entry.path.endswith(b".yaml")
        )
```

with:

```python
        repo = self._repo()
        if repo is None:
            return []
        head = self._resolve(repo, "HEAD")
        if head is None:
            return []
        try:
            tree = repo[repo[head.encode()].tree]
        except KeyError:
            # HEAD resolved a moment ago, pruned by a concurrent
            # `forget` since - see decision 24. Same answer as having
            # no HEAD at all.
            return []
        return sorted(
            entry.path.decode()[: -len(".yaml")]
            for entry in tree.items()
            if entry.path.endswith(b".yaml")
        )
```

In `survey`, replace:

```python
        index = self._revision_index(repo)
        if index is None:
            return Survey([], set(), {})
        names, removed_meta = index.names, index.removed_meta
        tree = repo[repo[head.encode()].tree]
        live = {
```

with:

```python
        index = self._revision_index(repo)
        if index is None:
            return Survey([], set(), {})
        names, removed_meta = index.names, index.removed_meta
        try:
            tree = repo[repo[head.encode()].tree]
        except KeyError:
            # HEAD resolved a moment ago, pruned by a concurrent
            # `forget` since - see decision 24. Same answer as the
            # index-not-ready case just above.
            return Survey([], set(), {})
        live = {
```

In `previous_change`, replace:

```python
        walker = repo.get_walker(
            include=[full.encode()],
            paths=[f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()],
            max_entries=2,
        )
        found = [_as_text(entry.commit.id) for entry in walker]
        if len(found) == 2 and found[0] == full:
            return found[1]
        return None
```

with:

```python
        try:
            walker = repo.get_walker(
                include=[full.encode()],
                paths=[f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()],
                max_entries=2,
            )
            found = [_as_text(entry.commit.id) for entry in walker]
        except (KeyError, MissingCommitError):
            # `full` resolved a moment ago, pruned by a concurrent
            # `forget` since - see decision 24. Same answer as a
            # revision the walk never reaches.
            return None
        if len(found) == 2 and found[0] == full:
            return found[1]
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k "test_commit_times_skips_a_revision_pruned or test_list_dashboards_answers_empty_if_head_is_pruned or test_survey_answers_empty_if_head_is_pruned or test_previous_change_answers_none_if_pruned_mid_walk" -v`

Expected: all four PASS.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest tests/ -v`

Expected: everything passes.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Guard four single-object reads against the same forget race

commit_times, list_dashboards, survey, and previous_change each
dereference a _resolve-returned sha exactly once, right after
resolving it - the same window issue #20's fix closes for
_each_change, just narrower: one object, not a loop. commit_times's
own comment even named the assumption ("no second guard needed")
that a concurrent forget's prune between resolve and read disproves.
Each now answers exactly what it already answers for a revision that
never resolved, instead of raising.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 4: `operations.async_search` retries its whole sequence, not just the store call

**Files:**
- Modify: `custom_components/dashboard_history/operations.py`
- Test: `tests/integration/run_search_past_a_forget.py` (new)

**Interfaces:**
- Consumes: `_FORGET_RACE_RETRIES` (import from `.store`), `HistoryStore.resolve(self, revision: str) -> str | None`, `HistoryStore.forget_in_progress(self) -> bool` (both existing, public, the second new from Task 1), `HistoryStore.list_versions`, `HistoryStore.search_changes` (Task 2's propagate-when-given-versions behavior).
- Produces: `operations._retrying_a_forget_race(hass: HomeAssistant, store: HistoryStore, attempt: Callable[[], Awaitable[tuple[list, dict]]]) -> tuple[list, dict]` - new private async helper, typed concretely for its one caller rather than with a generic, matching this module's existing style. Same two-signal trust rule as `HistoryStore._retrying_a_forget_race` (Task 1): a result is only trusted if HEAD read the same both before and after the whole `attempt()` ran *and* `forget_in_progress()` is false at that point. `operations.async_search(...)` - same signature, new retry behavior.

**Why tier 3 (`docker exec`, no running instance), not tier 2 (`run_checks.py` against a live instance):** `async_search`'s retry wraps `store.list_versions`, `store.search_changes`, and `_marks_by_revision` - all pure `HistoryStore`/local functions, none of them reach into Home Assistant's live dashboard registry. The one piece of `async_search` that does (`async_get_config`, for the `same_as_live` comparison) sits *outside* the retry, unchanged, and is not what this plan is testing. Confirm this by reading `async_search`'s current body (`operations.py:507-547`) before starting - if a future edit moves `async_get_config` inside the retried sequence, this reasoning no longer holds and the test needs `run_checks.py` instead.

- [ ] **Step 1: Write the failing test**

Create `tests/integration/run_search_past_a_forget.py`:

```python
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


async def main() -> int:
    await _retries_past_a_race()
    await _retries_past_a_race_with_missing_commit_error()
    await _retries_a_successful_but_stale_attempt()
    await _retries_when_checkpoint_present_even_if_head_is_stable()
    await _propagates_when_head_did_not_move()
    print(f"\n{len(_passed)} of {len(_passed) + len(_failed)} checks passed")
    if _failed:
        print("Failed: " + ", ".join(_failed))
        return 1
    return 0


sys.exit(asyncio.run(main()))
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `docker compose -f docker/compose.yaml up -d` (if not already running), then:

`docker exec -i dashboard-history-test python3 - < tests/integration/run_search_past_a_forget.py`

Expected: the container reports an unhandled `KeyError` from inside `operations.async_search` (raised by `flaky_search_changes`'s first call, with nothing catching it) rather than `_retries_past_a_race`'s three `check(...)` lines passing - `async_search` has no retry yet, so its `mock.patch.object` block raises out of the `with` and the script crashes before ever reaching any of the other scenario functions or printing a summary. Confirm the exact traceback names `search_changes`, not something unrelated (an unrelated failure here likely means the fixture setup itself is broken, not that the test correctly failed).

- [ ] **Step 3: Write the minimal implementation**

In `operations.py`, add a new stdlib import directly after the existing `import logging` line:

```python
from collections.abc import Awaitable, Callable
```

Add a new third-party import directly after the existing `from homeassistant.util import dt as dt_util` line, matching `store.py`'s own placement of the same import:

```python
from dulwich.errors import MissingCommitError
```

Then extend the existing local import line:

```python
from .store import HistoryStore, Version
```

to:

```python
from .store import HistoryStore, Version, _FORGET_RACE_RETRIES
```

Add a new private helper directly above `async_search`:

```python
async def _retrying_a_forget_race(
    hass: HomeAssistant,
    store: HistoryStore,
    attempt: Callable[[], Awaitable[tuple[list, dict]]],
) -> tuple[list, dict]:
    """The async twin of `HistoryStore._retrying_a_forget_race`.

    Cannot reuse that one directly: each attempt here is a sequence of
    awaited executor jobs, not one synchronous call, so the retry has
    to live on this side of the sync/async boundary. Same budget, same
    two signals, same reasoning - see decision 24.

    A result is trusted - whether `attempt()` raised or returned
    normally - only if, checked right after, HEAD reads the same as it
    did when this attempt began *and* `store.forget_in_progress()` is
    false. Checking only on failure would miss a `forget` that
    completes entirely between the two separate executor jobs inside
    `attempt()` - `list_versions` then `search_changes`, across a
    guaranteed `await` point - neither individually raises, so nothing
    would trigger a retry, yet the result mixes two generations. The
    checkpoint check catches what HEAD alone cannot: a call starting
    after HEAD already moved but before notes/tags catch up sees a
    HEAD that never moves again during its own execution at all.
    """

    async def current_head() -> object:
        try:
            return await hass.async_add_executor_job(store.resolve, "HEAD")
        except (KeyError, MissingCommitError):
            return object()

    head = await current_head()
    for _ in range(_FORGET_RACE_RETRIES - 1):
        try:
            found = await attempt()
        except (KeyError, MissingCommitError):
            moved = await current_head()
            unsettled = await hass.async_add_executor_job(store.forget_in_progress)
            if moved == head and not unsettled:
                raise
            head = moved
            continue
        moved = await current_head()
        unsettled = await hass.async_add_executor_job(store.forget_in_progress)
        if moved == head and not unsettled:
            return found
        head = moved
    return await attempt()
```

Replace `async_search`:

```python
async def async_search(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    text: str,
    limit: int = 50,
) -> dict:
    """Recorded changes of one dashboard whose words hold `text`.

    Answers in the same shape as `history`, minus the cursor: a search
    result is not a page, and offering to page through one would invite
    a second search with a different answer. `more` says the limit was
    reached, so the panel can say "the first fifty" rather than "fifty".

    The longest read this integration has - the whole history - so it is
    a command of its own rather than a flag on `history`. That keeps the
    ordinary path, which the panel walks on every click, off it.

    One tag scan, not two, and that is why this does not gather the way
    `history` does. The search matches a version's title, its description
    and its number, so it wants exactly the list this wants to say which
    versions sit on the rows it hands back - and run side by side, the
    two read every tag of the dashboard twice for one answer. Read once
    here and handed down, the second scan is gone; what is left is one
    executor hop after another instead of two at once, and the walk was
    always the expensive half of the pair.

    Retried as one whole sequence - `list_versions`, `search_changes`,
    and this function's own `marks` - if a concurrent `forget` races it
    (decision 24). `store.search_changes` cannot safely retry on its
    own here: it does not own the `versions` list this function hands
    it, and this function's own `marks` is built from that same list
    outside `search_changes`'s reach. A rebuild inside `search_changes`
    alone would come back with new shas while `marks` still named the
    old ones, and every version match would fail with nothing to say
    why - so `search_changes` propagates instead, and this function
    retries everything together, re-reading `versions` fresh on every
    attempt.
    """

    async def attempt() -> tuple[list, dict]:
        versions = await hass.async_add_executor_job(store.list_versions, key)
        changes = await hass.async_add_executor_job(
            store.search_changes, key, text, limit + 1, versions
        )
        return changes, _marks_by_revision(versions)

    changes, marks = await _retrying_a_forget_race(hass, store, attempt)
    more = len(changes) > limit
    changes = changes[:limit]
    live = await async_get_config(hass, key)
    same: set[str] = set()
    if live is not None and changes:
        same = await hass.async_add_executor_job(
            _same_as_live, store, key, [c.revision for c in changes], live
        )
    return {"changes": _rendered(changes, marks, same), "more": more}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `docker exec -i dashboard-history-test python3 - < tests/integration/run_search_past_a_forget.py`

Expected: `10 of 10 checks passed` (three `check(...)` calls in `_retries_past_a_race`, two in `_retries_past_a_race_with_missing_commit_error`, two in `_retries_a_successful_but_stale_attempt`, two in `_retries_when_checkpoint_present_even_if_head_is_stable`, one in `_propagates_when_head_did_not_move` - watch the per-line output too, not only the summary count, since a summary of `10 of 10` says nothing about *which* ten passed).

- [ ] **Step 5: Run the plain pytest suite once more**

Run: `python3 -m pytest tests/ -v`

Expected: unaffected - this task touches only `operations.py`, which plain `pytest` never imports.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/operations.py tests/integration/run_search_past_a_forget.py
git commit -m "$(cat <<'EOF'
Retry async_search's whole sequence, not just search_changes

search_changes now refuses to retry itself when async_search hands
it a pre-fetched versions list (Task 2), because async_search's own
marks - built from that same list, outside search_changes's reach -
would still name the old shas after a rebuild. async_search retries
its whole sequence instead: list_versions, search_changes, and marks
together, re-reading versions fresh on every attempt.

Trusted only if HEAD read the same both before and after the whole
sequence, and no forget checkpoint is on disk - not just "nothing
raised". A forget that completes entirely across the guaranteed
await point between list_versions and search_changes never raises
anything at all: the second call simply succeeds against the new
HEAD while the first already holds the old generation. The
checkpoint check catches what HEAD alone cannot: a call starting
after HEAD already moved but before notes/tags catch up (issue #27)
sees a HEAD that never moves again during its own execution.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Self-Review Notes

Run through after all four tasks are drafted, before handing the plan off:

- **Spec coverage:** decision 24's paragraphs map onto this plan as: "kein Wiederaufsetzen mitten im Generator" -> Task 1's `_retrying_a_forget_race`; the two-signal trust rule ("Wiederholt wird, wenn HEAD sich... bewegt hat" + "Der HEAD-Vergleich allein schließt nicht jeden Fall") -> Task 1's `_current_head`/`forget_in_progress` and its success-path checks, mirrored in Task 4's async helper; the protected-HEAD-observation paragraph -> `_current_head`'s exception handling in both; the `search_changes`/`operations.async_search` ownership split -> Tasks 2 and 4; "vier weitere Stellen" -> Task 3; the forgotten-mid-read paragraph -> Task 1's `test_list_changes_returns_empty_when_the_watched_dashboard_is_forgotten_mid_read`; issue #27 is explicitly closed by this plan (Task 1's and Task 4's checkpoint-based tests), not deferred; the issue #26 paragraph remains explicitly out of scope, confirmed by the "Out of scope" section above.
- **Type/signature consistency:** `_each_change`'s new `repo` parameter is used identically in Task 1 (`list_changes`) and Task 2 (`search_changes`) - both open `repo = self._repo()` themselves before calling it, guarding `None` the same way. `_FORGET_RACE_RETRIES` is defined once (Task 1) and consumed by both `HistoryStore._retrying_a_forget_race` (Task 1) and `operations._retrying_a_forget_race` (Task 4) via import - if Task 4 is implemented before Task 1's constant exists, the import fails immediately and loudly, which is the correct failure mode for an implementer executing tasks out of order without having finished a dependency. `forget_in_progress` is defined once (Task 1, public) and consumed by Task 4 across the module boundary, never by reaching for `_checkpoint_path` directly from `operations.py`.
- **No placeholders:** every step above shows the full method body being added or replaced, not a paraphrase - confirmed by re-reading each step once more before saving this plan.
- **This plan's own revision history:** two review rounds after the plan was first written found real gaps - a test-fixture ordering bug that made one assertion a false positive, a red-suite window between Task 1 and Task 2's commits, a wrong expected check count, missing type annotations, unprotected `_resolve("HEAD")` calls inside the retry helpers themselves, and - the largest - that gating retries on an exception alone misses a `forget` that completes silently between two separate reads. All are fixed inline above; nothing here is theoretical residue left for the implementer to rediscover.
