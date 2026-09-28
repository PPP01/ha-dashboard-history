# HistoryStore-Invarianten – Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Nebenläufigkeitsregeln von `HistoryStore` an einer Stelle beschreiben und so prüfen, dass jeder Test nur im gewünschten Fall grün werden kann.

**Architecture:** Ein prüfender Lock ersetzt in allen Tests `store._lock_for` (Fixture in `tests/conftest.py`); er wirft bei doppeltem Sperren und meldet, welcher Thread warten musste. Eine neue Testdatei hält ein echtes `forget` in seinem `progress`-Callback an und lässt jede andere Methode, die den Lock nimmt, dagegen laufen. Am Produktivcode ändert sich nur der Modul-Docstring von `store.py`.

**Tech Stack:** Python 3.12/3.13, pytest, `threading`, dulwich 1.2.14.

**Spec:** `docs/superpowers/specs/2026-09-28-historystore-aufteilen-design.md` – Abschnitte 1 und 2. Abschnitt 3 (geparkt) ist **nicht** Teil dieses Plans.

## Global Constraints

- Code, Kommentare, Docstrings, Testnamen und Commit-Nachrichten **englisch**; Commit-Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen; Leerzeile; Body mit dem Warum, max. 72 Zeichen je Zeile; letzte Zeile `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- **Kein bestehender Test wird geändert** (Spec, Nicht-Ziele). Nur `tests/conftest.py` bekommt etwas dazu, und `tests/test_store_concurrency.py` ist neu.
- Am Produktivcode ändert sich **nur der Modul-Docstring** von `custom_components/dashboard_history/store.py`.
- Kein `git`-Subprozess in irgendeinem Code, auch nicht in Hilfsskripten; `store.py` bleibt frei von Home Assistant.
- Nach jedem Commit: `python3 -m pytest tests/ -q` mit 0 failed, `python3 tools/complexity_ratchet.py` und `lint-imports` grün. Fehlen die beiden Werkzeuge, vorher in einer virtuellen Umgebung **außerhalb** des Repositorys installieren: `python3 -m pip install "ruff==0.16.9" "import-linter==2.15"` (`CLAUDE.md`, »Tests«). Beim eigenen Durchspielen dieses Plans am 2026-09-28 waren sie nicht installiert; Gemini hat sie im Plan-Review am selben Tag nach Task 1, 2 und 3 laufen lassen – beide grün (`none grew`, `2 kept, 0 broken`).
- **Nicht pushen.** Push nur auf ausdrückliche Freigabe des Nutzers.
- Findet ein neuer Test einen echten Fehler im Store: **nicht beheben.** Anhalten, dem Nutzer berichten; nach seiner Freigabe Issue anlegen und den Test mit `pytest.mark.xfail(strict=True, reason="#<nr>: …")` einchecken (Spec, »Fehler- und Randfälle«).

## Review Focus

Eingaben und Zustände, die die Spec voraussetzt, ohne dass ein Test sie eigens prüft – mit dem erwarteten Verhalten:

1. **Die Gegenoperation scheitert, bevor sie den Lock überhaupt erreicht** (falscher Aufruf, Tippfehler in einem Argument): Der Test muss mit der Ausnahme des anderen Threads in der Meldung rot werden, nicht mit einem nichtssagenden Timeout. Abgedeckt durch die Meldung in `queued_behind` (Task 1), geprüft in Task 2, Schritt 3.
2. **`forget` endet, bevor es den Callback erreicht** (kein HEAD, Schlüssel unbekannt, eine Ausnahme): `forget_paused` meldet das samt Ausnahme, statt den Test vakuös weiterlaufen zu lassen (Task 1).
3. **Ein Test scheitert, während ein Hintergrund-Thread noch am Lock hängt:** Der Thread darf das Ende des pytest-Laufs nicht blockieren – deshalb Daemon-Threads und ein `finally`, das `forget` immer freigibt (Task 1).
4. **Eine langsame CI-Maschine:** Alle Wartepunkte sind Ereignisse; `TIMEOUT = 10` ist nur die Obergrenze. 20 Läufe hintereinander ohne Fehlschlag sind Teil der Abnahme (Task 2, Schritt 5).
5. **Eine `HistoryStore`-Instanz mit breiterem Fixture-Scope als `function`** bekäme den Wächter nicht. Heute gibt es keine; `test_guard_is_the_lock_every_store_of_that_path_takes` belegt die Verdrahtung für den Normalfall (Task 1).

## Dateien

- Modify: `tests/conftest.py` – `GuardedLock`, `LockGuard`, Fixture `lock_guard` (automatisch aktiv).
- Create: `tests/test_store_concurrency.py` – Hilfen, 5 Selbsttests des Wächters, 10 Nebenläufigkeitstests.
- Modify: `custom_components/dashboard_history/store.py:1-11` – Abschnitt »Concurrency« im Modul-Docstring.
- Modify: `docs/superpowers/status.md` – ein Eintrag.

**Reihenfolge gegenüber der Spec getauscht:** Die Spec nennt den Docstring zuerst. Er verweist aber auf die neuen Tests beim Namen, deshalb kommt er hier nach ihnen (Task 3) – so zeigt jeder Verweis im Commit, der ihn einführt, auf etwas, das existiert.

---

### Task 1: Der Wächter

**Files:**
- Modify: `tests/conftest.py` (am Ende anfügen)
- Create: `tests/test_store_concurrency.py`

**Interfaces:**
- Produces: Fixture `lock_guard` (Typ `LockGuard`) mit `lock_guard.for_path(path) -> GuardedLock`. `GuardedLock` hat `acquire(blocking=True, timeout=-1) -> bool`, `release()`, Kontextmanager, `waited(thread, timeout) -> bool` (wartet, bis `thread` den Lock besetzt vorfand), `ever_waited(thread) -> bool`. In `tests/test_store_concurrency.py`: `TIMEOUT`, Fixture `store`, `Background(call, *args, **kwargs)` mit `.thread`, `.result`, `.error`, `.finished`, `.join()`; `forget_paused(store, key)` (Kontextmanager); `queued_behind(lock, call, *args, **kwargs) -> Background`; `history(store) -> SimpleNamespace(gone=…, home_v2=…)`; `assert_forgotten(store, before)`.

- [ ] **Step 1: Selbsttests schreiben**

`tests/test_store_concurrency.py` mit genau diesem Inhalt anlegen:

```python
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
```

- [ ] **Step 2: Laufen lassen, Fehlschlag prüfen**

Run: `python3 -m pytest tests/test_store_concurrency.py -v`
Expected: 5 ERROR mit `fixture 'lock_guard' not found`.

- [ ] **Step 3: Den Wächter in `tests/conftest.py` anfügen**

Am Anfang der Datei zu den vorhandenen Imports `import threading` und `import pytest` ergänzen (alphabetisch: `threading` nach `sys`, `pytest` als eigener Block danach). Ans Ende der Datei anfügen:

```python
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
```

- [ ] **Step 4: Selbsttests grün, ganze Suite grün**

Run: `python3 -m pytest tests/test_store_concurrency.py -v`
Expected: 5 passed.

Run: `python3 -m pytest tests/ -q`
Expected: fünf Tests mehr als vor Task 1 bestanden, gleich viele übersprungen, 0 failed (am 2026-09-28 mit `.real-storage`: `976 passed, 2 skipped` → `981 passed, 2 skipped`; die absolute Zahl schwankt mit den Dashboards in `.real-storage`). Schlägt ein bestehender Test mit »requested again by the thread that already holds it« fehl, ist das ein echter Befund – anhalten und berichten (Global Constraints), nicht umgehen.

- [ ] **Step 5: Ratchet, Importverträge**

Run: `python3 tools/complexity_ratchet.py && lint-imports`
Expected: beide grün (sie prüfen nur `custom_components/`, dürfen sich also nicht ändern).

- [ ] **Step 6: Commit**

```bash
git add tests/conftest.py tests/test_store_concurrency.py
git commit -F - <<'EOF'
Guard HistoryStore's lock in every test

