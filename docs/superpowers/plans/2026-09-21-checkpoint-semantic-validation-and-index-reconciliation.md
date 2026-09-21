# Checkpoint Semantic Validation and Index Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the gaps issue #24 found in `repair_pending_forget` after Korrektur 6 shipped: a checkpoint that is well-typed but semantically wrong (an invalid sha, an illegal ref name, a key that escapes the store) must never reach `_finish_forget` and partially apply before `dulwich` rejects it, and a checkpoint that had to be discarded — for any reason, at any correction — must never leave the git index resurrecting an already-forgotten dashboard into HEAD.

**Architecture:** Two additions to `repair_pending_forget`, both under the shared per-path lock it already holds. `_validate_checkpoint_semantics` runs after `_read_checkpoint`'s existing structural check succeeds and before `_finish_forget` is ever called, using `dulwich`'s own `valid_hexsha` and `check_ref_format`, a real existence-and-type check against `repo.object_store`, and `_file_for`'s existing containment check for `key` — any failure is treated exactly like a structurally broken checkpoint (Korrektur 6): logged, deleted, `_finish_forget` never reached. `_reconcile_index_with_head` runs whenever `repair_pending_forget` finds a checkpoint file on disk at all, *before* `_read_checkpoint` gets a chance to delete it — removing any index entry whose *path* HEAD's current tree no longer has. It prefers a precise, single-dashboard cleanup (identical to what `_drop_from_index` already does) whenever the checkpoint's own `key` can still be recovered, even from an otherwise-unusable checkpoint, and falls back to a generic, whole-index sweep only when even `key` is unreadable — the only way to still close a checkpoint damaged past recognition. Only `repo.head()`'s own absence is read as "nothing is live"; a missing commit or tree object surfaces as a real failure instead of being mistaken for an empty repository.

