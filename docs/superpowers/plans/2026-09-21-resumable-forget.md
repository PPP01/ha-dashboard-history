# Resumable `forget` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make an interrupted `forget` self-repairing — a process killed between its ref-rewrite steps must not report the dashboard "gone, nothing to repair" while leaving another dashboard's notes or tags stale, and the repair itself must never risk rolling HEAD back over history written after the crash, or racing anything else that might be touching the same repository.

**Architecture:** `_forget` already computes everything it needs before touching any ref. It now also writes those final target values (branch tip, note mapping, tag mapping, plus the key) to a small JSON checkpoint at `.git/dashboard_history_forget.json` before the first ref moves, and finishes through a new `_finish_forget` that both the normal path and a repair path share. Every write method refuses outright while that checkpoint file exists — on every call, not once per process — so nothing can advance HEAD, notes or tags between a crash and the next repair. The repair itself (`repair_pending_forget`) runs from Home Assistant's existing background task, ahead of the opening pass, never from the awaited `store.ensure()`. Underneath all of this, every `HistoryStore` for the same repository path — across reloads, not just within one instance — now shares one lock, not one each; that is what makes it safe for a repair to run every single time `_async_open` does (including every reload) without a separate "only the first time" gate, and what makes a comprehensive sweep for stale object-store locks (also folded into the repair step, also off the awaited start) safe again after a narrower, per-write retry was found unsafe.

**Tech Stack:** Python 3, `dulwich` 1.2.14 (pinned), plain `pytest` for `store.py` (one of the seven Home-Assistant-free modules).

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, decision 21, all five numbered corrections plus the "Nicht übernommen" paragraph. This plan implements that decision, revised twice now: a first external review against the plan's first draft found a reload race and a false startup-cost claim (corrections 3 and part of 2's fix); a second review, against the plan that followed from the first, found that the fixes for *those* findings were themselves incomplete — no two `HistoryStore` instances for the same path ever shared a lock, so a process-wide "first attempt only" gate could not actually prevent a repair from racing a live, ordinary `forget` on a different instance, and a lock cleared locally, at the point a write met it, could break a still-live writer's own rename exactly the way issue #19 already found for refs. Corrections 4 and 5 are the result. Where this plan and the spec disagree on a point neither review has touched, re-read the spec — it is binding.

## Global Constraints

- No shelling out to `git`. `dulwich` only (`CLAUDE.md`, "Hard rules").
- `store.py` must not `import homeassistant`, directly or indirectly — it is one of the seven Home-Assistant-free core modules and must keep working under plain `pytest` (`CLAUDE.md`, "Hard rules").
- Blocking work belongs in an executor (`hass.async_add_executor_job`) — never call a `store.py` method that touches disk directly from an `async def` in `__init__.py` (`CLAUDE.md`, "Hard rules").
- Nothing may block Home Assistant's startup. The repair added here — including the object-lock sweep folded into it — must run from the existing background task (`_async_open` in `__init__.py`), never from the awaited `store.ensure()` call in `async_setup_entry`. Nothing added for this feature may add an unbounded-with-history-size cost to that awaited call either.
- Every write path must refuse while a `forget` checkpoint is pending, checked on every call — not gated by the once-per-process `_swept_paths` set that `_clear_stale_locks` uses.
- Every `HistoryStore` for the same resolved repository path, within one process, must share one lock — not one per instance. A reload builds a fresh instance; without a shared lock, nothing stops it from running concurrently with whatever an older instance is still doing to the same repository.
- No local, per-write "clear this one lock and retry" logic for object-store locks. `FileLocked` means the lock file exists, never that its owner is dead; clearing one out from under a still-live writer breaks that writer's own rename the same way issue #19 found for refs. Any comprehensive sweep for stale object locks relies on the shared lock above for its safety, and runs from the same background step as the repair, never from the awaited start.
- Test command: `python3 -m pytest tests/ -v`. Some cases skip visibly without `DASHBOARD_HISTORY_REAL_STORAGE`/`tests/.real-storage` — that is expected, not a failure.
- Commit message format for this repo (`CLAUDE.md`, "Git"): English, imperative subject ≤ 50 characters, blank line, body wrapped at 72 characters explaining *why*. Reference issue #22 where relevant.

---

## Files touched

| File | Role |
|---|---|
| `custom_components/dashboard_history/store.py` | All the git-facing logic: the shared per-path lock, checkpoint read/write, the write-blocking guard, `_finish_forget`, `repair_pending_forget`. HA-free — every change here must stay that way. |
| `custom_components/dashboard_history/__init__.py` | Wires `repair_pending_forget` into the existing background task, ahead of the opening pass. |
| `tests/test_store.py` | New and updated tests, plain `pytest`, no Home Assistant. |

No other file needs to change. `operations.py`, `services.py`, `websocket_api.py`, `capture.py` and `milestones.py` all call the same public `store.py` methods they call today, with the same signatures; the new refusal surfaces as an ordinary `ValueError`, which is exactly what `forget` already raises for other reasons, so nothing upstream needs new handling.

---

### Task 1: Share one lock per repository path, not one per `HistoryStore` instance

The foundation every later task in this plan relies on. `HistoryStore.__init__` gives every instance its own `threading.Lock()`. Two instances for the *same* path — the ordinary case across a reload, since a reload builds a fresh `HistoryStore` — therefore have no mutual exclusion between them at all. `_clear_stale_locks`'s own `_swept_paths` mechanism works around this for exactly one narrow operation (never resweep after the first `ensure()` call in a process), by relying on a safety argument that does not generalise: "nothing has been written by this process yet" stops being true the moment any write starts, and a repair or a lock sweep attempted later in a long-running process cannot lean on it. This task replaces the per-instance lock with one shared, module-level lock per resolved path, so any two operations on the same repository — from any two instances, in any order — genuinely exclude each other.

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (one new module-level registry and helper, one line changed in `HistoryStore.__init__`)
- Test: `tests/test_store.py` (two new tests)

**Interfaces:**
- Consumes: nothing new.
- Produces: `_lock_for(path: Path) -> threading.Lock` (module-level function) — used by `HistoryStore.__init__` here, and relied on by every later task that touches `self._lock`, most importantly Task 4's `repair_pending_forget`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, directly after `test_ensure_does_not_repeat_the_cleanup_within_one_process`:

```python
def test_two_instances_of_the_same_path_share_one_lock(tmp_path):
    """The foundation everything else in decision 21 stands on.

    `HistoryStore.__init__` used to build its own `threading.Lock()`
    per instance. A reload builds a fresh instance for the same path -
    found in review of decision 21 to mean a repair on the new instance
    could race a still-running `forget` on the old one, since neither
    shared anything with the other. Two instances of the same path must
    now get the literal same lock object; two instances of different
    paths must not.
    """
    first = HistoryStore(tmp_path / "history")
    second = HistoryStore(tmp_path / "history")
    other = HistoryStore(tmp_path / "elsewhere")

    assert first._lock is second._lock
    assert first._lock is not other._lock


def test_repair_waits_for_a_live_forget_on_another_instance(tmp_path):
    """A reload's repair must never run concurrently with a live forget.

    Proven with two real threads, not just the identity check above:
    one holds the shared lock - standing in for an in-flight `forget`
    on an old instance - the other calls `repair_pending_forget` on a
    second instance of the same path, which must block until the first
    releases it, not run alongside it.
    """
    import threading

    first = HistoryStore(tmp_path / "history")
    first.ensure()
    second = HistoryStore(tmp_path / "history")

    entered = threading.Event()
    release = threading.Event()

    def hold_the_lock():
        with first._lock:
            entered.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_the_lock)
    holder.start()
    assert entered.wait(timeout=5)

    order = []

    def try_repair():
        second.repair_pending_forget()
        order.append("repaired")

    repairer = threading.Thread(target=try_repair)
    repairer.start()
    order.append("about to release")
    release.set()
    repairer.join(timeout=5)
    holder.join(timeout=5)

    assert order == ["about to release", "repaired"]
```