HistoryStore's lock is a plain threading.Lock: a code path that takes
it twice deadlocks, and the suite just hangs. The lock_guard fixture
turns that into a RuntimeError at the second acquire, for every store
a test builds. It also records which thread had to wait, so that a
test can prove an operation queued behind another one rather than
merely not having finished yet. Part of #42.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 2: `forget` gegen jede andere Methode, die den Lock nimmt

**Files:**
- Modify: `tests/test_store_concurrency.py` (am Ende anfügen)

**Interfaces:**
- Consumes: alles aus Task 1 (`lock_guard`, `store`, `Background`, `forget_paused`, `queued_behind`, `history`, `assert_forgotten`).
- Produces: die Testnamen, auf die der Docstring in Task 3 verweist: `test_write_snapshot_waits_for_forget`, `test_mark_deleted_waits_for_forget`, `test_create_version_waits_for_forget`, `test_retitle_version_waits_for_forget`, `test_remove_version_waits_for_forget`, `test_set_description_waits_for_forget`, `test_read_version_waits_for_forget`, `test_repair_waits_for_forget`, `test_list_changes_does_not_wait_for_forget`, `test_measure_does_not_wait_for_forget`.

- [ ] **Step 1: Die zehn Tests anfügen**

Ans Ende von `tests/test_store_concurrency.py`:

```python
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
```

- [ ] **Step 2: Laufen lassen**

Run: `python3 -m pytest tests/test_store_concurrency.py -v`
Expected: 15 passed in wenigen Sekunden. Diese Tests beschreiben heutiges Verhalten; sie werden nicht zuerst rot, sondern ihre Beweiskraft wird in Schritt 3 und 4 gezeigt. Schlägt einer fehl, ist das entweder ein Fehler im Test oder ein echter Befund im Store – im zweiten Fall anhalten (Global Constraints).

- [ ] **Step 3: Gegenprobe 1 – ohne Lock müssen die Warte-Tests rot werden**

Außerhalb des Repositorys (Wegwerf-Verzeichnis), nichts davon wird committet:

```bash
MUT=$(mktemp -d)
cp custom_components/dashboard_history/store.py custom_components/dashboard_history/versions.py "$MUT"/
python3 - "$MUT/store.py" <<'EOF'
import re, sys
path = sys.argv[1]
out, method = [], None
for line in open(path).read().split("\n"):
    found = re.match(r"    def (\w+)\(", line)
    if found:
        method = found.group(1)
    if line.strip() == "with self._lock:" and method not in ("ensure", "forget"):
        line = line.replace("with self._lock:", 'with __import__("contextlib").nullcontext():')
    out.append(line)
open(path, "w").write("\n".join(out))
EOF
grep -c nullcontext "$MUT/store.py"   # erwartet: 8
mkdir "$MUT/tests"
python3 - "$MUT" <<'EOF'
import pathlib, sys
mut = pathlib.Path(sys.argv[1])
conftest = pathlib.Path("tests/conftest.py").read_text()
start = conftest.index("PACKAGE = (")
end = conftest.index(")\n", start) + 2
conftest = conftest[:start] + f"PACKAGE = pathlib.Path({str(mut)!r})\n" + conftest[end:]
(mut / "tests" / "conftest.py").write_text(conftest)
EOF
cp tests/test_store_concurrency.py "$MUT/tests/"
python3 -m pytest "$MUT/tests/test_store_concurrency.py" -q -p no:cacheprovider
rm -rf "$MUT"
```

Expected: `9 failed, 6 passed` – rot die acht `*_waits_for_forget` und `test_guard_is_the_lock_every_store_of_that_path_takes`, grün die vier übrigen Selbsttests und die zwei `*_does_not_wait_for_forget`. Die Meldungen lauten »the other operation never found the lock held«. Dauer rund 90 s, weil jeder rote Test seinen Timeout abwartet.

- [ ] **Step 4: Gegenprobe 2 – nimmt ein Leser den Lock, müssen die Lesetests rot werden**

```bash
trap 'rm -f tests/test_zz_reader_mutant.py' EXIT
cat > tests/test_zz_reader_mutant.py <<'EOF'
import pytest
import store as store_module
from test_store_concurrency import (  # noqa: F401
    store,
    test_list_changes_does_not_wait_for_forget,
    test_measure_does_not_wait_for_forget,
)


@pytest.fixture(autouse=True)
def readers_take_the_lock(monkeypatch):
    for name in ("list_changes", "measure"):
        real = getattr(store_module.HistoryStore, name)

        def locked(self, *args, _real=real, **kwargs):
            with self._lock:
                return _real(self, *args, **kwargs)

        monkeypatch.setattr(store_module.HistoryStore, name, locked)
EOF
python3 -m pytest tests/test_zz_reader_mutant.py -q -p no:cacheprovider
rm -f tests/test_zz_reader_mutant.py
trap - EXIT
test ! -e tests/test_zz_reader_mutant.py && echo "mutant removed"
```

Expected: `2 failed` mit »the background call did not finish«, danach `mutant removed`. Die Datei wird auch bei einem Abbruch gelöscht (`trap`) und nie committet.

- [ ] **Step 5: Stabilität und ganze Suite**