**Tech Stack:** Python 3, `dulwich` 1.2.14 (pinned), plain `pytest` for `store.py` (one of the seven Home-Assistant-free modules).

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md`, decision 21, Korrektur 7. Read that section before starting, including its later paragraphs added after a review of this plan's first draft found three further gaps in the reconciliation piece plus one in the validation piece — this plan already reflects the reviewed design, but the spec's own account of *why* is the binding reasoning. Where this plan and Korrektur 7 disagree on a point, the spec is binding.

**Out of scope, tracked separately:** issue [#25](https://github.com/PPP01/ha-dashboard-history/issues/25) — `_finish_forget`'s `garbage_collect(prune=True, grace_period=0)` does not know about the git index and can prune a completely unrelated, staged-but-uncommitted save whenever *any* `forget`/`repair_pending_forget` completes. Found while verifying this plan, but pre-existing since Korrektur 4/5, and not something this plan's own tests exercise — every test below that needs `_finish_forget` to complete uses a scenario where nothing else is mid-save, and every test involving a staged-but-uncommitted write uses a checkpoint this plan's own validation rejects before `_finish_forget` is ever reached, by design, to keep the two concerns apart.

## Global Constraints

- No shelling out to `git`. `dulwich` only (`CLAUDE.md`, "Hard rules").
- `store.py` must not `import homeassistant`, directly or indirectly — it stays testable under plain `pytest`.
- Both new pieces run under `self._lock` inside `repair_pending_forget`, which already holds it — no new locking, and no local per-write "clear and retry" logic is reintroduced anywhere (decision 21, correction 5).
- Repair — both new pieces included — stays entirely inside the existing background-task path (`repair_pending_forget`, called from `_async_open`), never the awaited `store.ensure()` / `async_setup_entry` path (decision 21, correction 3). This plan touches only `store.py` and `tests/test_store.py`; `__init__.py` needs no change, since `repair_pending_forget`'s call site is already wired.
- Test command: `python3 -m pytest tests/ -v`. Some cases skip visibly without `DASHBOARD_HISTORY_REAL_STORAGE`/`tests/.real-storage` set — that is expected, not a failure.
- Commit message format (`CLAUDE.md`, "Git"): English, imperative subject ≤ 50 characters, blank line, body wrapped at 72 characters explaining the *why*, referencing issue #24.

---

## Files touched

| File | Role |
|---|---|
| `custom_components/dashboard_history/store.py` | `_is_valid_commit`, `_is_valid_tag_target`, `_validate_checkpoint_semantics`, `_best_effort_checkpoint_key`, `_reconcile_index_with_head`, and the extended `repair_pending_forget` that wires all five in. |
| `tests/test_store.py` | New tests, plain `pytest`, no Home Assistant. |

No other file needs to change.

---

### Task A: Reject a checkpoint whose values are well-typed but not real

Korrektur 6's `_read_checkpoint` proves the payload has the right *shape* — strings where strings belong, dicts where dicts belong. It cannot prove a string is a real git sha, a legal ref name, or a key that stays inside the store, because it has no `repo` (or `_file_for`) to check against. A checkpoint that passes that shape check but carries, say, an invalid sha in `notes` reaches `_finish_forget` today: `_rewrite_notes` deletes `refs/notes/commits` *before* writing the individual entries back, so the invalid sha's own `AssertionError` arrives only after a real, unrelated note is already gone; `_rewrite_tags` writes its mapping into `packed-refs` before an invalid ref name's `PackedRefsException` stops it, corrupting tag lookups for the whole repository; `_drop_from_index` builds a path straight from `key` with no containment check of its own, unlike every live write path. This task adds a real content check, positioned so `_finish_forget` is never reached with an unvalidated value.

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (four new methods, one extended method)
- Test: `tests/test_store.py` (five new tests)

**Interfaces:**
- Consumes: `HistoryStore._read_checkpoint`, `HistoryStore._checkpoint_path`, `HistoryStore._repo`, `HistoryStore._file_for` (all existing).
- Produces:
  - `HistoryStore._is_valid_commit(repo: Repo, sha: bytes) -> bool` (staticmethod)
  - `HistoryStore._is_valid_tag_target(repo: Repo, sha: bytes) -> bool` (staticmethod)
  - `HistoryStore._validate_checkpoint_semantics(self, repo: Repo, key: str, head: bytes | None, notes: dict[bytes, bytes], tags: dict[bytes, bytes | None]) -> None` — raises `ValueError` naming the first offending value; used by `repair_pending_forget` here and relied on by no other task.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, directly after `test_repair_leaves_checkpoint_intact_on_read_os_error`:

```python
def test_repair_rejects_a_checkpoint_with_an_invalid_head(store, caplog):
    """A well-typed but unreal `head` must never reach `_finish_forget`.

    Korrektur 6 only checks that `head` is a string or `None` - never
    that the string is a real sha. `_point_head` sets the branch ref
    to whatever it is handed; a fabricated value would leave HEAD
    pointing at nothing dulwich can resolve. Issue #24, decision 21
    correction 7.
    """
    import logging

    store.write_snapshot("home", "a: 1\n", "first")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "not-a-sha", "notes": {}, "tags": {}}',
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("head" in record.message for record in caplog.records)
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_rejects_a_checkpoint_with_an_invalid_note_sha_and_keeps_existing_notes(
    store, caplog
):
    """An invalid note sha must not cost a real, unrelated note.

    `_rewrite_notes` deletes `refs/notes/commits` whole before writing
    entries back - without this check, an invalid sha in `notes` would
    let that deletion happen and only then fail with `AssertionError`,
    taking a genuine, unrelated note down with it. Issue #24, decision
    21 correction 7.
    """
    import logging

    first = store.write_snapshot("home", "a: 1\n", "first")
    store.set_description(first, "an important, pre-existing note")
    second = store.write_snapshot("home", "a: 2\n", "second")
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "%s", '
        '"notes": {"not-a-valid-sha": "hello"}, "tags": {}}' % second,
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("notes" in record.message for record in caplog.records)
    assert store.descriptions() == {first: "an important, pre-existing note"}
    assert store.write_snapshot("home", "a: 3\n", "third") is not None


def test_repair_rejects_a_checkpoint_with_an_invalid_tag_ref_and_keeps_packed_refs_intact(
    store, caplog
):
    """An invalid ref name must never reach `add_packed_refs`.

    `_rewrite_tags` writes its whole mapping into `packed-refs` before
    an illegal ref name's `PackedRefsException` stops it - reproduced
    against real `dulwich`: the malformed name lands on disk and every
    later `list_versions()` call fails, not just for the dashboard
    being forgotten. Issue #24, decision 21 correction 7.
    """
    import logging

    revision = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "Home", "", revision)
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "%s", "notes": {}, '
        '"tags": {"refs/tags/home/v1.0.0": "%s", '
        '"refs/tags/../../etc/evil": "%s"}}' % (revision, revision, revision),
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("tags" in record.message for record in caplog.records)
    assert [v.name for v in store.list_versions()] == ["home/v1.0.0"]
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_rejects_a_checkpoint_whose_key_escapes_the_store(store, caplog):
    """A key with a path traversal must never reach `_drop_from_index`.

    `_drop_from_index` builds `f"{key}.yaml"`/`f"meta/{key}.yaml"` and
    unlinks them with no containment check of its own, unlike every
    live write path, which all go through `_file_for`. Reproduced: an
    unguarded `key` of `"../evil-marker"` resolves outside the store
    entirely. Issue #24, decision 21 correction 7.
    """
    import logging

    revision = store.write_snapshot("home", "a: 1\n", "first")
    marker = store.path.parent / "evil-marker.yaml"
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "../evil-marker", "head": "%s", "notes": {}, "tags": {}}'
        % revision,
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("key" in record.message for record in caplog.records)
    assert not marker.exists()
    assert store.write_snapshot("home", "a: 2\n", "second") is not None