Note: `test_repair_waits_for_a_live_forget_on_another_instance` calls `repair_pending_forget`, which does not exist until Task 4. Write it now anyway - it belongs conceptually with this task's other test, and its own step below says exactly when it starts passing.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py::test_two_instances_of_the_same_path_share_one_lock -v`
Expected: FAIL — `first._lock is second._lock` is false before this task.

Run: `python3 -m pytest tests/test_store.py::test_repair_waits_for_a_live_forget_on_another_instance -v`
Expected: FAIL with `AttributeError: 'HistoryStore' object has no attribute 'repair_pending_forget'`. Leave it failing for this reason until Task 4; this task's own proof is the first test together with Step 4 below.

- [ ] **Step 3: Write the minimal implementation**

In `store.py`, add a module-level registry directly after `_swept_paths` (which it sits beside conceptually, though its lifecycle is different - see the comment):

```python
# Locks shared by every `HistoryStore` for the same resolved path within
# this process - not one lock per instance. A reload builds a fresh
# instance with what would otherwise be its own, unrelated lock, and
# nothing then stops it from running concurrently with whatever an
# older instance is still doing to the same repository. `_swept_paths`
# above solves a related-looking problem for a different operation by
# never repeating it after the first attempt in a process - that works
# there because repeating the lock sweep has no value once it has
# happened once. A repair does not have that property: a checkpoint can
# genuinely appear later in a long-running process, from a real, new
# crash, and must stay safe to repair when it does. A lock shared
# across instances, not a "done once" marker, is what that needs.
_locks_by_path: dict[str, threading.Lock] = {}
_locks_registry_guard = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _locks_registry_guard:
        if key not in _locks_by_path:
            _locks_by_path[key] = threading.Lock()
        return _locks_by_path[key]
```

Then change `HistoryStore.__init__` from:

```python
    def __init__(self, path) -> None:
        self.path = Path(path)
        # dulwich takes an exclusive lock on the git index while it writes.
        # Two dashboards saved in the same moment run in two executor
        # threads; measured, eight parallel commits let exactly one through
        # and the other seven raised FileLocked. Writes are serialised here
        # rather than left to chance.
        self._lock = threading.Lock()
```

to:

```python
    def __init__(self, path) -> None:
        self.path = Path(path)
        # dulwich takes an exclusive lock on the git index while it writes.
        # Two dashboards saved in the same moment run in two executor
        # threads; measured, eight parallel commits let exactly one through
        # and the other seven raised FileLocked. Writes are serialised here
        # rather than left to chance - and, since decision 21, shared with
        # every other `HistoryStore` for this same path in this process,
        # not held by this instance alone: see `_lock_for`.
        self._lock = _lock_for(self.path)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py::test_two_instances_of_the_same_path_share_one_lock -v`
Expected: PASS.

Run: `python3 -m pytest tests/test_store.py -v`
Expected: PASS, all of them except `test_repair_waits_for_a_live_forget_on_another_instance`, which still fails on `AttributeError` until Task 4 - confirm it is the *only* failure, and that the failure is that one `AttributeError`, not something this task broke. In particular `test_ensure_does_not_repeat_the_cleanup_within_one_process` must still pass: it builds two instances of the same path but only ever uses them sequentially, never holding one's lock while touching the other, so sharing the lock object does not change its outcome.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Share one lock per repository path, not one per instance

HistoryStore gave every instance its own threading.Lock, so a reload
- which builds a fresh instance for the same path - shared no lock
at all with whatever the old instance was still doing. _swept_paths
already works around an analogous gap for the lock sweep, but only
because that operation has no value in repeating; a repair does not
have that property and needs real, ongoing mutual exclusion instead
(found in review of decision 21, correction 4).
EOF
)"
```

---

### Task 2: Refuse to write while a `forget` checkpoint is pending

The core of decision 21's first correction. Every public write method gets a cheap guard, checked on every call: if `.git/dashboard_history_forget.json` exists, refuse. This has to run unconditionally (not gated the way `_clear_stale_locks` is) because the danger it prevents — something else advancing HEAD, notes or tags between a crash and the next repair — can happen at any time in a process that keeps running after `forget` raises, not just once at startup.

The checkpoint doesn't exist yet as a real artifact (Task 3 introduces the code that writes one), so this task's tests create it by hand with `Path.write_text`. The guard only checks *existence*, never *content*, so this is a faithful test of the mechanism on its own.

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (new constant near line 42, two new methods near `_clear_stale_locks`, one line added to each of `write_snapshot`, `mark_deleted`, `create_version`, `retitle_version`, `remove_version`, `set_description`, `forget`)
- Test: `tests/test_store.py` (new test)

**Interfaces:**
- Consumes: nothing new.
- Produces: `HistoryStore._checkpoint_path(self) -> Path` and `HistoryStore._refuse_if_forget_pending(self) -> None`, both used by Task 3's `_forget`/`_finish_forget` and Task 4's `repair_pending_forget`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_store.py`, after the existing `forget`-related tests (near `test_forgetting_reports_a_lock_hit_after_head_already_moved`):

```python
def test_writes_refuse_while_a_forget_checkpoint_is_pending(store):
    """Every write path must see a pending checkpoint the same way.

    Decision 21, correction 1: replaying a stale checkpoint after
    something else wrote in the meantime could roll HEAD back over that
    write, or drop a note it added. The guard has to run on every call,
    not once per process, so nothing can slip in between a crash and the
    next restart's repair. The checkpoint's *content* doesn't matter
    here - only that the file exists - so it is faked by hand; Task 3
    is what makes `forget` write a real one.
    """
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Home", "", first)
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="forget"):
        store.write_snapshot("home", "a: 2\n", "second")
    with pytest.raises(ValueError, match="forget"):
        store.mark_deleted("home", "gone")
    with pytest.raises(ValueError, match="forget"):
        store.create_version("home/v1.0.1", "Home", "", first)
    with pytest.raises(ValueError, match="forget"):
        store.retitle_version("home", "home/v1.0.0", "New title", "")
    with pytest.raises(ValueError, match="forget"):
        store.remove_version("home", "home/v1.0.0")
    with pytest.raises(ValueError, match="forget"):
        store.set_description(first, "a note")
    with pytest.raises(ValueError, match="forget"):
        store.forget("home")

    # Reads are unaffected - only writes are blocked.
    assert store.list_changes("home") != []
    assert store.read_at("home", "HEAD") == "a: 1\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_store.py::test_writes_refuse_while_a_forget_checkpoint_is_pending -v`
Expected: FAIL — the first `pytest.raises` block fails because `write_snapshot` succeeds instead of raising.

- [ ] **Step 3: Write the minimal implementation**

In `store.py`, add the constant right after `_IDENTITY` (line 42):

```python
_IDENTITY = b"Dashboard History <dashboard-history@localhost>"

# The name of the file `forget` leaves behind, inside `.git`, while one
# of its ref-rewrite steps is still outstanding - see decision 21. Every
# write method checks for it before doing anything; `forget` itself
# checks it too, so a crashed attempt cannot be stomped on by a second
# one before a restart gets to repair it.
_FORGET_CHECKPOINT_NAME = "dashboard_history_forget.json"
```

Add two methods to `HistoryStore`, directly after `_clear_stale_locks` (after line 506, before `_file_for`):

```python
    def _checkpoint_path(self) -> Path:
        return self.path / ".git" / _FORGET_CHECKPOINT_NAME

    def _refuse_if_forget_pending(self) -> None:
        """Refuse to write while an earlier `forget` is still unfinished.

        Checked on every call, not once per process the way
        `_clear_stale_locks` is: the checkpoint can sit unrepaired for as
        long as nobody restarts Home Assistant, and every write in that
        window is a chance to advance HEAD, notes or tags past what the
        checkpoint expects - which a later repair would then either
        overwrite or leave stale, either way silently. Refusing costs
        nothing to be wrong about: a paused recording is recoverable, a
        repair that undid somebody else's save is not. See decision 21,
        correction 1.
        """
        if self._checkpoint_path().exists():
            raise ValueError(
                "Dashboard History cannot write right now: an earlier "
                "forget did not finish and left a checkpoint behind "
                f"({self._checkpoint_path()}). Restart Home Assistant - "
                "the interrupted rewrite finishes automatically before "
                "recording resumes."
            )
```