```bash
for i in $(seq 20); do python3 -m pytest tests/test_store_concurrency.py -q -p no:cacheprovider > /dev/null || echo "run $i failed"; done
python3 -m pytest tests/ -q
python3 tools/complexity_ratchet.py && lint-imports
```

Expected: keine Zeile »run … failed«; zehn Tests mehr bestanden als nach Task 1, 0 failed (am 2026-09-28: `991 passed, 2 skipped`); Ratchet und Importverträge grün.

- [ ] **Step 6: Commit**

```bash
git add tests/test_store_concurrency.py
git commit -F - <<'EOF'
Test forget against every other lock holder

Nothing ran forget against the writers yet, and a forget that races
one is where this module has had most of its fixes. Each test pauses
a real forget under the lock and proves the other operation queued
behind it - the guard saw it wait, a pause alone would not show that
- then checks the end state, e.g. that create_version on a pruned
revision fails instead of tagging a dead object. Part of #42.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 3: Das Nebenläufigkeitsmodell im Modul-Docstring

**Files:**
- Modify: `custom_components/dashboard_history/store.py:1-11`
- Modify: `docs/superpowers/status.md`

**Interfaces:**
- Consumes: die Testnamen aus Task 1 und 2 sowie diese bestehenden Tests in `tests/test_store.py`: `test_two_instances_of_the_same_path_share_one_lock`, `test_list_changes_retries_a_read_that_raced_forget`, `test_list_changes_retries_when_a_checkpoint_is_present_even_if_head_is_stable`, `test_the_survey_follows_head`, `test_forgetting_a_dashboard_leaves_no_stale_index_behind`, `test_an_index_built_across_a_rewrite_is_not_kept`, `test_writes_refuse_while_a_forget_checkpoint_is_pending`.

- [ ] **Step 1: Vorher prüfen, dass jeder genannte Test existiert**

```bash
for name in test_two_instances_of_the_same_path_share_one_lock test_list_changes_retries_a_read_that_raced_forget test_list_changes_retries_when_a_checkpoint_is_present_even_if_head_is_stable test_the_survey_follows_head test_forgetting_a_dashboard_leaves_no_stale_index_behind test_an_index_built_across_a_rewrite_is_not_kept test_writes_refuse_while_a_forget_checkpoint_is_pending test_write_snapshot_waits_for_forget test_read_version_waits_for_forget test_repair_waits_for_forget test_list_changes_does_not_wait_for_forget test_measure_does_not_wait_for_forget; do grep -q "def $name(" tests/*.py || echo "missing: $name"; done
```

Expected: keine Ausgabe.

- [ ] **Step 2: Den Abschnitt einfügen**

In `store.py` die letzte Zeile des Modul-Docstrings

```python
Home Assistant OS, Container, Core and Supervised installations.
"""
```

ersetzen durch:

```python
Home Assistant OS, Container, Core and Supervised installations.

Concurrency
-----------
Five rules, each with the decision of the design record it comes from
and the test that pins it. They were spread over a score of docstrings
below; this is the one place that states them together.

1. **One lock per repository path, not per instance.** `_lock_for`
   hands every `HistoryStore` for the same resolved path the same
   `threading.Lock` (decision 21, correction 4), so a reload's fresh
   instance cannot run beside an old one that is still writing. It is
   a plain lock, not a re-entrant one: nothing called while it is held
   may take it again - which is why `_tag_at_locked` exists. Pinned by
   `test_two_instances_of_the_same_path_share_one_lock`, and for
   re-entry by the `lock_guard` fixture in `tests/conftest.py`, which
   fails any test whose code path takes the lock twice.
2. **Ten methods take it,** and each is one critical section:
   `ensure`, `write_snapshot`, `mark_deleted`, `create_version`,
   `retitle_version`, `read_version`, `remove_version`,
   `set_description`, `forget`, `repair_pending_forget`. For `forget`
   and `repair_pending_forget` that section holds the checkpoint, the
   generation counter, HEAD, notes, tags, the index and the garbage
   collection together. `read_version` is the one reader among them:
   the preview of a removal must not see a half-finished write. Pinned
   by the `*_waits_for_forget` tests in
   `tests/test_store_concurrency.py` - all but `ensure`, which after
   its first call per path and process only checks that `.git` exists.
3. **Every other read runs without it, on purpose** - a sensor must
   never wait fifteen seconds for a `forget`. What that costs differs,
   and each public read belongs to exactly one of three groups:

   * *Consistent or refused.* `list_changes`, and `search_changes`
     when it reads the versions itself, rebuild their whole answer when
     a `forget` raced them, and raise `RuntimeError` once the retry
     budget is spent (`_retrying_a_forget_race`, decision 24).
   * *Cannot meet a pruned object.* `list_versions` skips a tag that
     vanished while it listed (`_each_tag`); `forget_generation` and
     `forget_in_progress` read plain files.
   * *Best effort.* All the others - `survey`, `measure`,
     `previous_change`, `commit_times`, `commit_order`,
     `list_dashboards`, `list_all_dashboards`, `matching_revisions`,
     `same_state`, `resolve`, `read_at`, `read_meta_at`,
     `descriptions`. They catch a pruned object at the places a race
     was once observed and skip it or answer empty, but not
     throughout: `_resolve` loads the object it has just found without
     a guard, `_read_from` loads the blob without one, and building the
     index walks without one. While a `forget` prunes, any of them can
     still raise `KeyError` or `MissingCommitError`. Decision 24 does
     not cover them.

   Pinned: that the reads do not wait, by
   `test_list_changes_does_not_wait_for_forget` and
   `test_measure_does_not_wait_for_forget`; the retry, by
   `test_list_changes_retries_a_read_that_raced_forget`. The best-effort
   group is pinned by nothing, on purpose - best effort is all it
   promises; its unguarded loads are issue #44.
4. **The caches belong to the instance, not to the path.** `_index` and
   `_survey` are filled by readers without the lock and dropped by
   `forget` and `repair_pending_forget` under it. Both are keyed by
   HEAD, so an entry built before a rewrite - even one a reader stored
   after `forget` had dropped the cache - is recognised on its next use
   and rebuilt. Pinned by `test_the_survey_follows_head`,
   `test_forgetting_a_dashboard_leaves_no_stale_index_behind` and
   `test_an_index_built_across_a_rewrite_is_not_kept`.
5. **The checkpoint is a signal in both directions.** While the file an
   unfinished `forget` leaves behind exists, every write refuses
   (`_refuse_if_forget_pending`, decision 21), and the reads with a
   retry distrust their answer (decision 24). The other reads do not
   look at it. Pinned by
   `test_writes_refuse_while_a_forget_checkpoint_is_pending` and
   `test_list_changes_retries_when_a_checkpoint_is_present_even_if_head_is_stable`.
"""
```

- [ ] **Step 3: Prüfen**

```bash
python3 -c "import ast; ast.parse(open('custom_components/dashboard_history/store.py').read())"
python3 -m pytest tests/ -q
python3 tools/complexity_ratchet.py && lint-imports
git diff --stat   # erwartet: nur store.py, nur Docstring-Zeilen
```

Expected: dieselbe Zahl wie nach Task 2, 0 failed; beide Wächter grün; im Diff von `store.py` ausschließlich hinzugefügte Zeilen innerhalb des Modul-Docstrings.

- [ ] **Step 4: Eintrag in `docs/superpowers/status.md`**

Im Abschnitt »Bekannte offene Punkte« als neuen ersten Punkt einfügen (deutsch, eine Zeile, kein Hard-Wrap):

```markdown
- **Umgesetzt am <Datum der Umsetzung>** (GitHub-Issue [#42](https://github.com/PPP01/ha-dashboard-history/issues/42), nur der erste Teil): Die Nebenläufigkeitsregeln von `HistoryStore` stehen im Abschnitt »Concurrency« des Modul-Docstrings von `store.py`, jede mit Entscheidung und Test. Ein prüfender Lock in `tests/conftest.py` lässt jeden Test fehlschlagen, der den Lock doppelt nimmt, und `tests/test_store_concurrency.py` lässt `forget` gegen jede andere Methode laufen, die den Lock nimmt – mit nachgewiesenem Warten und geprüftem Endzustand. Der Umbau von `store.py` (Herauslösen von `forget`) ist ausgearbeitet, aber geparkt, bis `forget` selbst wieder geändert wird; #42 bleibt dafür offen. Spec: `specs/2026-09-28-historystore-aufteilen-design.md`.
```

`<Datum der Umsetzung>` ist das Datum des Tages, an dem dieser Task ausgeführt wird, im Format `JJJJ-MM-TT`. Er gehört in denselben Commit wie der Docstring – die Spec sieht für diese Arbeit drei Commits vor, und der Eintrag beschreibt genau den Stand, den dieser dritte herstellt.

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py docs/superpowers/status.md
git commit -F - <<'EOF'
Document the store concurrency model

What is locked, what is deliberately not, and how the unlocked reads
cope with a forget was spread over some twenty docstrings - enough to
mislead the spec for this change twice, into claiming protection for
reads that only have it in places. Five rules now, each with the
decision it comes from and the test that pins it, and every public
read sorted into one of three groups. Part of #42.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

### Task 4: Kommentar für #42

- [ ] **Step 1: Kommentar entwerfen – nicht absenden**

Den folgenden Text (englisch) dem Nutzer als Vorschau zeigen. Erst nach seiner ausdrücklichen Freigabe mit `gh issue comment 42 --body-file <datei>` absenden:

```markdown
First part done, deliberately not the split itself.

Measured before changing anything: half of `store.py` is docstrings, its functions are small (four above the complexity limit, the worst at 15), and it has not changed since 2026-09-22 - but it has more fix commits than any other file, nearly all about `forget` and concurrency, which is exactly where tests were missing.

So this part:

- documents the concurrency model in one place (the "Concurrency" section of the `store.py` module docstring), each rule with its decision and its test;
- adds a lock guard for the whole suite (`tests/conftest.py`): taking the lock twice from one thread fails instead of hanging, and a test can prove that another thread really waited;
- runs a paused `forget` against every other lock holder (`tests/test_store_concurrency.py`) and checks the end state.

The `forget` extraction is worked out in the spec (`docs/superpowers/specs/2026-09-28-historystore-aufteilen-design.md`, section 3) but parked until `forget` itself changes again. Keeping this issue open for it.
```

---

### Task 5: Korrektheits-Review in einer frischen Session

Nicht in der Session, die Spec und Plan geschrieben hat.

- [ ] **Step 1: Review-Auftrag an eine frische Session übergeben**

```markdown
Prüfe in ha-dashboard-history die Commits seit `475f0d1` (Spec) gegen die Spec `docs/superpowers/specs/2026-09-28-historystore-aufteilen-design.md`, Abschnitte 1 und 2, und den Plan `docs/superpowers/plans/2026-09-28-historystore-invarianten.md`. Antworte auf Deutsch.

1. Beschreibt der Abschnitt »Concurrency« im Modul-Docstring von `store.py` jede der fünf Regeln so, wie der Code sich heute verhält? Prüfe insbesondere Regel 3 (welche Leser über den Retry laufen, welche an Ort und Stelle abfangen) gegen jede öffentliche Lesemethode von `HistoryStore`, nicht nur gegen die genannten.
2. Existiert jeder im Docstring genannte Test, und prüft er, was der Docstring ihm zuschreibt?
3. Kann einer der Tests in `tests/test_store_concurrency.py` grün werden, ohne seine Eigenschaft zu beweisen? Weise das nicht durch Lesen nach, sondern durch Gegenprobe: Entferne in einer Wegwerf-Kopie außerhalb des Repositorys das `with self._lock` der geprüften Methode (bzw. füge es einem geprüften Leser hinzu) und zeige, dass der Test rot wird.
4. Ist am Produktivcode wirklich nur der Docstring geändert, und ist kein bestehender Test verändert (`git diff 475f0d1 -- tests/test_store.py` leer)?
5. Stimmen Kommentare und Docstrings, die dieses Vorhaben berührt, noch mit dem Code überein – auch dort, wo sie nicht in `.md`-Dateien stehen?

Kein Befund ohne Nachweis (Befehl und Ausgabe oder `datei:zeile`). Ändere nichts im Repository. Findings nach Schweregrad; am Ende die Liste dessen, was du ausdrücklich bestätigt hast.
```

- [ ] **Step 2: Befunde einarbeiten** – jeder Befund am Code nachgeprüft, bevor er übernommen wird; Korrekturen als eigene Commits.

## Nachbemerkung

`test_repair_waits_for_a_live_forget_on_another_instance` (`tests/test_store.py:104-157`) hat dieselbe Schwäche, die Astra für den ersten Entwurf der neuen Tests fand: Er schließt aus »nach einem Zeitfenster nicht fertig« auf Warten. Er bleibt in diesem Plan unverändert (keine Änderung an bestehenden Tests). Mit dem Wächter aus Task 1 ließe er sich später auf `lock.waited(…)` umstellen – ein eigener, kleiner Commit, wenn der Nutzer ihn möchte.