def test_repair_rejects_a_checkpoint_whose_tag_value_is_not_a_commit_or_tag(
    store, caplog
):
    """A tag value must resolve to a commit or a tag object, nothing else.

    A blob or tree sha passing a plain existence check would let
    `_rewrite_tags` create a tag nothing meaningful can ever resolve -
    reproduced by pointing a tag value at a real, existing tree sha.
    Issue #24, decision 21 correction 7.
    """
    import logging

    revision = store.write_snapshot("home", "a: 1\n", "first")
    repo = store._repo()
    tree_sha = repo[revision.encode()].tree.decode()
    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "home", "head": "%s", "notes": {}, '
        '"tags": {"refs/tags/home/v1.0.0": "%s"}}' % (revision, tree_sha),
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    assert not checkpoint.exists()
    assert any("tags" in record.message for record in caplog.records)
    assert store.list_versions() == []
    assert store.write_snapshot("home", "a: 2\n", "second") is not None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "invalid_head or invalid_note_sha or invalid_tag_ref or escapes_the_store or not_a_commit_or_tag" -v`

Expected: all five FAIL. The first three fail because `repair_pending_forget` raises an unhandled exception from inside `_finish_forget` (`ValueError`/`AssertionError`/`PackedRefsException` from `dulwich`) instead of the checkpoint being cleanly rejected. The fourth fails because nothing stops `_drop_from_index` from being called with the traversal key (confirm it does not actually delete anything outside a throwaway test directory before moving on - the assertion is what proves this, not a manual check). The fifth fails because `_rewrite_tags` happily accepts the tree sha today.

- [ ] **Step 3: Write the minimal implementation**

In `store.py`, add four new methods directly after `_read_checkpoint`, before `_file_for`:

```python
    @staticmethod
    def _is_valid_commit(repo: Repo, sha: bytes) -> bool:
        """Whether `sha` is a real, existing commit in this repository."""
        from dulwich.objects import valid_hexsha  # noqa: PLC0415

        if not valid_hexsha(sha):
            return False
        try:
            return repo[sha].type_name == b"commit"
        except KeyError:
            return False

    @staticmethod
    def _is_valid_tag_target(repo: Repo, sha: bytes) -> bool:
        """Whether `sha` is a commit or a tag object.

        The only two things a tag in this repository ever points at: a
        lightweight tag directly at a commit, an annotated one at its
        own tag object. A blob or a tree sha existing is not enough -
        see decision 21, correction 7.
        """
        from dulwich.objects import valid_hexsha  # noqa: PLC0415

        if not valid_hexsha(sha):
            return False
        try:
            return repo[sha].type_name in (b"commit", b"tag")
        except KeyError:
            return False

    def _validate_checkpoint_semantics(
        self,
        repo: Repo,
        key: str,
        head: bytes | None,
        notes: dict[bytes, bytes],
        tags: dict[bytes, bytes | None],
    ) -> None:
        """Reject a checkpoint whose values look right but are not.

        `_read_checkpoint` (Korrektur 6) only proves the payload has
        the right shape - strings where strings belong, dicts where
        dicts belong. It cannot prove a string is a real sha, a legal
        ref name, or a key that stays inside the store, because it
        never has `repo` or `_file_for` to check against. A value that
        is well-typed but wrong reaches `_finish_forget` unless
        something stops it here, and letting it through is dangerous,
        not merely wrong: `_rewrite_notes` deletes `refs/notes/commits`
        before writing entries back, so an invalid sha loses a real,
        unrelated note before its own `AssertionError` is even raised;
        `_rewrite_tags` writes partially into `packed-refs` before an
        invalid ref name raises `PackedRefsException`, corrupting tag
        lookups for the whole repository, not just the dashboard being
        forgotten; `_drop_from_index` builds a path straight from
        `key` with no containment check of its own, unlike every live
        write path, which all go through `_file_for`. See decision 21,
        correction 7.

        Raises `ValueError` naming the first offending field on any
        failure; the caller treats that exactly like a checkpoint that
        failed to parse at all.
        """
        try:
            self._file_for(key)
            self._file_for(key, "meta")
        except ValueError as exc:
            raise ValueError(f"key {key!r} does not name a file in the store") from exc
        if head is not None and not self._is_valid_commit(repo, head):
            raise ValueError(f"head {head!r} is not a valid, existing commit")
        for sha in notes:
            if not self._is_valid_commit(repo, sha):
                raise ValueError(f"notes key {sha!r} is not a valid, existing commit")
        from dulwich.refs import check_ref_format  # noqa: PLC0415

        for ref, sha in tags.items():
            if not check_ref_format(ref) or not ref.startswith(b"refs/tags/"):
                raise ValueError(f"tags key {ref!r} is not a legal tag ref name")
            if sha is not None and not self._is_valid_tag_target(repo, sha):
                raise ValueError(f"tags value {sha!r} is not a valid commit or tag object")
