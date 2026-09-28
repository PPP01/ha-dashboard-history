"""Make the integration importable in plain pytest.

Only the Home-Assistant-free modules are imported this way, so the
package's __init__ (which imports Home Assistant) is never executed.
"""

import os
import pathlib
import sys
import threading

import pytest

# Exported: the file-based tests read the package's assets from here
# rather than each spelling the path out again.
PACKAGE = (
    pathlib.Path(__file__).resolve().parents[1]
    / "custom_components"
    / "dashboard_history"
)
sys.path.insert(0, str(PACKAGE))

# Some tests can run against real dashboards, which is worth a lot: the
# synthetic cards are four, a real installation has hundreds, and the
# weak matching was found to cover only 57 % of them that way. Where they
# live is a detail of somebody's machine, though, and this repository is
# public - so the path comes from the environment, or from a local file
# that git ignores. Neither is required; without one those cases skip and
# say so.
_LOCAL_STORAGE = pathlib.Path(__file__).with_name(".real-storage")
if not os.environ.get("DASHBOARD_HISTORY_REAL_STORAGE") and _LOCAL_STORAGE.exists():
    for line in _LOCAL_STORAGE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            os.environ["DASHBOARD_HISTORY_REAL_STORAGE"] = line.strip()
            break


class GuardedLock:
    """A `threading.Lock` that refuses re-entry and says who had to wait.

    Two jobs, both only in tests. Re-entry from the thread that already
    holds it raises instead of deadlocking, so a code path that takes
    `HistoryStore`'s lock twice fails loudly at the second `with` rather
    than hanging the suite. And a thread that finds it held is recorded
    before it starts waiting, so a test can prove that an operation
    really queued behind another one - finding it "not finished yet"
    after a pause proves nothing, since a thread that simply has not
    been scheduled is not finished either.
    """

    def __init__(self) -> None:
        self._inner = threading.Lock()
        # Thread objects, not `threading.get_ident()`: an ident is reused
        # once its thread has ended, and a new thread must never inherit a
        # finished one's mark (found in review).
        self._owner: threading.Thread | None = None
        self._seen = threading.Condition()
        self._waited: set[threading.Thread] = set()

    def acquire(self, blocking: bool = True, timeout: float = -1) -> bool:
        """Mirrors `threading.Lock.acquire`, with one caveat.

        `waited()` only means "this thread found the lock held and
        registered as such" - with `timeout=0` that registration still
        happens even though the immediate re-attempt below then fails
        at once, so the thread never actually blocked. Nothing in this
        suite calls `acquire` with a `timeout`, and `HistoryStore`
        itself never does either, so this stays a documented edge case
        rather than a fix (found in review).
        """
        me = threading.current_thread()
        if self._owner is me:
            raise RuntimeError(
                "HistoryStore's lock was requested again by the thread "
                "that already holds it - a plain threading.Lock would "
                "deadlock here"
            )
        if self._inner.acquire(blocking=False):
            self._owner = me
            return True
        if not blocking:
            return False
        with self._seen:
            self._waited.add(me)
            self._seen.notify_all()
        if not self._inner.acquire(timeout=timeout):
            return False
        self._owner = me
        return True

    def release(self) -> None:
        self._owner = None
        self._inner.release()

    def __enter__(self) -> "GuardedLock":
        self.acquire()
        return self

    def __exit__(self, *exc) -> None:
        self.release()

    def waited(self, thread: threading.Thread, timeout: float) -> bool:
        """Whether `thread` found this lock held, waiting up to `timeout`."""
        with self._seen:
            return self._seen.wait_for(
                lambda: thread in self._waited, timeout=timeout
            )

    def ever_waited(self, thread: threading.Thread) -> bool:
        with self._seen:
            return thread in self._waited


class LockGuard:
    """Stands in for `store._lock_for`: one `GuardedLock` per resolved path."""

    def __init__(self) -> None:
        self._locks: dict[str, GuardedLock] = {}
        self._registry = threading.Lock()

    def for_path(self, path) -> GuardedLock:
        key = str(pathlib.Path(path).resolve())
        with self._registry:
            if key not in self._locks:
                self._locks[key] = GuardedLock()
            return self._locks[key]


@pytest.fixture(autouse=True)
def lock_guard(monkeypatch):
    """Every `HistoryStore` built in a test gets a `GuardedLock`.

    Autouse and function-scoped, so pytest sets it up before any other
    fixture of the same test - the `store` fixtures included - and every
    instance built from then on looks `_lock_for` up here.
    """
    import store

    guard = LockGuard()
    monkeypatch.setattr(store, "_lock_for", guard.for_path)
    return guard
