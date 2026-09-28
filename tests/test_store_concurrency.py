"""`forget` against every other operation that takes the store's lock.

Each test pauses a real `forget` inside its first progress report - under
the lock, after the caches are dropped, before any ref moves or the
checkpoint is written - and starts the other operation in a second
thread. It then proves three things: the other thread really found the
lock held (the guard in `conftest.py` saw it wait, not merely "not done
yet"), both threads finish once `forget` is let go, and the end state is
the one `forget` promises. See the "Concurrency" section of `store.py`
and docs/superpowers/specs/2026-09-28-historystore-aufteilen-design.md.

Only public methods and the public `progress` callback are used, so that
these tests survive a later restructuring of `store.py` unchanged.
"""

import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from dulwich.repo import Repo

from store import HistoryStore

# Only an upper bound: every wait below is for an event, never a sleep.
TIMEOUT = 10


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


class Background:
    """Run one call in its own thread and keep what it returned or raised."""

    def __init__(self, call, *args, **kwargs) -> None:
        self.result = None
        self.error: BaseException | None = None

        def run() -> None:
            try:
                self.result = call(*args, **kwargs)
            except BaseException as exc:  # noqa: BLE001 - handed to the test
                self.error = exc

        # A daemon, so that a thread stuck behind a failed test can never
        # keep the test run itself from ending.
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()

    @property
    def finished(self) -> bool:
        return not self.thread.is_alive()

    def join(self) -> None:
        self.thread.join(timeout=TIMEOUT)
        assert self.finished, "the background call did not finish"


@contextmanager
def forget_paused(store, key):
    """`store.forget(key)` in a thread, held inside its first progress call."""
    reached = threading.Event()
    release = threading.Event()

    def progress(phase, done, total):
        if not reached.is_set():
            reached.set()
            release.wait(timeout=TIMEOUT)

    run = Background(store.forget, key, progress=progress)
    assert reached.wait(timeout=TIMEOUT), (
        f"forget never reached its progress call (it raised {run.error!r})"
    )
    try:
        yield run
    finally:
        release.set()
        run.join()
    assert run.error is None, run.error


def queued_behind(lock, call, *args, **kwargs) -> Background:
    """Start `call` and prove it is waiting for `lock`, not merely slow."""
    other = Background(call, *args, **kwargs)
    assert lock.waited(other.thread, timeout=TIMEOUT), (
        f"the other operation never found the lock held (it raised {other.error!r})"
    )
    assert not other.finished
    return other