```

Then change `repair_pending_forget` from:

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

to:

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

        A checkpoint that parses but carries an invalid sha, ref name
        or key is rejected the same way a structurally broken one is
        (decision 21, correction 7): `_validate_checkpoint_semantics`
        runs before `_finish_forget` is ever reached, so nothing here
        can apply a value `_rewrite_notes`, `_rewrite_tags` or
        `_drop_from_index` would only reject midway through a
        destructive rewrite.
        """
        with self._lock:
            self._ensure()
            git_dir = self.path / ".git"
            if git_dir.exists():
                self._clear_stale_object_locks(git_dir)
            repo = self._repo()
            if repo is None:
                return
            checkpoint = self._read_checkpoint()
            if checkpoint is None:
                return
            key, head, notes, tags = checkpoint
            try:
                self._validate_checkpoint_semantics(repo, key, head, notes, tags)
            except ValueError as exc:
                _LOGGER.exception(
                    "Removed a forget checkpoint with an invalid value: "
                    "%s. An interrupted forget could not be finished "
                    "automatically.",
                    exc,
                )
                try:
                    self._checkpoint_path().unlink(missing_ok=True)
                except OSError:
                    _LOGGER.exception(
                        "Could not remove invalid checkpoint %s",
                        self._checkpoint_path(),
                    )
                return
            self._index = None
            self._survey = None
            self._finish_forget(repo, key, head, notes, tags, _Progress(None))
```

Note that `repo = self._repo()` moves ahead of `_read_checkpoint()` in this change — semantic validation needs `repo`. Task B's own diff builds on this same placement and extends it further; do not reorder anything else in the method.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k "invalid_head or invalid_note_sha or invalid_tag_ref or escapes_the_store or not_a_commit_or_tag" -v`
Expected: PASS, all five.

Run: `python3 -m pytest tests/ -v`
Expected: PASS (or visible skips only) — confirm nothing from Korrekturen 4-6 regressed. In particular `test_repair_finishes_an_interrupted_forget` (Korrektur 4) must still pass unchanged: it feeds `repair_pending_forget` values `_forget` itself just derived from freshly created objects and an already-safe `key`, which are always valid by construction and pass every new check here without issue.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Reject a checkpoint with an invalid value before repair runs it

_read_checkpoint (Korrektur 6) only proves the payload has the right
shape, never that a sha, ref name or key inside it is real. A value
that passes that check but is wrong used to reach _finish_forget
anyway: _rewrite_notes deletes refs/notes/commits before writing
entries back, so an invalid sha cost a real, unrelated note before
its own AssertionError even fired; _rewrite_tags wrote part of its
mapping into packed-refs before an invalid ref name's
PackedRefsException stopped it, breaking tag lookups for the whole
repository; _drop_from_index built a path straight from key with no
containment check, unlike every live write.

_validate_checkpoint_semantics now checks every sha with dulwich's
own valid_hexsha plus a real existence-and-type lookup (a tag target
must be a commit or a tag object, never a blob or tree), every tag
ref name with check_ref_format, and key with the same _file_for
containment check every live write already goes through - before
_finish_forget is ever reached. A failure is treated exactly like a
structurally broken checkpoint: logged, deleted, nothing written
(decision 21, correction 7).