Then add one call to `self._refuse_if_forget_pending()` in each of these seven methods, right after the point where each already acquires `self._lock` and (where it has one) calls `self._ensure()`:

In `write_snapshot` (currently line 552-554):

```python
        with self._lock:
            self._ensure()
            self._refuse_if_forget_pending()
            target = self._file_for(key)
```

In `mark_deleted` (currently line 618-620):

```python
        with self._lock:
            self._ensure()
            self._refuse_if_forget_pending()
            if self.read_at(key, "HEAD") is None:
```

In `create_version` (currently line 639-641):

```python
        with self._lock:
            self._ensure()
            self._refuse_if_forget_pending()
            self._create_version(name, title, description, revision)
```

In `retitle_version`, right after the existing comment that explains why there is no `_ensure()` call here (currently lines 730-736):

```python
        with self._lock:
            # No `_ensure()`, unlike every other write here. This one can
            # only ever change something that already exists, so a
            # repository that is not there is an answer and not a state
            # to be built: creating one to then report "no such version"
            # would leave a history behind that nobody asked for.
            self._refuse_if_forget_pending()
            repo = self._repo()
            ref, old = self._tag_at_locked(repo, key, name)
```

In `remove_version` (currently lines 898-900):

```python
        with self._lock:
            self._refuse_if_forget_pending()
            repo = self._repo()
            ref, target = self._tag_at_locked(repo, key, name)
```

In `set_description` (currently lines 978-981):

```python
        with self._lock:
            self._ensure()
            self._refuse_if_forget_pending()
            repo = self._repo()
            if repo is None:
                return False
```

In `forget` (currently lines 1052-1059), where it matters most: before the `key not in list_all_dashboards()` check, because a pending checkpoint from an *earlier* forget may already have removed `key` from HEAD, and this must not be mistaken for "there's nothing to forget":

```python
        with self._lock:
            repo = self._repo()
            if repo is None:
                return 0
            self._refuse_if_forget_pending()
            if self._resolve(repo, "HEAD") is None:
                return 0
            if key not in set(self.list_all_dashboards()):
                return 0
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: PASS, all of them — this task only adds a new refusal path; nothing that could already succeed should now fail (no test creates a file named `dashboard_history_forget.json` except the new one).

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Refuse every write while a forget checkpoint is pending

An interrupted forget's ref-rewrite is only safe to finish later if
nothing else changed HEAD, notes or tags in the meantime - replaying
a stale plan over newer, unrelated history would roll it back
(decision 21, correction 1, found in review of the fix for #22). The
checkpoint this guards against does not exist yet; that lands in the
next commit.
EOF
)"
```

---

### Task 3: `_forget` checkpoints its plan and finishes through a shared method

This is the structural core. `_forget` already computes, before touching any ref, everything the three rewrite steps need — the rewalk that produces `nearest`/`kept`. This task makes it also compute the *final* target values for HEAD, notes and tags, write them to the checkpoint file Task 2's guard watches for, and finish through a new `_finish_forget` that a later repair (Task 4) will call with the same arguments read back from disk.

Splitting `_rewrite_tags` matters here: today it both decides the final `{ref: sha}` mapping *and* applies it in one call. The decided mapping is exactly what gets checkpointed, and the tag *objects* it creates along the way are already written to the object store by the time `_forget` reaches this point - durable enough to survive this process dying, since that write is an atomic rename, though not a promise against a full power loss, since neither that rename nor `_write_file` (used for the checkpoint itself) calls `fsync`. Either way, a later repair never needs to recreate those objects, only replay `add_packed_refs` with the same mapping. `_rewrite_notes` is restructured the same way: it now takes the already-flattened `{new_sha: text}` mapping instead of `(notes, kept)`, so the exact same call works whether it is the first attempt or a repair.