def history(store) -> SimpleNamespace:
    """home, then gone, then home again - so forgetting gone rewrites home_v2.

    `home_v2` carries `gone.yaml` in its tree, so `forget("gone")` gives
    it a new sha and prunes the old one. A commit before gone's first
    one would not do: forget rebuilds it with the same tree, parents and
    message, and its content-addressed sha stays the same.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    gone = store.write_snapshot("gone", "b: 1\n", "gone first")
    home_v2 = store.write_snapshot("home", "a: 2\n", "home second")
    store.create_version("gone/v1.0.0", "Gone", "", gone)
    store.create_version("home/v1.0.0", "Home", "", home_v2)
    store.set_description(home_v2, "a note on home_v2")
    return SimpleNamespace(gone=gone, home_v2=home_v2)


def assert_forgotten(store, before) -> None:
    """The preconditions every end state below relies on."""
    assert store.resolve(before.home_v2) is None
    assert "gone" not in store.list_all_dashboards()


# -- the guard itself ---------------------------------------------------


def test_guard_refuses_reentry(lock_guard, tmp_path):
    lock = lock_guard.for_path(tmp_path)
    with lock:
        with pytest.raises(RuntimeError, match="already holds it"):
            lock.acquire()


def test_guard_reports_a_thread_that_had_to_wait(lock_guard, tmp_path):
    lock = lock_guard.for_path(tmp_path)
    with lock:
        waiter = Background(lock.acquire)
        assert lock.waited(waiter.thread, timeout=TIMEOUT)
    waiter.join()
    lock.release()


def test_guard_reports_nobody_when_uncontended(lock_guard, tmp_path):
    lock = lock_guard.for_path(tmp_path)

    def take_and_give_back():
        with lock:
            pass

    free = Background(take_and_give_back)
    free.join()
    assert not lock.ever_waited(free.thread)


def test_guard_does_not_pass_a_finished_threads_mark_on(lock_guard, tmp_path):
    """A new thread must not inherit the mark of one that waited and ended.

    CPython reuses a thread's ident once it has ended, so a guard that
    remembered idents would report a fresh thread as having waited
    before it ever asked for the lock - and `queued_behind` would pass
    without proving anything. A hundred successors, because whether an
    ident is reused at once is up to the runtime (found in review).
    """
    lock = lock_guard.for_path(tmp_path)
    with lock:
        first = Background(lock.acquire)
        assert lock.waited(first.thread, timeout=TIMEOUT)
    first.join()
    lock.release()

    for _ in range(100):
        successor = Background(lambda: None)
        successor.join()
        assert not lock.ever_waited(successor.thread)


def test_guard_is_the_lock_every_store_of_that_path_takes(lock_guard, tmp_path):
    store = HistoryStore(tmp_path / "history")
    store.ensure()
    lock = lock_guard.for_path(tmp_path / "history")
    with lock:
        other = queued_behind(lock, store.write_snapshot, "home", "a: 1\n", "first")
    other.join()
    assert other.error is None
    assert other.result is not None


# -- forget against every other lock holder ------------------------------


def test_write_snapshot_waits_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(lock, store.write_snapshot, "home", "a: 3\n", "home third")
    other.join()

    assert_forgotten(store, before)
    assert other.error is None
    assert other.result is not None
    assert store.resolve("HEAD") == other.result
    rewritten = store.read_version("home", "home/v1.0.0").revision
    assert store.previous_change("home", other.result) == rewritten
    assert store.read_at("gone", "HEAD") is None
    index = Repo(str(store.path)).open_index()
    assert b"gone.yaml" not in index
    assert b"meta/gone.yaml" not in index


def test_mark_deleted_waits_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(lock, store.mark_deleted, "gone", "gone: deleted")
    other.join()

    assert_forgotten(store, before)
    assert other.error is None
    assert other.result is None
    assert store.list_changes("home", 1)[0].revision == store.resolve("HEAD")


def test_create_version_waits_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(
            lock, store.create_version, "home/v9.0.0", "Late", "", before.home_v2
        )
    other.join()

    assert_forgotten(store, before)
    assert isinstance(other.error, ValueError)
    assert "unknown revision" in str(other.error)
    assert "home/v9.0.0" not in [v.name for v in store.list_versions()]


def test_retitle_version_waits_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(
            lock, store.retitle_version, "gone", "gone/v1.0.0", "New", ""
        )
    other.join()

    assert_forgotten(store, before)
    assert isinstance(other.error, ValueError)
    assert "unknown version" in str(other.error)


def test_remove_version_waits_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(lock, store.remove_version, "gone", "gone/v1.0.0")
    other.join()

    assert_forgotten(store, before)
    assert isinstance(other.error, ValueError)
    assert "unknown version" in str(other.error)
    assert "gone/v1.0.0" not in [v.name for v in store.list_versions()]


def test_set_description_waits_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(lock, store.set_description, before.home_v2, "late note")
    other.join()

    assert_forgotten(store, before)
    assert other.error is None
    assert other.result is False
    assert "late note" not in store.descriptions().values()


def test_read_version_waits_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(lock, store.read_version, "home", "home/v1.0.0")
    other.join()

    assert_forgotten(store, before)
    assert other.error is None
    assert other.result.revision != before.home_v2
    assert other.result.revision == store.resolve("HEAD")


def test_repair_waits_for_forget(store, lock_guard):
    before = history(store)
    second = HistoryStore(store.path)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        other = queued_behind(lock, second.repair_pending_forget)
    other.join()

    assert_forgotten(store, before)
    assert other.error is None
    assert not store.forget_in_progress()
    assert store.forget_generation() == 1
    # Exactly what forget alone leaves behind - nothing the queued repair
    # could have added, moved or dropped: HEAD, the note, the one tag.
    rewritten = store.resolve("HEAD")
    assert store.read_version("home", "home/v1.0.0").revision == rewritten
    assert store.descriptions() == {rewritten: "a note on home_v2"}
    refs = Repo(str(store.path)).refs.as_dict()
    assert set(refs) == {
        b"HEAD",
        b"refs/heads/master",
        b"refs/notes/commits",
        b"refs/tags/home/v1.0.0",
    }
    assert refs[b"refs/heads/master"].decode() == rewritten


# -- reads that deliberately do not wait ---------------------------------


def test_list_changes_does_not_wait_for_forget(store, lock_guard):
    before = history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        reader = Background(store.list_changes, "gone")
        reader.join()
        assert not lock.ever_waited(reader.thread)
    assert reader.error is None
    assert [change.revision for change in reader.result] == [before.gone]


def test_measure_does_not_wait_for_forget(store, lock_guard):
    history(store)
    lock = lock_guard.for_path(store.path)
    with forget_paused(store, "gone"):
        reader = Background(store.measure)
        reader.join()
        assert not lock.ever_waited(reader.thread)
    assert reader.error is None
    assert reader.result.revisions == 3
    assert sorted(row.key for row in reader.result.dashboards) == ["gone", "home"]