Part of #24.
EOF
)"
```

---

### Task B: Reconcile the git index with HEAD whenever repair finds a checkpoint

A checkpoint can be discarded for reasons entirely unrelated to whether `_point_head` already ran — Korrektur 6's structural rejection, Task A's semantic rejection, or simple absence after a successful, ordinary `forget`. If `_point_head` *did* already run before the interruption, the on-disk git index still carries the forgotten dashboard's two files; `_drop_from_index`'s own docstring already documents why that matters for its one known key. Nothing before this task detects or repairs that staleness when the checkpoint that would have let `_finish_forget` finish the job is the very thing being discarded.

This task's first draft (a single, unconditional, path-only, whole-index scan) was reviewed before implementation and found to have three further gaps, closed below: the scan ran *after* `_read_checkpoint` had already deleted a broken file, losing its own trigger on a second failure; a shared `except KeyError` around both "no commit yet" and "commit/tree object missing" treated real repository corruption as an empty repository, licensing a full wipe; and comparing paths alone could not tell a dashboard `forget` actually orphaned from a completely different dashboard's brand-new, still-uncommitted first save, which looks identical by path. This plan already reflects the reviewed design.

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (two new methods, `repair_pending_forget` extended further)
- Test: `tests/test_store.py` (four new tests)

**Interfaces:**
- Consumes: `HistoryStore._repo`, `HistoryStore._checkpoint_path`, `HistoryStore._read_checkpoint` (all existing); the `repo` variable Task A's edit already moved ahead of `_read_checkpoint()` in `repair_pending_forget`.
- Produces:
  - `HistoryStore._best_effort_checkpoint_key(self) -> str | None` — a lenient, best-effort read of just the checkpoint's `key` field, used only by `_reconcile_index_with_head`'s caller.
  - `HistoryStore._reconcile_index_with_head(self, repo: Repo, key: str | None) -> None` — used only by `repair_pending_forget`, here.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_store.py`, directly after the five tests Task A added:

```python
def test_repair_reconciles_a_stale_index_after_an_unreadable_checkpoint(store, monkeypatch):
    """The exact scenario issue #24 reported: a forgotten dashboard's own
    self-healing mechanism bringing it back, when the checkpoint is too
    damaged even to say which key it was about.

    `forget("gone")` is interrupted right after `_point_head` - HEAD
    already rewritten to the tree without "gone", `_drop_from_index`
    never ran - and the checkpoint that would let a later repair
    finish the job is then found corrupted, exactly as it would be
    after the same power loss that interrupted the rewrite in the
    first place (`_write_file` never calls `fsync`, so the checkpoint
    written moments earlier is not guaranteed durable either).
    Truncated to 10 bytes, mid-key: even `_best_effort_checkpoint_key`
    cannot recover which dashboard this was about, forcing the
    generic, whole-index fallback. Without it, the next unrelated
    `write_snapshot` would build its commit from the stale index and
    bring "gone" back into HEAD.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def boom(self, repo, targets):
        raise RuntimeError("crash right after _point_head")

    monkeypatch.setattr(HistoryStore, "_rewrite_notes", boom)
    with pytest.raises(RuntimeError):
        store.forget("gone")
    monkeypatch.undo()

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_bytes(checkpoint.read_bytes()[:10])  # truncated mid-key

    store.repair_pending_forget()

    assert not checkpoint.exists()
    assert store.write_snapshot("home", "a: 2\n", "second, after repair") is not None
    assert "gone" not in store.list_all_dashboards()


def test_repair_reconciliation_leaves_a_staged_uncommitted_write_untouched(store, caplog):
    """Reconciliation must only ever act on a path HEAD does not have at
    all - never on one that merely differs in content.

    `write_snapshot` calls `porcelain.add` before `porcelain.commit`;
    if the commit step fails transiently, the index is left staged
    with newer content than HEAD for a path HEAD still has, ready to
    be picked up by the next save. That is indistinguishable, by path
    alone, from an ordinary in-flight write - removing it here would
    throw away a real, still-recoverable save.

    The checkpoint used here is for an unrelated key and carries an
    invalid `head`, so Task A's own validation rejects it and
    `_finish_forget` never runs - this isolates reconciliation's own
    precision from `_finish_forget`'s separate `garbage_collect` step
    (issue #25, not this plan's concern).
    """
    import logging
    from dulwich import porcelain
    from dulwich.repo import Repo

    store.write_snapshot("home", "a: 1\n", "first")
    (store.path / "home.yaml").write_text("a: 2 (staged, not committed)\n", encoding="utf-8")
    porcelain.add(str(store.path), [str(store.path / "home.yaml")])
    staged_sha_before = store._repo().open_index()[b"home.yaml"].sha

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "unrelated", "head": "not-a-sha", "notes": {}, "tags": {}}',
        encoding="utf-8",
    )

    with caplog.at_level(logging.ERROR):
        store.repair_pending_forget()

    after = Repo(str(store.path)).open_index()
    staged_sha_after = after[b"home.yaml"].sha
    assert staged_sha_after == staged_sha_before
    assert staged_sha_after in Repo(str(store.path)).object_store


def test_repair_reconciliation_spares_an_unrelated_new_dashboards_staged_save(
    store, monkeypatch
):
    """A generic sweep is only a fallback when the checkpoint's own key is
    unreadable - never the first choice when it is not.

    A completely unrelated, brand-new dashboard's first save (added,
    not yet committed) has its path in the index and nowhere in HEAD -
    identical, by path alone, to an orphan left by `forget`. The
    checkpoint's `key` survives here even though its `head` does not,
    so reconciliation must stay scoped to that one key and never touch
    the new dashboard's own entry. Issue #24, decision 21 correction 7
    (found in review of this plan's first draft, which used a
    generic, key-independent sweep unconditionally).
    """
    import json as json_module
    from dulwich import porcelain
    from dulwich.repo import Repo

    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("gone", "b: 1\n", "gone first")

    def boom(self, repo, targets):
        raise RuntimeError("crash right after _point_head")

    monkeypatch.setattr(HistoryStore, "_rewrite_notes", boom)
    with pytest.raises(RuntimeError):
        store.forget("gone")
    monkeypatch.undo()

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    payload = json_module.loads(checkpoint.read_text(encoding="utf-8"))
    payload["head"] = "not-a-sha"  # key stays readable, semantics do not
    checkpoint.write_text(json_module.dumps(payload), encoding="utf-8")

    (store.path / "newdash.yaml").write_text("z: 1\n", encoding="utf-8")
    porcelain.add(str(store.path), [str(store.path / "newdash.yaml")])
    new_blob_sha = store._repo().open_index()[b"newdash.yaml"].sha

    store.repair_pending_forget()

    after = Repo(str(store.path)).open_index()
    assert b"newdash.yaml" in after
    assert new_blob_sha in Repo(str(store.path)).object_store


def test_repair_reconciliation_surfaces_a_corrupted_tree_instead_of_deleting_everything(
    store,
):
    """A missing HEAD commit or tree object is corruption, not "empty".

    Treating every `KeyError` the same way used to mean a corrupted
    repository looked exactly like a fresh one - every index entry
    considered orphaned and removed. Only `repo.head()`'s own
    `KeyError` (a genuinely unborn branch) means "nothing is live"; a
    `KeyError` opening the commit or tree it names must propagate.
    Issue #24, decision 21 correction 7.
    """
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "x: 1\n", "other first")
    repo = store._repo()
    tree_sha = repo[repo.head()].tree.decode()
    object_path = store.path / ".git" / "objects" / tree_sha[:2] / tree_sha[2:]
    object_path.unlink()  # simulate a corrupted repository

    checkpoint = store.path / ".git" / "dashboard_history_forget.json"
    checkpoint.write_text(
        '{"key": "nonexistent", "head": null, "notes": {}, "tags": {}}',
        encoding="utf-8",
    )

    with pytest.raises(KeyError):
        store.repair_pending_forget()

    assert set(store._repo().open_index().paths()) == {b"home.yaml", b"other.yaml"}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest tests/test_store.py -k "reconciles_a_stale_index or staged_uncommitted or spares_an_unrelated or surfaces_a_corrupted" -v`

Expected: `test_repair_reconciles_a_stale_index_after_an_unreadable_checkpoint` FAILS on `assert "gone" not in store.list_all_dashboards()` — "gone" is back in HEAD, exactly issue #24's reproduction. `test_repair_reconciliation_leaves_a_staged_uncommitted_write_untouched` and `test_repair_reconciliation_spares_an_unrelated_new_dashboards_staged_save` PASS vacuously (nothing removes anything yet). `test_repair_reconciliation_surfaces_a_corrupted_tree_instead_of_deleting_everything` FAILS - `repair_pending_forget` does not raise `KeyError` today; it simply returns after `_read_checkpoint` rejects the (deliberately garbage) `key`, leaving the index untouched, so `pytest.raises(KeyError)` finds nothing raised. Step 4's full set, all four together, is the real proof this task adds targeted removal without over-reaching and without mistaking corruption for emptiness.

- [ ] **Step 3: Write the minimal implementation**

In `store.py`, add two new methods directly after `_validate_checkpoint_semantics` (from Task A), before `_file_for`:

```python
    def _best_effort_checkpoint_key(self) -> str | None:
        """The checkpoint's `key` field, read as leniently as possible.

        Used only to narrow `_reconcile_index_with_head`'s reach: if
        the checkpoint survived far enough to name which dashboard it
        was about - even if `head`, `notes` or `tags` did not -
        reconciliation only ever touches that dashboard's own two
        paths, with the same precision `_drop_from_index` already has
        for the ordinary case. Returns `None` on any failure
        whatsoever; the caller then falls back to the wider, generic
        sweep, which is the only way to still close a checkpoint too
        damaged to say even this much. See decision 21, correction 7.
        """
        try:
            payload = json.loads(self._checkpoint_path().read_text(encoding="utf-8"))
            key = payload["key"]
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            UnicodeDecodeError,
            OSError,
        ):
            return None
        return key if isinstance(key, str) else None

    def _reconcile_index_with_head(self, repo: Repo, key: str | None) -> None:
        """Drop any index entry whose path HEAD's tree no longer has.

        `_drop_from_index` already does this for one known key, right
        after `_finish_forget`'s other three steps succeed. If `forget`
        is interrupted between `_point_head` and `_drop_from_index` -
        HEAD already rewritten, the index not yet touched - and the
        checkpoint that would have let a later `repair_pending_forget`
        finish the job is itself discarded, nothing else remembers
        which key was being forgotten, unless `key` could still be
        recovered.

        When `key` is available (`_best_effort_checkpoint_key`
        recovered it), only that dashboard's own two paths are ever
        considered - identical precision to `_drop_from_index`, zero
        risk of touching an unrelated dashboard's own, still-legitimate
        index entry (a brand-new dashboard's first save, staged but not
        yet committed, has its path in the index and nowhere in HEAD
        too - indistinguishable from an orphan by path alone). Only
        when even `key` could not be recovered does this fall back to
        every path in the index - the only way to still close a
        checkpoint damaged enough to lose even that, at the cost of the
        same narrow ambiguity. See decision 21, correction 7.

        A path's *presence* in HEAD's tree is what decides its fate,
        never whether its content still matches: an index entry can
        legitimately differ from HEAD if a `porcelain.commit` step
        failed transiently and is waiting for the next save to retry.

        Only `repo.head()`'s own `KeyError` - no commit yet, a genuinely
        empty repository - is treated as "nothing is live". A `KeyError`
        while opening the commit, its tree, or the `meta` subtree HEAD
        already names is a corrupted repository, not an empty one, and
        is left to propagate rather than being read as license to
        remove every index entry.
        """
        index = repo.open_index()
        candidates = (
            [f"{key}.yaml".encode(), f"meta/{key}.yaml".encode()]
            if key is not None
            else list(index.paths())
        )

        try:
            head = repo.head()
        except KeyError:
            live: set[bytes] = set()
        else:
            commit = repo[head]
            tree = repo[commit.tree]
            live = set()
            for entry in tree.items():
                if entry.path == b"meta":
                    inner = repo[entry.sha]
                    for item in inner.items():
                        live.add(b"meta/" + item.path)
                    continue
                live.add(entry.path)

        changed = False
        for path in candidates:
            if path in index and path not in live:
                del index[path]
                (self.path / path.decode()).unlink(missing_ok=True)
                changed = True
        if changed:
            index.write()
```

Then extend `repair_pending_forget` (Task A already moved `repo = self._repo()` ahead of `_read_checkpoint()`) from:

```python
            repo = self._repo()
            if repo is None:
                return
            checkpoint = self._read_checkpoint()
            if checkpoint is None:
                return
            key, head, notes, tags = checkpoint
```

to:

```python
            repo = self._repo()
            if repo is None:
                return
            if self._checkpoint_path().exists():
                self._reconcile_index_with_head(repo, self._best_effort_checkpoint_key())
            checkpoint = self._read_checkpoint()
            if checkpoint is None:
                return
            key, head, notes, tags = checkpoint
```

The existence check runs *before* `_read_checkpoint()`, not after, and reconciliation is called from inside that `if`, not gated on `_read_checkpoint()`'s own return value: `_read_checkpoint` already deletes a structurally broken file itself and then returns `None`, which looks identical to "there never was one" from the caller's side. Checking existence first, and reconciling before that deletion can happen, is what lets reconciliation still run - and survive its own failure without losing its trigger - in exactly the case it exists for: a checkpoint that has to be thrown away.

Also add one sentence to `repair_pending_forget`'s docstring, directly after the paragraph Task A added:

