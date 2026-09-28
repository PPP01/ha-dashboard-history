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