Object writes here (`repo.object_store.add_object`) stay exactly as they are today - a plain call, no local lock-clearing wrapper. An earlier version of this task added one; a review found it unsafe (`FileLocked` means the lock file exists, never that its writer is dead - clearing it out from under a still-live one breaks that writer's own rename) and incomplete (`_tree_without` writes two more objects the wrapper never touched). Decision 21's correction 5 handles stale object locks a different way entirely, in Task 4.

**Files:**
- Modify: `custom_components/dashboard_history/store.py:1006-1435` (`forget`, `_forget`, `_rewrite_notes`, `_rewrite_tags`, plus two new checkpoint methods)
- Test: `tests/test_store.py` (two new tests; every existing `forget`-related test must keep passing unchanged — that is this task's regression proof)

**Interfaces:**
- Consumes: `HistoryStore._checkpoint_path(self) -> Path` (Task 2).
- Produces:
  - `HistoryStore._write_checkpoint(self, key: str, head: bytes | None, notes: dict[bytes, bytes], tags: dict[bytes, bytes | None]) -> None`
  - `HistoryStore._read_checkpoint(self) -> tuple[str, bytes | None, dict[bytes, bytes], dict[bytes, bytes | None]] | None`
  - `HistoryStore._finish_forget(self, repo: Repo, key: str, head: bytes | None, notes: dict[bytes, bytes], tags: dict[bytes, bytes | None], say: _Progress) -> None` — used directly by Task 4's `repair_pending_forget`.
  - `HistoryStore._planned_tag_changes(repo: Repo, versions: list, nearest: dict[bytes, bytes | None], tag_class, key: str) -> dict[bytes, bytes | None]` (staticmethod)
  - `HistoryStore._rewrite_tags(repo: Repo, changed: dict[bytes, bytes | None]) -> None` (staticmethod, narrower signature than today)
  - `HistoryStore._rewrite_notes(self, repo: Repo, targets: dict[bytes, bytes]) -> None` (narrower signature than today)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, after `test_forgetting_removes_the_dashboard_from_the_history`:

```python
def test_forget_leaves_no_checkpoint_behind(store):
    """A normal, uninterrupted forget must clean up after itself.

    Decision 21: the checkpoint is only meant to outlive `forget` when
    something interrupted it. `_finish_forget` deletes it as its very
    last step, so an ordinary run - the overwhelming majority of them -
    must never leave it lying around.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    store.forget("gone")

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    assert not checkpoint.exists()


def test_forget_writes_a_checkpoint_before_the_first_ref_moves(store, monkeypatch):
    """A real interruption must leave a real, usable checkpoint behind.

    `test_forget_leaves_no_checkpoint_behind` alone cannot catch a
    missing `_write_checkpoint` call: it only checks the file is gone
    *after* a normal run, which holds whether or not one was ever
    written in between. A review of this plan's first draft found that
    exact gap. This interrupts a real `forget()` call instead of
    building a checkpoint by hand, and reads back what it actually left
    on disk.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def boom(self, repo, notes):
        raise RuntimeError("simulated crash between _point_head and _rewrite_notes")

    monkeypatch.setattr(HistoryStore, "_rewrite_notes", boom)

    with pytest.raises(RuntimeError):
        store.forget("gone")

    key, head, notes, tags = store._read_checkpoint()
    assert key == "gone"
    assert head is not None
    assert "gone" not in store.list_all_dashboards()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py::test_forget_writes_a_checkpoint_before_the_first_ref_moves -v`
Expected: FAIL with `AttributeError: 'HistoryStore' object has no attribute '_read_checkpoint'`.

`test_forget_leaves_no_checkpoint_behind` passes vacuously before this task (nothing writes a checkpoint yet, so none is ever left behind either) — that is exactly the gap the second test above exists to close; treat Step 4's full run, including both tests together, as the real proof, not this one test's pass/fail on its own.

- [ ] **Step 3: Write the implementation**

In `store.py`, add two checkpoint helpers directly after `_refuse_if_forget_pending` (from Task 2), before `_file_for`:

```python
    def _write_checkpoint(
        self,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
    ) -> None:
        """Save what `forget` is about to finish, before any ref moves.

        Four fields, not three: `key` has to be in here too, because
        `_drop_from_index` needs it and nothing else remembers which
        dashboard was being forgotten once a crash has happened. Written
        through `_write_file`'s temp-then-`os.replace` so an interrupted
        write of the checkpoint itself is never mistaken for a valid one
        - see decision 21.
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
        }
        self._write_file(self._checkpoint_path(), json.dumps(payload))

    def _read_checkpoint(
        self,
    ) -> tuple[str, bytes | None, dict[bytes, bytes], dict[bytes, bytes | None]] | None:
        """The inverse of `_write_checkpoint`, or `None` if there is none."""
        path = self._checkpoint_path()
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        head = payload["head"].encode() if payload["head"] is not None else None
        notes = {
            sha.encode(): text.encode("utf-8") for sha, text in payload["notes"].items()
        }
        tags = {
            ref.encode("utf-8", "surrogateescape"): (
                sha.encode() if sha is not None else None
            )
            for ref, sha in payload["tags"].items()
        }
        return payload["key"], head, notes, tags
```

Add `import json` to the top-of-file imports (after `import logging`, alphabetically before `import os`):

```python
import json
import logging
import os
```

Change `_rewrite_notes` from:

```python
    def _rewrite_notes(
        self, repo: Repo, notes: dict[str, str], kept: dict[bytes, bytes]
    ) -> None:
        """Put the descriptions back on the commits that survived."""
        if b"refs/notes/commits" in repo.refs:
            del repo.refs[b"refs/notes/commits"]
        for old, text in notes.items():
            new = kept.get(old.encode())
            if new is None:
                continue  # its commit is gone; the description goes too
            porcelain.notes_add(
                str(self.path),
                new,
                text.encode("utf-8"),
                author=_IDENTITY,
                committer=_IDENTITY,
            )
```

to:

```python
    def _rewrite_notes(self, repo: Repo, targets: dict[bytes, bytes]) -> None:
        """Put the descriptions back on the commits that survived.

        Takes the already-flattened `{new commit sha: note text}` this
        dashboard's forgetting leaves behind, rather than the raw notes
        and the old-to-new commit mapping separately - the flattening
        used to happen inline here, but decision 21 needs the flattened
        form on its own, to checkpoint it and to hand the exact same
        mapping to a later repair. Deleting the ref first and rebuilding
        it whole makes this safe to call twice: a repair that redoes this
        after a partial first attempt ends at the same content either way.
        """
        if b"refs/notes/commits" in repo.refs:
            del repo.refs[b"refs/notes/commits"]
        for new, text in targets.items():
            porcelain.notes_add(
                str(self.path),
                new,
                text,
                author=_IDENTITY,
                committer=_IDENTITY,
            )
```

Change `_rewrite_tags` from the single method that both decides and writes into two: a pure planning step and a thin apply step. Replace the whole existing method (lines 1348-1435) with:

```python
    @staticmethod
    def _planned_tag_changes(
        repo: Repo,
        versions: list,
        nearest: dict[bytes, bytes | None],
        tag_class,
        key: str,
    ) -> dict[bytes, bytes | None]:
        """Decide the final `{ref: sha or None}` this dashboard's tags need.

        The dashboard's own versions go with it. Since decision 13 of the
        design record a version belongs to one dashboard and is named
        `<key>/v<major>.<minor>.<patch>`, so every tag under `<key>/` is
        forgotten here rather than moved. Moving it was right while a
        version marked a moment of the whole history; measured after
        decision 13 it left `gone/v1.0.0` sitting on another dashboard's
        commit, `read_at` answering None for it, and the numbering for a
        future `gone` counting up from a version nobody can reach.

        Every other tag keeps the old behaviour: rebuilt with its original
        message and time, moved to the nearest surviving ancestor when its
        own commit disappears. A lightweight tag has no object to rebuild
        - the ref *is* the tag - so it is re-pointed instead. Inventing a
        tag object for it would hand somebody back a different kind of tag
        than the one they made.

        Stops short of writing the result anywhere: the new tag *objects*
        this creates for annotated tags are written to the object store
        immediately below, since they are content-addressed and harmless
        to write early, but the returned mapping is exactly what decision
        21 checkpoints and what `_rewrite_tags` later applies in one
        `add_packed_refs` call - kept apart so a repair can replay just
        that call without recreating a single object.
        """
        changed: dict[bytes, bytes | None] = {}
        for ref, old, target in versions:
            name = b"refs/tags/" + ref
            if _owns(ref, key):
                # This dashboard's own version, forgotten with it. Since
                # decision 13 a version belongs to one dashboard, and
                # carrying it onto a surviving ancestor left `gone/v1.0.0`
                # sitting on a stranger's commit (measured 2026-09-02).
                changed[name] = None
                continue
            moved = nearest.get(target)
            if moved is None:
                changed[name] = None  # nothing left for it to mark
                continue
            if old is None:
                # A lightweight tag has no object to rebuild - the ref IS
                # the tag - so it is re-pointed. Inventing a tag object
                # would hand somebody back a different kind than the one
                # they made.
                changed[name] = moved
                continue
            fresh = tag_class()
            fresh.object = (old.object[0], moved)
            fresh.name = old.name
            fresh.message = old.message
            fresh.tagger = old.tagger
            fresh.tag_time = old.tag_time
            fresh.tag_timezone = old.tag_timezone
            repo.object_store.add_object(fresh)
            changed[name] = fresh.id
        return changed

    @staticmethod
    def _rewrite_tags(repo: Repo, changed: dict[bytes, bytes | None]) -> None:
        """Apply a plan from `_planned_tag_changes` in one write.

        One write for all of them. `del repo.refs[...]` rewrites the
        whole `packed-refs` file and renames it into place, once per
        mark; the assignment after it writes a loose file and fsyncs
        that. Measured 2026-09-18 on the test bench with 782 packed
        marks: 11.1 ms and 5.5 ms each, 12.46 s together, against
        0.02 s for the single call below.

        `add_packed_refs` takes the whole mapping at once, and a target
        of `None` removes that ref - exactly the two things this method
        does. It also unlinks any loose ref of the same name, so both
        shapes are covered without asking which one a mark has. It also
        merges: any tag *not* named in `changed` is left exactly as it
        stood, which is what makes this safe for `repair_pending_forget`
        to replay even after other tags were created since the plan was
        made.

        Empty is not a special case for `add_packed_refs`; it returns at
        once. Said here because a repository without a single mark is
        the ordinary case for a young installation.
        """
        repo.refs.add_packed_refs(changed)
```

Change `_forget` from (the tail, starting where the rewrite loop ends):

```python
        self._point_head(repo, nearest.get(order[-1].id) if order else None)
        self._rewrite_notes(repo, notes, kept)
        self._rewrite_tags(repo, versions, nearest, Tag, key, say)
        self._drop_from_index(repo, key)

        # Rewriting refs only makes the old objects unreachable; the blobs
        # and commits stay on disk, and `resolve` still finds them. Without
        # this, "forgotten for good" would be a claim the repository
        # contradicts. The grace period is zero on purpose - the usual
        # fourteen days protect objects another writer may be building, and
        # the only other writer here is this class, holding the lock this
        # method runs under.
        from dulwich.gc import garbage_collect  # noqa: PLC0415

        # No counting here: the collection walks the object store on its
        # own and reports nothing back. A phase name without numbers is
        # still worth saying - it is a fifth of the wait.
        say("cleaning", 0, 0)
        garbage_collect(repo, prune=True, grace_period=0)

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
        # and stays visible instead of vanishing behind `ignore_errors`:
        # `forget` already renamed refs, rewrote notes and pruned objects
        # by this point, so raising here would report the whole operation
        # as failed when it had, in fact, already succeeded - and a
        # second attempt could not repair anything, since the dashboard
        # is already gone from HEAD.
        try:
            shutil.rmtree(self.path / ".git" / "logs")
        except FileNotFoundError:
            pass
        except OSError:
            _LOGGER.exception("Could not clear the reflog after forgetting %s", key)
        return removed
```

to:

```python
        head = nearest.get(order[-1].id) if order else None
        note_targets = {
            kept[old.encode()]: text.encode("utf-8")
            for old, text in notes.items()
            if kept.get(old.encode()) is not None
        }
        tag_targets = self._planned_tag_changes(repo, versions, nearest, Tag, key)

        # Written before any ref moves - `_point_head` is the first of
        # the three steps below. From here on, `.git/dashboard_history_
        # forget.json` is the one true record of what this call is about
        # to finish, for this call and for any later repair alike. See
        # decision 21.
        self._write_checkpoint(key, head, note_targets, tag_targets)
        self._finish_forget(repo, key, head, note_targets, tag_targets, say)
        return removed

    def _finish_forget(
        self,
        repo: Repo,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
        say: _Progress,
    ) -> None:
        """Move every ref to its planned target, then clean up.

        Shared by the call that just computed `head`/`notes`/`tags` and
        by `repair_pending_forget`, which reads the same three values
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
        """
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
        # method runs under.
        from dulwich.gc import garbage_collect  # noqa: PLC0415

        # No counting here: the collection walks the object store on its
        # own and reports nothing back. A phase name without numbers is
        # still worth saying - it is a fifth of the wait.
        say("cleaning", 0, 0)
        garbage_collect(repo, prune=True, grace_period=0)

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

Note that `say` is no longer threaded through `_planned_tag_changes`/`_rewrite_tags` (it was already unused there before this change, by the old method's own admission — this refactor is a natural moment to drop it, since the signature is already being narrowed for the checkpoint split).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -v`

Expected: PASS, all of them, including every existing test with `forget` in its name (`test_forgetting_removes_the_dashboard_from_the_history`, `test_forgetting_leaves_another_dashboard_whole`, `test_forgetting_removes_the_metadata_too`, `test_forgetting_clears_the_reflog_that_still_named_it`, `test_forgetting_reports_a_reflog_it_could_not_clear`, `test_forgetting_an_unknown_dashboard_changes_nothing`, `test_forgetting_the_only_dashboard_empties_the_history`, `test_forgetting_is_refused_for_nothing_and_survives_an_empty_repo`, `test_the_forgotten_text_is_gone_from_the_object_store`, `test_forgetting_a_dashboard_keeps_the_versions_of_a_nested_legacy_key`, `test_forgetting_clears_the_index_and_the_working_tree_too`, `test_forgetting_a_dashboard_leaves_no_stale_index_behind`, `test_forgetting_reports_its_progress`, `test_forgetting_without_a_progress_callback_still_works`, `test_forgetting_does_not_write_packed_refs_once_per_version`) and both new tests above, except `test_repair_waits_for_a_live_forget_on_another_instance` from Task 1, still failing on the same `AttributeError` until Task 4. `test_forgetting_reports_a_held_lock_plainly` and `test_forgetting_reports_a_lock_hit_after_head_already_moved` are expected to still pass too, unchanged, at this point (Task 5 is what updates their wording, not their pass/fail).

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Checkpoint forget's plan and finish through a shared method

_forget already computed every ref's final target before touching
one; it now also writes those targets - branch tip, flattened note
mapping, flattened tag mapping, and the key - to a checkpoint file
before the first ref moves, and finishes through the new
_finish_forget. That method is the piece a later repair (next
commit) replays after a crash, using the exact values a first
attempt would have used, instead of guessing from whatever ref state
happens to be left over (issue #22).
EOF
)"
```

---

### Task 4: `repair_pending_forget` — the payoff, plus the object-lock sweep decision 21's fifth correction moved here

This is what proves issue #22 is actually fixed: a `forget` interrupted mid-rewrite must, after this, correctly finish rewriting - including a note and a tag that sat on a commit the rewrite itself renames - without calling `forget` again, and without ever running concurrently with a live `forget` on another instance. It also folds in a comprehensive sweep for stale locks under `.git/objects/`, which an earlier version of this plan tried to handle with a narrow, per-write retry that a review found unsafe and incomplete (see Task 3's note). With Task 1's shared lock in place, that sweep becomes safe again for the same reason `_clear_stale_locks` already is for `refs/` and the top level - anything found while holding the lock cannot belong to a still-live writer in this process - and it belongs here, in the background step, rather than in the awaited `_ensure()`, for the same cost reason the repair itself does.

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (one new staticmethod, one new public method)
- Test: `tests/test_store.py` (three new tests, one of them already written in Task 1)

**Interfaces:**
- Consumes: `_read_checkpoint`, `_write_checkpoint`, `_finish_forget` (Task 3), `_ensure` (existing), `_Progress` (existing), the shared `self._lock` (Task 1).
- Produces: `HistoryStore.repair_pending_forget(self) -> None` — called by `__init__.py` in Task 6. `HistoryStore._clear_stale_object_locks(git_dir: Path) -> None` (staticmethod) — called only from `repair_pending_forget`.

- [ ] **Step 1: Write the failing tests**

`test_repair_waits_for_a_live_forget_on_another_instance` was already written in Task 1 and is still failing there on `AttributeError`; no change needed to it here - Step 4 below is where it starts passing.

Add to `tests/test_store.py`, after `test_forget_writes_a_checkpoint_before_the_first_ref_moves`:

```python
def test_repair_finishes_an_interrupted_forget(store, monkeypatch):
    """The exact scenario issue #22 reported, fixed end to end.

    Not a hand-built checkpoint: a real `forget("gone")` call is
    interrupted between `_rewrite_notes` and `_rewrite_tags`, on a
    dashboard whose forgetting *rewrites* another, still-living commit
    - "home"'s second save still has "gone.yaml" sitting in its tree,
    so removing "gone" gives that commit a new sha. Both a note and a
    tag sit on exactly that rewritten commit, which a checkpoint built
    from an unchanged sha could never prove correct.
    """
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

    # The crash already happened: HEAD moved to the rewritten "home"
    # commit and the note followed it, but the tag still names the
    # stale, pre-rewrite one - exactly the half-repaired state issue
    # #22 could not recover from.
    assert "gone" not in store.list_all_dashboards()
    rewritten_head = store.resolve("HEAD")
    assert rewritten_head != home_v2
    assert store.read_version("home", "home/v1.0.0").revision == home_v2
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    assert checkpoint.exists()

    monkeypatch.setattr(HistoryStore, "_rewrite_tags", real_rewrite_tags)
    store.repair_pending_forget()

    assert not checkpoint.exists()
    assert store.resolve("HEAD") == rewritten_head
    assert store.read_version("home", "home/v1.0.0").revision == rewritten_head
    assert store.descriptions() == {
        rewritten_head: "a note on the commit that gets rewritten"
    }
    assert store.write_snapshot("home", "a: 3\n", "third") is not None


def test_repair_does_nothing_when_no_checkpoint_exists(store):
    """The ordinary case - nothing to repair - must be a cheap no-op."""
    store.write_snapshot("home", "a: 1\n", "first")
    store.repair_pending_forget()
    assert store.read_at("home", "HEAD") == "a: 1\n"


def test_repair_clears_a_stale_object_lock(store):
    """A lock under objects/ left by a dead process must not survive repair.

    Decision 21, correction 5: an earlier version of this fix cleared a
    lock like this locally, right where a write met it, and a review
    found that unsafe (a live writer's own rename could break) and
    incomplete (more than one call site writes objects). Swept
    comprehensively here instead, the same way `_clear_stale_locks`
    already sweeps `refs/` and the top level, and safe for the same
    reason: nothing else in this process can be writing while
    `repair_pending_forget` holds the shared lock.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    stale_lock = store.path / ".git" / "objects" / "ab" / "cdef0123456789.lock"
    stale_lock.parent.mkdir(parents=True)
    stale_lock.touch()

    store.repair_pending_forget()

    assert not stale_lock.exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py::test_repair_finishes_an_interrupted_forget -v`
Expected: FAIL with `AttributeError: 'HistoryStore' object has no attribute 'repair_pending_forget'`.

Run: `python3 -m pytest tests/test_store.py::test_repair_clears_a_stale_object_lock -v`
Expected: FAIL the same way.

- [ ] **Step 3: Write the minimal implementation**

Add a new staticmethod to `HistoryStore`, directly after `_clear_stale_locks`, before `_checkpoint_path` (from Task 2):

```python
    @staticmethod
    def _clear_stale_object_locks(git_dir: Path) -> None:
        """Remove `.lock` files under `objects/` left by a dead process.

        Kept apart from `_clear_stale_locks` (issue #19, `refs/` and the
        top level) because it relies on a different safety argument.
        `_clear_stale_locks` may run only once, at the very first
        `ensure()` call in a process, before that process has written
        anything - the one moment a lock's owner can be assumed dead
        without more to go on. This sweep instead relies on the shared,
        per-path lock `repair_pending_forget` holds while calling it
        (decision 21, correction 4): while that lock is held, nothing
        else in this process can be concurrently writing to this
        repository, so any lock found here is provably not a live
        writer's - a dead, earlier process, or an earlier attempt in
        this same process that already released the lock without
        cleaning up after itself. Safe to repeat on every call, unlike
        `_clear_stale_locks`.

        A first version of this fix cleared a lock like this locally,
        at the one write it would block, and retried that write once -
        a review found that unsafe without this argument (`FileLocked`
        means the lock file exists, never that its owner is dead) and
        incomplete (`_tree_without` writes two more objects a narrow,
        per-call-site fix would have missed). See decision 21,
        correction 5.
        """
        objects_dir = git_dir / "objects"
        if not objects_dir.is_dir():
            return
        for lock in objects_dir.rglob("*.lock"):
            lock.unlink(missing_ok=True)
            _LOGGER.warning(
                "Removed stale object lock left by an interrupted git "
                "operation: %s",
                lock,
            )
```

Add a new method to `HistoryStore`, directly after `forget` (after its closing `except FileLocked` block, before `_forget`):

```python
    def repair_pending_forget(self) -> None:
        """Finish an interrupted `forget`, if one was left behind.

        Meant to be called from Home Assistant's background task ahead
        of the opening pass - never from the awaited `store.ensure` call
        in `async_setup_entry`, since this can cost several seconds
        (`garbage_collect` alone measured 4.5-6.6 s on the test bench,
        and the object-lock sweep below costs time proportional to the
        whole history's size) and nothing in that awaited path may cost
        Home Assistant's start. See decision 21, corrections 3 and 5.

        No "first attempt only" gate: `self._lock` is shared by every
        `HistoryStore` for this path within this process (decision 21,
        correction 4), so a second call - from a reload's fresh
        instance, or from this same one - simply waits for an earlier
        one to finish instead of racing it, and finds either a
        genuinely new checkpoint to repair or nothing left to do. Safe
        to call as many times as this runs, not just the first.
        """
        with self._lock:
            self._ensure()
            git_dir = self.path / ".git"
            if git_dir.exists():
                self._clear_stale_object_locks(git_dir)
            checkpoint = self._read_checkpoint()
            if checkpoint is None:
                return
            key, head, notes, tags = checkpoint
            repo = self._repo()
            if repo is None:
                return
            self._index = None
            self._survey = None
            self._finish_forget(repo, key, head, notes, tags, _Progress(None))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k repair -v`
Expected: PASS, all four (this task's three, plus Task 1's `test_repair_waits_for_a_live_forget_on_another_instance`, now that `repair_pending_forget` exists).

Then run the full suite once more: `python3 -m pytest tests/ -v` — expected PASS (or visible skips only), confirming nothing in this task disturbed Tasks 1-3's work.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Add repair_pending_forget to finish an interrupted rewrite

Reads the checkpoint _forget now writes before touching any ref and
replays _finish_forget with its exact values - the same method a
normal, uninterrupted forget already uses. Proven against a real
interrupted forget, not a hand-built checkpoint, on a commit that
the rewrite itself renames, carrying both a note and a tag through
correctly (issue #22).

Also sweeps stale locks under objects/, comprehensively rather than
at each write site - a first attempt at the latter was found unsafe
and incomplete (decision 21, correction 5). Both this and the repair
itself rely on the shared per-path lock from the earlier commit for
their safety, so neither needs its own "first attempt only" gate:
a second call waits instead of racing.

Not yet called from anywhere Home Assistant reaches - that is the
next commit.
EOF
)"
```

---

### Task 5: `forget()` refuses to start over a pending checkpoint; the `FileLocked` messages promise only what can be kept

Two related fixes to `forget()`'s own exception handling. First: `forget()` must not let a *second* call start computing a brand new checkpoint while an earlier one is still unresolved — Task 2's guard already covers this, checked at the very top of `forget`, before the "nothing to forget" early returns; this task strengthens the regression test for that placement. Second: the two `FileLocked` messages need to say only what is actually true. A lock met while *preparing* rewritten objects - before `_write_checkpoint` ever runs - means nothing was remembered to finish automatically, and nothing in this plan clears that specific lock synchronously any more (Task 4's sweep only runs from the background repair step); only a lock met at or after `_point_head` can honestly promise that a restart finishes the job by itself.

**Files:**
- Modify: `custom_components/dashboard_history/store.py:1071-1110` (the `except FileLocked` block in `forget`)
- Test: `tests/test_store.py` (update two existing tests, add two new ones)

**Interfaces:**
- Consumes: `_refuse_if_forget_pending`, `_checkpoint_path` (Task 2, already wired into `forget` by that task).
- Produces: no new methods - message text only.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, after `test_forgetting_reports_a_lock_hit_after_head_already_moved`:

```python
def test_a_second_forget_refuses_while_the_first_is_still_pending(store):
    """A crashed forget's checkpoint must not be stomped on by another.

    Decision 21: two forgets racing to write the same checkpoint file
    would let the second one's plan silently replace the first's,
    losing whatever the first one was going to finish. Task 2's guard
    - checked at the very top of `forget`, before anything else - is
    what prevents this.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "other first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="forget"):
        store.forget("other")

    assert checkpoint.read_text(encoding="utf-8") == "{}"


def test_forget_on_the_checkpoints_own_key_still_refuses(store):
    """Guards the exact issue #22 regression, not just an unrelated one.

    The test above, forgetting a dashboard that is still plainly
    present, cannot tell a correctly-placed guard from one placed
    *after* the "nothing to forget" early returns: `other` being
    present means both placements reach the guard anyway. A guard
    placed after those returns would instead let `forget` on the
    *checkpoint's own key* silently report 0 - because that key
    already looks exactly like one that was never recorded, once a
    checkpoint is pending past `_point_head`. A key that genuinely was
    never written reproduces that same appearance without needing a
    real crash to set it up.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="forget"):
        store.forget("never-written")
```

Also add, after `test_forgetting_reports_a_lock_hit_after_head_already_moved`, a case for the sub-branch that Task 5's Step 3 introduces - a lock met *before* any checkpoint exists:

```python
def test_forgetting_reports_a_lock_hit_before_any_checkpoint_exists(store, monkeypatch):
    """A lock met while preparing objects, before any checkpoint exists.

    Nothing clears an object lock synchronously any more (decision 21,
    correction 5 - only the background sweep in `repair_pending_forget`
    does, once, off the awaited start). A lock met here means nothing
    was written down to repair automatically: unlike the two lock tests
    above, a restart can only promise to clear the lock, not to finish
    the request - that has to be made again.
    """
    from dulwich.file import FileLocked
    from dulwich.object_store import DiskObjectStore

    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def always_locked(self, obj):
        raise FileLocked("stale.lock", "stale.lock")

    monkeypatch.setattr(DiskObjectStore, "add_object", always_locked)

    with pytest.raises(ValueError, match="forget") as excinfo:
        store.forget("gone")

    message = str(excinfo.value)
    assert "call forget again" in message.lower()
    assert "gone" in store.list_all_dashboards()
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    assert not checkpoint.exists()
```

- [ ] **Step 2: Run tests to verify they fail (or already pass, where noted)**

Run: `python3 -m pytest tests/test_store.py -k "second_forget or checkpoints_own_key or hit_before_any_checkpoint" -v`

Expected: `test_a_second_forget_refuses_while_the_first_is_still_pending` and `test_forget_on_the_checkpoints_own_key_still_refuses` already PASS (Task 2 wired the guard in) - confirm both pass now; they are written here because they belong conceptually with this task's other lock/checkpoint tests. `test_forgetting_reports_a_lock_hit_before_any_checkpoint_exists` FAILS - the current message does not yet contain "call forget again".

- [ ] **Step 3: Update the `FileLocked` messages**

In `store.py`, change the `except FileLocked` block in `forget` (currently):

```python
            except FileLocked as exc:
                # `ensure()` clears a lock left by a *dead* process before
                # any call can reach here - see issue #19. What can still
                # arrive is the other case: an earlier `forget` in this
                # same, still-running process left one behind without
                # crashing. `str(exc)` on the bare exception is the two
                # paths as a tuple, which was the whole of the report in
                # issue #19 - naming what happened and how to clear it
                # replaces it here rather than at every caller.
                #
                # Which sentence is true depends on *where* the lock was
                # met. `_point_head` and `_rewrite_notes` write only
                # loose refs, never `packed-refs.lock`; `_rewrite_tags`
                # is the one call that does, and it runs after both have
                # already succeeded. A lock met there means `key` is
                # already gone from HEAD - claiming the history is
                # unaffected there is the false reassurance the review
                # of the first fix found, and a repeat `forget` cannot
                # repair it: `list_all_dashboards` below no longer lists
                # `key`, so a second call returns 0 without ever
                # reaching the tags this one did not finish.
                lockfile = os.fsdecode(exc.lockfilename)
                if key in set(self.list_all_dashboards()):
                    raise ValueError(
                        "forget could not finish: a lock file from an "
                        f"earlier attempt is still in place ({lockfile}). "
                        "Nothing was written yet, so the history is "
                        "unaffected. Restart Home Assistant to clear the "
                        "lock, then try again."
                    ) from exc
                raise ValueError(
                    "forget could not finish: a lock file from an earlier "
                    f"attempt is still in place ({lockfile}), after {key} "
                    "was already removed from the history. Restarting "
                    "Home Assistant clears the lock, but running forget "
                    "again will not repair this by itself - it will find "
                    f"{key} already gone and report nothing removed, "
                    "while other dashboards' tags may still be the old "
                    "ones."
                ) from exc
```

to:

```python
            except FileLocked as exc:
                # `ensure()` clears a lock left by a *dead* process before
                # any call can reach here - see issue #19. What can still
                # arrive is the other case: an earlier `forget` in this
                # same, still-running process left one behind without
                # crashing.
                #
                # Which message applies depends on *where* the lock was
                # met, and on one more thing decision 21 added: whether a
                # checkpoint already exists. `_point_head` and
                # `_rewrite_notes` write only loose refs, never
                # `packed-refs.lock`; `_rewrite_tags` is the one call
                # that does, and it runs after both have already
                # succeeded - a lock met there always finds a checkpoint
                # already written (see `_forget`), so a restart finishes
                # the job. A lock met while preparing rewritten objects,
                # before the checkpoint exists, is different: nothing
                # clears an object lock synchronously (decision 21,
                # correction 5 - only `repair_pending_forget`'s sweep
                # does, once, from the background), so reaching here
                # means nothing was ever remembered, and a restart can
                # only promise to clear the lock eventually, not to
                # finish a request that never got far enough to be
                # written down.
                lockfile = os.fsdecode(exc.lockfilename)
                if key in set(self.list_all_dashboards()):
                    if self._checkpoint_path().exists():
                        raise ValueError(
                            "forget could not finish: a lock file from "
                            f"an earlier attempt is still in place "
                            f"({lockfile}). Nothing about {key} has "
                            "changed yet. Restart Home Assistant - the "
                            "interrupted rewrite finishes automatically "
                            "before recording resumes; nothing further "
                            "is required."
                        ) from exc
                    raise ValueError(
                        "forget could not finish: a lock file from an "
                        f"earlier attempt is still in place ({lockfile}). "
                        f"Nothing about {key} has changed yet, and "
                        "nothing was remembered to finish automatically. "
                        "Restart Home Assistant to clear the lock, then "
                        "call forget again."
                    ) from exc
                raise ValueError(
                    "forget could not finish: a lock file from an earlier "
                    f"attempt is still in place ({lockfile}), after {key} "
                    "was already removed from the history. Restart Home "
                    "Assistant - the interrupted rewrite finishes "
                    "automatically before recording resumes; nothing "
                    "further is required."
                ) from exc
```

Then update the two existing tests in `tests/test_store.py`:

Change `test_forgetting_reports_a_held_lock_plainly`'s docstring from:

```python
    """A lock left by an earlier, still-uncleared attempt gets a sentence.

    Not the raw `dulwich.file.FileLocked` - its default `str()` is the
    two paths as a bare tuple, exactly the message issue #19 was filed
    over. `ensure()` already clears a lock left by a *dead* process, so
    what reaches here is the one case it cannot: an earlier `forget` in
    this same, still-running process left one behind without crashing.
    """
```

to:

```python
    """A lock left by an earlier, still-uncleared attempt gets a sentence.

    Not the raw `dulwich.file.FileLocked` - its default `str()` is the
    two paths as a bare tuple, exactly the message issue #19 was filed
    over. `ensure()` already clears a lock left by a *dead* process, so
    what reaches here is the one case it cannot: an earlier `forget` in
    this same, still-running process left one behind without crashing.
    This lock sits at `_point_head`'s own ref, so a checkpoint already
    exists by the time it is met - decision 21 promises a real repair
    here, not just a cleared lock, and the message must still name the
    lock and say to restart.
    """
```

Change `test_forgetting_reports_a_lock_hit_after_head_already_moved`'s docstring from:

```python
    """A lock met after HEAD has already moved must not claim otherwise.

    `_point_head` and `_rewrite_notes` touch loose refs only and do not
    need `packed-refs.lock` at all; `_rewrite_tags` is what calls
    `add_packed_refs`, after both have already succeeded. A lock found
    only there means the forgotten dashboard is already gone from HEAD
    and its notes have already moved - "the history is unaffected"
    would be the exact false reassurance the review of issue #19's
    first fix found. A second `forget` cannot repair this by itself:
    `key` is no longer in `list_all_dashboards()`, so it returns 0
    without touching the tags `_rewrite_tags` never got to.
    """
```

to:

```python
    """A lock met after HEAD has already moved must not claim otherwise.

    `_point_head` and `_rewrite_notes` touch loose refs only and do not
    need `packed-refs.lock` at all; `_rewrite_tags` is what calls
    `add_packed_refs`, after both have already succeeded. A lock found
    only there means the forgotten dashboard is already gone from HEAD
    and its notes have already moved - "the history is unaffected"
    would be the exact false reassurance the review of issue #19's
    first fix found. Decision 21 made a *restart* the true remedy
    (`repair_pending_forget` replays the checkpoint `_forget` wrote
    before `_point_head` ever ran) - this test pins that the message
    still says so, still names the dashboard, and still avoids the two
    phrases that used to be the false reassurance.
    """
```

And add one assertion to that same test, next to its existing three - the earlier draft of this test only checked what the message *avoided* saying, not that it still promised the repair that decision 21 added:

```python
    assert "restart" in message.lower()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k "lock or forget" -v`
Expected: PASS. `test_forgetting_reports_a_held_lock_plainly` still passes because the new message still contains `"master.lock"`, still contains `"restart"` (case-insensitive), and still does not start with `"("`. `test_forgetting_reports_a_lock_hit_after_head_already_moved` now also asserts `"restart" in message.lower()`, which the new message satisfies. `test_forgetting_reports_a_lock_hit_before_any_checkpoint_exists` passes because that branch's message contains `"call forget again"` and no checkpoint file exists afterward.

Then the full suite once more: `python3 -m pytest tests/ -v` — expected PASS (or visible skips only).

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Promise only the repair forget's FileLocked messages can keep

Both branches used to hedge - one on "nothing was written yet", the
other on "a second forget will not fix this by itself" - because
neither the checkpoint's existence nor a reliable lock recovery
could be relied on yet. Both are true now for a lock met at or after
_point_head, when a checkpoint always already exists; a lock met
earlier, during object preparation, gets its own honest message
instead - nothing was remembered, so the request has to be made
again, not just retried by restarting.
EOF
)"
```

---

### Task 6: Wire the repair into Home Assistant's background task

The only task that touches `__init__.py`. Not directly testable under plain `pytest` (it imports `homeassistant`), so this task's verification is a careful read plus the full `store.py` suite staying green - the mechanism it calls was already proven in Task 4.

**Files:**
- Modify: `custom_components/dashboard_history/__init__.py`, the function `_async_open` (starts at line 97) and its call site inside `async_setup_entry`. Only `_async_open`'s signature and the first few lines of its body change here; the rest of the function (laying the floor, the coordinator refresh) is untouched.

**Interfaces:**
- Consumes: `HistoryStore.repair_pending_forget(self) -> None` (Task 4).
- Produces: nothing new for other files to consume.

- [ ] **Step 1: Read the current code once more, to place the new step correctly**

`_async_open` already runs two guarded steps in sequence, each with its own `try/except Exception` and `_LOGGER.exception` call: the opening pass, then laying the floor. The repair belongs *before* both. It is safe to run on every call to `_async_open`, including every reload, not because of any gate of its own, but because `repair_pending_forget` now blocks on the same shared lock any live write already uses (Task 1) instead of racing it. Task 2's write-guard means the ordering relative to the opening pass is not a correctness requirement either, only a best-effort one that avoids a flurry of "cannot write" log lines if a crashed forget is waiting to be repaired.

- [ ] **Step 2: Add the repair step**

In `__init__.py`, change the start of `_async_open` from:

```python
    try:
        await capture.async_opening_pass()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
```

to:

```python
    # First, and off the awaited start for the same reason the opening
    # pass below is: `garbage_collect` alone measured 4.5-6.6 s on the
    # test bench, and the object-lock sweep folded into this call costs
    # time proportional to the whole history's size - nothing may add
    # that to `async_setup_entry`. Safe to run on every call to
    # `_async_open`, including every reload, without a gate of its own:
    # `repair_pending_forget` blocks on the same lock a live write would
    # already be holding, rather than racing it (decision 21, correction
    # 4). Ahead of the opening pass on purpose, though not for
    # correctness - every write in store.py refuses on its own while a
    # checkpoint is pending - only so a crashed forget does not turn the
    # opening pass into a wall of refused writes in the log before it
    # gets repaired.
    try:
        await hass.async_add_executor_job(store.repair_pending_forget)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not repair an interrupted forget")

    try:
        await capture.async_opening_pass()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
```

`store` is not currently passed into `_async_open` - check its signature (`hass, entry, capture, milestones, coordinator`) and its call site in `async_setup_entry` (`entry.async_create_background_task(hass, _async_open(hass, entry, capture, milestones, coordinator), ...)`). Add it to both:

Change the `_async_open` signature from:

```python
async def _async_open(
    hass: HomeAssistant,
    entry: ConfigEntry,
    capture: HistoryCapture,
    milestones: Milestones,
    coordinator: MeasurementCoordinator,
) -> None:
```

to:

```python
async def _async_open(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: HistoryStore,
    capture: HistoryCapture,
    milestones: Milestones,
    coordinator: MeasurementCoordinator,
) -> None:
```

And change its call site from:

```python
    entry.async_create_background_task(
        hass,
        _async_open(hass, entry, capture, milestones, coordinator),
        f"{DOMAIN} opening pass",
    )
```

to:

```python
    entry.async_create_background_task(
        hass,
        _async_open(hass, entry, store, capture, milestones, coordinator),
        f"{DOMAIN} opening pass",
    )
```

- [ ] **Step 3: Verify by reading, and by the tests that can reach this indirectly**

Run: `python3 -m pytest tests/ -v`
Expected: PASS (or visible skips only) - this file is not imported by plain `pytest` (it requires `homeassistant`), so this run only confirms Tasks 1-5 are still intact; it cannot exercise this task's own change.

Read back the four touched spots (`_async_open`'s signature, its new first `try` block, and both places `_async_open(...)` is constructed) and confirm: `store` is in scope at the call site (it is created at the top of `async_setup_entry` and already stored in `hass.data[DOMAIN]`), and the new step's `try/except Exception` matches the two existing ones in shape and in never re-raising.

If a live or containerized Home Assistant is available (`docker/README.md`), `tests/integration/run_checks.py`'s existing `run_forget` check exercising a normal `forget` end to end is the regression proof at that level for an ordinary, uninterrupted `forget` - it cannot prove resumability or the shared-lock fix itself (nothing short of killing the container mid-rewrite, or a genuine concurrent reload, would), and it should not be read as doing so; those proofs are Task 1's and Task 4's unit tests.

- [ ] **Step 4: Commit**

```bash
git add custom_components/dashboard_history/__init__.py
git commit -m "$(cat <<'EOF'
Repair an interrupted forget before the opening pass starts

repair_pending_forget existed since an earlier commit but nothing
called it. Runs from the same background task the opening pass
already uses, off the awaited store.ensure path, so a repair - and
the object-lock sweep folded into it - that can cost several seconds
never adds to Home Assistant's start. Ahead of the opening pass so a
crashed forget does not turn it into a wall of refused writes in the
log, though every write already refuses safely on its own either
way. Safe to run on every reload without its own gate, because it
now blocks on the same lock a live write would already hold instead
of racing it.

Closes #22.
EOF
)"
```

---

## Self-Review

**Spec coverage** (against decision 21 and all five corrections, as revised by two rounds of external review):
- Checkpoint written before any ref moves, four fields (`key`, `head`, `notes`, `tags`) → Task 3.
- `_finish_forget` shared by the normal path and repair → Task 3, Task 4.
- Correction 1 (block every write while a checkpoint is pending, checked every call, including in `forget` itself before its own early returns) → Task 2, reinforced by Task 5's `test_forget_on_the_checkpoints_own_key_still_refuses`.
- Correction 2 (the two `FileLocked` messages depend honestly on whether a checkpoint already exists) → Task 5.
- Correction 3 (repair off the awaited start, in the existing background task) → Task 4, Task 6.
- Correction 4 (one lock shared per repository path across every `HistoryStore` instance, not one per instance) → Task 1, relied on by Task 4's `repair_pending_forget` and `_clear_stale_object_locks`, and by Task 6's note that no gate of its own is needed.
- Correction 5 (a comprehensive, safe sweep for stale object locks, folded into the background repair step rather than a local per-write retry) → Task 4.
- "Nicht übernommen" (no special resumability for a reflog-clear failure) → deliberately not built; Task 3's `_finish_forget` keeps the existing logged-and-swallowed behavior and deletes the checkpoint regardless, matching the spec's explicit decision not to change this.

**Placeholder scan:** none found - every step above has complete code, not a description of code.

**Type consistency:** `head: bytes | None`, `notes: dict[bytes, bytes]`, `tags: dict[bytes, bytes | None]` are the same three types from where `_forget` first builds them (Task 3) through `_write_checkpoint`/`_read_checkpoint` (Task 3) to `_finish_forget` (Task 3) to `repair_pending_forget` (Task 4). `_planned_tag_changes` and `_rewrite_tags` narrow to exactly the mapping type `_rewrite_tags` already used internally as `changed`, just promoted to the boundary between them. `_lock_for(path: Path) -> threading.Lock` (Task 1) is consumed only by `HistoryStore.__init__`; every later task's `self._lock` usage is unchanged in shape, only in what it now points to.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-09-21-resumable-forget.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