```python
        Whenever a checkpoint file is found at all - whatever is then
        decided about its contents - `_reconcile_index_with_head` runs
        first, before anything could delete that file, so a discarded
        checkpoint never leaves the index resurrecting a forgotten
        dashboard into HEAD on the next, unrelated write (decision 21,
        correction 7).
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest tests/test_store.py -k "reconciles_a_stale_index or staged_uncommitted or spares_an_unrelated or surfaces_a_corrupted" -v`
Expected: PASS, all four.

Run: `python3 -m pytest tests/ -v`
Expected: PASS (or visible skips only) — the full suite, confirming Task A's five tests, this task's four, and every existing repair/checkpoint/forget test from Korrekturen 1-6 are all still green together.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "$(cat <<'EOF'
Reconcile the index with HEAD whenever repair finds a checkpoint

_drop_from_index already keeps the on-disk git index from naming a
forgotten dashboard's files once _finish_forget's other three steps
succeed. If forget is interrupted right after _point_head - HEAD
already rewritten, the index not yet touched - and the checkpoint
that would let a later repair finish the job has to be discarded for
any reason, nothing was left remembering to clean up the index.
Reproduced: the next unrelated write_snapshot then builds its commit
from the stale index and brings the forgotten dashboard back into
HEAD - the one operation in this integration meant to be irreversible
undoing itself.

_reconcile_index_with_head closes this, preferring a precise,
single-dashboard cleanup whenever the checkpoint's own key can still
be recovered - even from an otherwise unusable checkpoint - and
falling back to a generic, whole-index sweep only when even that is
unreadable. Runs before _read_checkpoint gets a chance to delete a
broken file, so a failure inside reconciliation itself never loses
its own trigger for the next attempt. Only repo.head()'s own absence
is read as an empty repository; a missing commit or tree object
surfaces as a real failure instead of licensing a full wipe.

Runs only when repair actually finds a checkpoint file, not on every
call - narrow enough for the trigger's real likelihood, general
enough to close it regardless of which correction ends up discarding
the checkpoint (decision 21, correction 7).

Closes #24.
EOF
)"
```

---

## Self-Review

**Spec coverage** (against Korrektur 7's full, reviewed text):
- "Typ- und Formprüfung allein garantieren keinen ausführbaren Plan" (semantic validation of `head`/`notes`/`tags`/`key` before `_finish_forget` is reached) → Task A.
- "das bloße Verwerfen eines nicht mehr vertrauenswürdigen Checkpoints übersieht, dass `_point_head` schon gelaufen sein kann" (index left stale after a discarded checkpoint) → Task B.
- The narrower scope Korrektur 7 explicitly chose (`_reconcile_index_with_head` runs only when a checkpoint was found, not on every `repair_pending_forget` call) → Task B, both in the method's own docstring and in `repair_pending_forget`'s existence check.
- The three further gaps found in review of this plan's first draft - reconciliation losing its own trigger, corruption mistaken for emptiness, path-absence mistaken for proof of an orphan - → Task B's reordering, narrowed `except KeyError`, and keyed-first/generic-fallback design, respectively.
- The `key`-containment gap found in the same review → Task A's `_file_for` call.
- The tag-target-type gap found in the same review → Task A's `_is_valid_tag_target`.
- Korrektur 7's explicit non-goal — reordering `_rewrite_notes`'s delete-then-write sequence — is not touched by either task; that sequence stays correct for its only caller, now always fed either freshly-derived values from a live `_forget` or a checkpoint validated by Task A before it ever arrives.
- Issue #25 (`_finish_forget`'s GC not knowing about the index) is explicitly out of scope, named as such at the top of this plan, and every test here is built so it is never incidentally exercised.

**Placeholder scan:** none found — every step above has complete code, not a description of code.

**Type consistency:** `_is_valid_commit`/`_is_valid_tag_target` both take `(repo: Repo, sha: bytes) -> bool`, matching how `_validate_checkpoint_semantics` calls them and how `head: bytes | None`, `notes: dict[bytes, bytes]`, `tags: dict[bytes, bytes | None]` are already typed from `_read_checkpoint` (Korrektur 6) through `_finish_forget` (Korrektur 4/5). `_best_effort_checkpoint_key(self) -> str | None` and `_reconcile_index_with_head(self, repo: Repo, key: str | None) -> None` share the same `str | None` for `key` at their boundary - the one place a `None` deliberately means "fall back to the generic sweep," not an error. `repo` throughout Task B is the same object `repair_pending_forget` already obtains via `self._repo()` and passes to `_finish_forget` later in the same method — no new type introduced anywhere in this plan.
