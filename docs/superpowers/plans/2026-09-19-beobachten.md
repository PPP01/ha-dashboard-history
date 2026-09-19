# Beobachten — Implementierungsplan

> **Umgesetzt wird dieser Plan von Gemini.** Die Aufgaben in der angegebenen Reihenfolge abarbeiten, die Schritte innerhalb einer Aufgabe ebenso; die Checkboxen (`- [ ]`) sind zum Abhaken da. Es braucht dafür keine Werkzeuge außer Shell, Editor und `git` — der Abschnitt »Für den Umsetzer« unten sagt, was gilt.
>
> **Vorher lesen:** `CLAUDE.md` im Wurzelverzeichnis. Dort stehen die harten Regeln dieses Projekts, und sie gelten auch dort, wo dieser Plan sie nicht wiederholt.

**Ziel:** Fünf Diagnose-Sensoren und ein herunterladbarer Bericht, mit dem Tester die Messwerte zurückgeben können, auf die Vorhaben C laut Spec wartet.

**Architektur:** Zwei neue Home-Assistant-freie Module tragen die ganze Rechnerei — `measure()` in `store.py` sammelt in einem Durchgang, `report.py` baut daraus den JSON-Körper. Darüber liegen drei dünne HA-Schichten: ein `DataUpdateCoordinator`, fünf Sensor-Entitäten und ein `diagnostics.py`. Nichts davon fasst den Rekorder oder den Schreibpfad an.

**Technik:** Python 3.12 (Entwicklungsmaschine) / 3.14 (Container), `dulwich` 1.2.14, `pytest`, Home Assistant 2026.8.3.

**Spec:** `docs/superpowers/specs/2026-09-19-beobachten-design.md` — Entscheidungen B1 bis B10 und der Abschnitt »Der Vertrag des Berichts«. Die Spec ist bindend; wo dieser Plan von ihr abweicht, gilt sie.

## Voraussetzung

Dieser Plan setzt auf `main` ab `1ffa987` auf (»Design the measuring that C waits for«). Was er vorfindet und benutzt:

- `HistoryStore.survey()` und `HistoryStore._revision_index()` sind beide nach HEAD gecacht (`store.py:346-356`). Darauf beruht die gesamte Kostenrechnung.
- `HistoryStore._blob_at()` (`store.py:1788`) liefert die **Blob-ID**, nicht den Inhalt — der Name täuscht, der Docstring sagt es. Die Größe ist `len(repo[blob_id].data)`.
- Versionsmarken heißen `refs/tags/<key>/v<major>.<minor>.<patch>` (`_owns`, `store.py:316-328`). Ein Schlüssel darf selbst Schrägstriche enthalten, deshalb wird **von rechts** getrennt.
- `tests/integration/run_checks.py` hat bereits `entry_id(access)` (Zeile 289) und `reload_entry(access)` (Zeile 348).
- Der Options-Flow existiert und ersetzt die Optionen **vollständig** statt sie zu mischen (`config_flow.py:52-58`). Dieser Plan fügt keine Option hinzu, also bleibt das, wie es ist.

## Globale Randbedingungen

Gelten in **jeder** Aufgabe, auch wo sie nicht wiederholt werden:

- **Kein `import homeassistant`** in `store.py` und `report.py`. Beide müssen in gewöhnlichem `pytest` importierbar bleiben.
- **Kein Aufruf eines `git`-Programms.** Nur `dulwich`.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`). Der Verzeichnis-Walk ist blockierend.
- **Nichts blockiert den Start von Home Assistant.** Kein `async_config_entry_first_refresh`.
- **Alle Byte-Werte sind Ganzzahlen in Bytes**, nie KiB oder MB.
- **Alle Datumsangaben im Bericht sind tagesgenau** (`YYYY-MM-DD`, UTC) — die einzige Ausnahme ist `measured_at`.
- **Code, Kommentare, Docstrings und Commit-Messages auf Englisch.** Dieser Plan ist deutsch, das Ergebnis nicht.

## Für den Umsetzer

Dieser Plan wird außerhalb von Claude Code abgearbeitet. Was dort selbstverständlich wäre, steht deshalb hier.

### Nachweispflicht

**Eine Aufgabe gilt erst als erledigt, wenn ihre Befehlsausgabe vorliegt — als Text, nicht als Behauptung.** Für jede Aufgabe gehört in die Rückmeldung:

- der Befehl, so wie er gelaufen ist,
- die **letzten Zeilen seiner Ausgabe** im Original (bei `pytest` die Zusammenfassungszeile, bei `run_checks.py` die `ok`/`FAIL`-Zeilen),
- der Commit-Hash.

»Tests laufen durch« ohne die Zeile `N passed` ist kein Nachweis. Wenn etwas nicht läuft: die Fehlermeldung ungekürzt zeigen und **anhalten**, nicht umbauen, bis es grün aussieht.

### Arbeitsumgebung

- Alle Befehle laufen im **Wurzelverzeichnis des Repos**. Kein `cd /pfad &&` davorsetzen.
- Die Prüfbank ist ein Wegwerf-Container: `docker compose -f docker/compose.yaml up -d`. Aufgaben 4, 6, 7, 8 und 9 brauchen ihn.

### Nach jeder Python-Änderung: den Container neu starten

**Ein Integrations-Reload lädt geänderten Python-Code nicht neu.** `reload_entry` ruft `async_unload_entry` und `async_setup_entry` erneut auf, aber die Modul-Objekte bleiben im laufenden Prozess, wie sie beim ersten Import waren. Wer nach einer Änderung an `store.py` oder `__init__.py` nur neu lädt, prüft den **alten** Code und bekommt ein grünes Ergebnis, das nichts bedeutet.

Deshalb vor jeder Prüfung, die geänderten Python-Code betrifft:

```bash
docker compose -f docker/compose.yaml restart
python3 - <<'WAIT'
import sys
sys.path.insert(0, "tests/integration")
from run_checks import wait_for_api, wait_for_integration, token
assert wait_for_api(), "Home Assistant kam nicht wieder hoch"
assert wait_for_integration(token()), "die Integration wurde nicht eingerichtet"
print("bereit")
WAIT
```

**Warum dieses Warten den IP-Bann nicht auslöst:** `wait_for_api` fragt `/manifest.json` ohne Anmeldung ab, `wait_for_integration` benutzt ein gültiges Token. Der Bann greift bei **fehlgeschlagenen Anmeldeversuchen** — davon erzeugt keiner der beiden welche. Was verboten bleibt, ist das, was das Projekt einmal teuer gelernt hat: mit ungültigen oder abgelaufenen Zugangsdaten gegen eine startende Instanz zu hämmern.

`reload_entry` bleibt trotzdem in Gebrauch — aber als **Funktionstest** (»übersteht das Entladen und erneute Einrichten den zweiten Durchlauf?«), nicht als Weg, neuen Code zu laden. Das ist Aufgabe 9.
- **Kein `push`, kein `tag`, keine Release.** Committen ja, veröffentlichen nein — das entscheidet der Eigentümer des Repos.
- Die Zahl der `pytest`-Fälle **schwankt** mit den Dashboards der echten `.storage`. Maßgeblich ist allein `0 failed`, nie eine absolute Zahl.

### Was in diesem Vorhaben nicht angefasst wird

Wenn eine dieser Dateien im Diff auftaucht, ist etwas schiefgegangen:

- `panel.js`, `panel.py`, `capture.py`, `operations.py`, `services.py`, `milestones.py`, `restore.py`, `analyze.py` — dieses Vorhaben misst, es ändert nichts am Aufzeichnen oder am Zurückholen.
- `config_flow.py` — es kommt **keine** neue Option dazu. Der Kommentar dort über das vollständige Ersetzen der Optionen bleibt stehen, wie er ist.

### Sprache

Code, Kommentare, Docstrings und **Commit-Messages auf Englisch**. Dieser Plan ist deutsch, das Ergebnis nicht. Commit-Betreff im Imperativ, erster Buchstabe groß, höchstens 50 Zeichen; Leerzeile; Rumpf auf 72 Zeichen umgebrochen und mit der **Begründung**, nicht der Beschreibung. Die Betreffzeilen in diesem Plan sind bereits in dieser Form vorgeschlagen und können übernommen werden.

### Vorgegebener Code ist ein Vorschlag, kein Diktat

Die Codeblöcke hier sind ausformuliert, damit niemand raten muss — nicht, weil jede Zeile unantastbar wäre. Wenn beim Schreiben auffällt, dass etwas so nicht funktioniert (eine API heißt anders, eine Signatur passt nicht), dann ist **der Plan falsch und nicht die Wirklichkeit**: den Unterschied melden und die funktionierende Fassung nehmen. Eine Stelle, an der das wahrscheinlich ist, ist in Aufgabe 8 ausdrücklich markiert.

Umgekehrt gilt: Die **Kommentare** in den Codeblöcken sind nicht Beiwerk. Sie halten die Begründung fest, die in der Spec steht, und dieses Projekt lebt davon. Sie gehören mit übernommen.

## Wo eine Rückfrage fällig ist, statt allein zu entscheiden

Zwei Stellen. Überall sonst gilt: durcharbeiten.

1. **Aufgabe 4.** Das Aktualisierungs-Intervall wird aus einer Messung abgeleitet, nicht geraten. Messergebnis vorlegen, dann entscheiden lassen.
2. **Aufgabe 10, README.** Der Text, mit dem Tester um Messwerte gebeten werden, ist eine öffentliche Äußerung in einem öffentlichen Repository — und er muss sagen, was der HA-Umschlag mitschickt. Wortlaut vorher zeigen.

## Dateien

| Datei | Zuständig für |
|---|---|
| `custom_components/dashboard_history/store.py` | *ändern:* `DashboardFacts`, `Measurement`, `measure()`, `_measure_disk()` |
| `custom_components/dashboard_history/report.py` | *neu:* der JSON-Körper und die IDs. HA-frei. |
| `custom_components/dashboard_history/coordinator.py` | *neu:* der `DataUpdateCoordinator` |
| `custom_components/dashboard_history/sensor.py` | *neu:* die fünf Entitäten |
| `custom_components/dashboard_history/diagnostics.py` | *neu:* Secret, Refresh, Übergabe an `report()` |
| `custom_components/dashboard_history/__init__.py` | *ändern:* Plattform vorwärts, Plattform zurück |
| `custom_components/dashboard_history/const.py` | *ändern:* `PLATFORMS`, `MEASURE_INTERVAL`, `DATA_REPORT_SECRET` |
| `custom_components/dashboard_history/strings.json`, `translations/en.json` | *ändern:* Namen der fünf Entitäten |
| `tests/test_measure.py` | *neu:* `measure()` |
| `tests/test_report.py` | *neu:* Vertrag, IDs, Datenschutz |
| `tests/integration/run_checks.py` | *ändern:* Download, Reload, gemeinsamer Stand, Secret |
| `CLAUDE.md`, `README.md`, `docs/superpowers/status.md` | *ändern:* siehe Aufgabe 10 |

---

## Aufgabe 1: `Measurement` und die Summen

**Dateien:**
- Ändern: `custom_components/dashboard_history/store.py`
- Test: `tests/test_measure.py` (neu)

**Schnittstellen:**
- Liefert: `store.DashboardFacts`, `store.Measurement`, `HistoryStore.measure() -> Measurement`. Aufgabe 2 füllt die Größenfelder, Aufgabe 3 die Liste `dashboards`, Aufgabe 5 liest alles.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_measure.py`:

```python
"""Tests for what the history costs and holds."""

import pytest
from store import HistoryStore, Measurement


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def test_an_empty_history_measures_as_empty(store):
    found = store.measure()
    assert found.revisions == 0
    assert found.oldest is None
    assert found.newest is None
    assert found.newest_key is None
    assert found.dashboards == ()


def test_a_store_without_a_repository_does_not_raise(tmp_path):
    found = HistoryStore(tmp_path / "nothing").measure()
    assert isinstance(found, Measurement)
    assert found.revisions == 0


def test_revisions_are_counted_across_dashboards(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.measure().revisions == 3


def test_the_newest_commit_is_named_with_its_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    found = store.measure()
    assert found.newest_key == "other"
    assert found.newest >= found.oldest


def test_versions_are_counted_without_reading_the_tags(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "")
    store.write_snapshot("other", "b: 1\n", "first")
    store.create_version("other/v1.0.0", "First", "")
    assert store.measure().versions == 2
```

- [ ] **Schritt 2: Lauf zur Bestätigung, dass er fehlschlägt**

Lauf: `python3 -m pytest tests/test_measure.py -v`
Erwartet: FAIL mit `ImportError: cannot import name 'Measurement'`.

- [ ] **Schritt 3: Die minimale Umsetzung schreiben**

In `store.py`, direkt hinter `class Survey` (also vor `class RevisionIndex`):

```python
@dataclass(frozen=True)
class DashboardFacts:
    """One dashboard's share of the history.

    `bytes` is the length of the newest state that *had content*, which
    for a deleted dashboard is the state before its deletion - the size
    a restore would bring back. `last` is the newest commit that touched
    it at all, which for that same dashboard is the deletion. The two
    fields answer different questions on purpose; tying both to one
    revision would answer one of them wrongly.
    """

    key: str
    revisions: int
    bytes: int
    versions: int
    first: int
    last: int
    gone: bool


@dataclass(frozen=True)
class Measurement:
    """What the history costs and holds, taken at one moment.

    Every field has a defined value on an empty or absent repository, so
    that a fresh installation reads as "nothing recorded yet" rather
    than as a failure - an empty history is an answer, not a fault.

    A history that cannot be *read*, though, is a fault, and `measure`
    raises on one. The coordinator above it keeps the last good
    measurement and marks it stale, which is what a reader needs;
    numbers quietly missing their unreadable half would not be.
    """

    revisions: int = 0
    oldest: int | None = None
    newest: int | None = None
    newest_key: str | None = None
    versions: int = 0
    dashboards: tuple[DashboardFacts, ...] = ()
    bytes_logical: int = 0
    bytes_allocated: int | None = None
    bytes_git_logical: int = 0
    bytes_worktree_logical: int = 0
    loose_objects: int = 0
    packs: int = 0
```

Und als neue öffentliche Methode von `HistoryStore`, hinter `survey()`:

```python
    def measure(self) -> Measurement:
        """Everything the sensors show and the report carries, in one pass.

        Deliberately not behind `self._lock`: every other read here -
        `list_changes`, `survey`, `read_at` - runs without it, and a
        measurement that waits for a running `forget` would block a
        sensor for fifteen seconds. What it can catch instead is a
        half-rewritten history, and every step below survives that by
        skipping rather than raising.
        """
        repo = self._repo()
        if repo is None:
            return Measurement()
        index = self._revision_index(repo)
        if index is None:
            return Measurement()

        by_position = {position: revision for revision, position in index.order.items()}
        newest_revision = by_position.get(0)
        oldest_revision = by_position.get(max(by_position)) if by_position else None
        edges = self.commit_times(
            [r for r in (newest_revision, oldest_revision) if r is not None]
        )
        newest_key = next(
            (
                key
                for key, revisions in index.by_key.items()
                if revisions and revisions[0] == newest_revision
            ),
            None,
        )

        return Measurement(
            revisions=len(index.order),
            oldest=edges.get(oldest_revision) if oldest_revision else None,
            newest=edges.get(newest_revision) if newest_revision else None,
            newest_key=newest_key,
            versions=len(repo.refs.as_dict(b"refs/tags")),
        )

    @staticmethod
    def _versions_by_key(repo: Repo) -> dict[str, int]:
        """How many version marks each dashboard has.

        Counted from the ref *names* alone - `refs/tags/<key>/vX.Y.Z` -
        without loading a single tag object. `list_versions` would read
        every object in the namespace, and measured on 2026-09-05 that
        cost 492 ms at 3650 tags. A count needs none of it.

        Split from the right, because a key may hold a slash itself: a
        dashboard recorded before the key rule existed can be named
        `foo/bar`, and splitting from the left would file its versions
        under `foo`.
        """
        counted: dict[str, int] = {}
        for ref in repo.refs.as_dict(b"refs/tags"):
            if b"/" not in ref:
                continue
            key = ref.rsplit(b"/", 1)[0].decode()
            counted[key] = counted.get(key, 0) + 1
        return counted
```

- [ ] **Schritt 4: Lauf zur Bestätigung, dass er durchläuft**

Lauf: `python3 -m pytest tests/test_measure.py -v`
Erwartet: PASS, sechs Fälle.

- [ ] **Schritt 5: Die gesamte Suite laufen lassen**

Lauf: `python3 -m pytest tests/ -q`
Erwartet: `0 failed`. Die absolute Zahl schwankt mit den Dashboards der echten `.storage` — nur »0 failed« zählt.

- [ ] **Schritt 6: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_measure.py
git commit -m "Count what the history holds in a single pass"
```

---

## Aufgabe 2: Die Größe, logisch und belegt

**Dateien:**
- Ändern: `custom_components/dashboard_history/store.py`
- Test: `tests/test_measure.py`

**Schnittstellen:**
- Benutzt: `Measurement` aus Aufgabe 1.
- Liefert: gefüllte Felder `bytes_logical`, `bytes_allocated`, `bytes_git_logical`, `bytes_worktree_logical`, `loose_objects`, `packs`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_measure.py` anhängen:

```python
import os


def _walked(path):
    """Sum the same tree independently, for the test to compare against."""
    logical = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            logical += os.lstat(os.path.join(root, name)).st_size
    return logical


def test_the_logical_size_is_the_sum_of_every_file(store):
    store.write_snapshot("home", "a: 1\n", "first")
    found = store.measure()
    assert found.bytes_logical == _walked(store.path)


def test_git_and_worktree_add_up_to_the_whole(store):
    store.write_snapshot("home", "a: 1\n", "first")
    found = store.measure()
    assert found.bytes_git_logical + found.bytes_worktree_logical == found.bytes_logical
    assert found.bytes_worktree_logical > 0


def test_allocated_size_is_whole_blocks_or_absent(store):
    store.write_snapshot("home", "a: 1\n", "first")
    allocated = store.measure().bytes_allocated
    assert allocated is None or allocated % 512 == 0


def test_loose_objects_are_counted_and_packing_moves_them(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    before = store.measure()
    assert before.loose_objects > 0
    assert before.packs == 0

    from dulwich.repo import Repo

    with Repo(str(store.path)) as repo:
        repo.object_store.pack_loose_objects()
    after = store.measure()
    assert after.packs >= 1
    assert after.loose_objects < before.loose_objects
```

> **Was hier absichtlich *nicht* geprüft wird:** dass eine Datei von einem Byte einen ganzen Block belegt. Das klingt wie der naheliegende Test für `st_blocks` und ist auf mehreren Dateisystemen falsch — ext4 mit `inline_data` und btrfs legen sehr kleine Dateien in den Inode und melden `st_blocks == 0`. Der Test wäre je nach Laufumgebung rot, ohne dass der Code falsch wäre. Geprüft wird stattdessen die Invariante, die überall gilt: ein Vielfaches von 512.

- [ ] **Schritt 2: Lauf zur Bestätigung, dass er fehlschlägt**

Lauf: `python3 -m pytest tests/test_measure.py -k "size or loose or worktree" -v`
Erwartet: FAIL — `bytes_logical` ist 0.

- [ ] **Schritt 3: Die minimale Umsetzung schreiben**

`os` und `Path` sind in `store.py` bereits importiert (Zeilen 16 und 21), es ist nichts zu ergänzen. Neue Methode hinter `measure()`:

```python
    def _measure_disk(self) -> dict:
        """Walk the store once and weigh it in two ways.

        Two numbers rather than one, and that is the point of this
        method. `st_size` is what a file contains; `st_blocks * 512` is
        what it costs. For a packed repository the two are within a
        percent of each other - measured on 2026-09-19 against the test
        bench, 0.1 % across the pack. Across the *loose* objects of the
        same repository it was 689.5 %: a loose git object is a few
        hundred bytes and still occupies a whole 4 KiB block. The loose
        count is precisely the number initiative C decides on, so
        reporting only the logical size would be reporting the wrong one.

        Both numbers come out of one `lstat` per file. It is one walk,
        not two, and the allocated figure costs nothing on top.

        `st_blocks` does not exist on Windows. There the allocated sum
        stays `None` rather than being estimated against a guessed block
        size: a missing number is honest, an invented one spoils the very
        analysis it was invented for.

        Only a *vanished* file is skipped. A permission error or a bad
        disk is not skipped, it is raised: the coordinator turns that
        into a failed refresh, keeps the last good numbers and says
        `stale`. Swallowing every `OSError` would publish a measurement
        that is silently too small and flag it as fresh, which is worse
        than no measurement at all. `os.walk` is given `onerror` for the
        same reason - without it, it hides directory errors by design.
        """

        def _raise(error: OSError) -> None:
            raise error

        git = self.path / ".git"
        objects = git / "objects"
        packs = objects / "pack"
        logical = allocated = git_logical = worktree_logical = 0
        loose_count = pack_count = 0
        have_blocks = True

        for root, _dirs, files in os.walk(self.path, onerror=_raise):
            here = Path(root)
            in_git = here == git or git in here.parents
            for name in files:
                try:
                    stat = os.lstat(here / name)
                except FileNotFoundError:
                    # A `garbage_collect` is pruning while we count. One
                    # file missing from a size is nothing. Every other
                    # OSError travels on - see the docstring.
                    continue
                logical += stat.st_size
                blocks = getattr(stat, "st_blocks", None)
                if blocks is None:
                    have_blocks = False
                else:
                    allocated += blocks * 512
                if in_git:
                    git_logical += stat.st_size
                else:
                    worktree_logical += stat.st_size
                if here == packs:
                    if name.endswith(".pack"):
                        pack_count += 1
                elif here.parent == objects and len(here.name) == 2:
                    # git fans loose objects out over two-character
                    # directories. `objects/info` is neither, which is
                    # why the name length is asked and not just the parent.
                    loose_count += 1

        return {
            "bytes_logical": logical,
            "bytes_allocated": allocated if have_blocks else None,
            "bytes_git_logical": git_logical,
            "bytes_worktree_logical": worktree_logical,
            "loose_objects": loose_count,
            "packs": pack_count,
        }
```

In `measure()` beide `return`-Stellen und den Schluss um die Größen ergänzen:

```python
    def measure(self) -> Measurement:
        sizes = self._measure_disk()
        repo = self._repo()
        if repo is None:
            return Measurement(**sizes)
        index = self._revision_index(repo)
        if index is None:
            return Measurement(**sizes)
        ...
        return Measurement(
            revisions=len(index.order),
            ...
            versions=len(repo.refs.as_dict(b"refs/tags")),
            **sizes,
        )
```

- [ ] **Schritt 4: Lauf zur Bestätigung, dass er durchläuft**

Lauf: `python3 -m pytest tests/test_measure.py -v`
Erwartet: PASS, zehn Fälle.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_measure.py
git commit -m "Weigh the store in bytes and in blocks"
```

---

## Aufgabe 3: Eine Zeile je Dashboard

**Dateien:**
- Ändern: `custom_components/dashboard_history/store.py`
- Test: `tests/test_measure.py`

**Schnittstellen:**
- Liefert: `Measurement.dashboards` als Tupel von `DashboardFacts`, absteigend nach `revisions`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

An `tests/test_measure.py` anhängen:

```python
def test_each_dashboard_gets_a_row_sorted_by_revisions(store):
    store.write_snapshot("quiet", "a: 1\n", "first")
    for n in range(3):
        store.write_snapshot("busy", f"b: {n}\n", f"change {n}")
    rows = store.measure().dashboards
    assert [row.key for row in rows] == ["busy", "quiet"]
    assert rows[0].revisions == 3
    assert rows[1].revisions == 1
    assert all(not row.gone for row in rows)


def test_a_live_dashboard_reports_the_length_of_its_current_state(store):
    text = "a: 1\nb: 2\n"
    store.write_snapshot("home", text, "first")
    row = store.measure().dashboards[0]
    assert row.bytes == len(text.encode("utf-8"))


def test_a_deleted_dashboard_reports_what_a_restore_would_bring_back(store):
    text = "a: 1\nb: 2\nc: 3\n"
    store.write_snapshot("home", text, "first")
    store.mark_deleted("home", "home was deleted")
    row = store.measure().dashboards[0]
    assert row.gone is True
    # Not the deletion commit, which holds no dashboard text at all.
    assert row.bytes == len(text.encode("utf-8"))


def test_first_and_last_bracket_a_dashboards_own_commits(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    row = store.measure().dashboards[0]
    assert row.first <= row.last


def test_versions_are_attributed_to_their_own_dashboard(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "")
    rows = {row.key: row for row in store.measure().dashboards}
    assert rows["home"].versions == 1
    assert rows["other"].versions == 0
```

- [ ] **Schritt 2: Lauf zur Bestätigung, dass er fehlschlägt**

Lauf: `python3 -m pytest tests/test_measure.py -k dashboard -v`
Erwartet: FAIL — `dashboards` ist leer, `IndexError`.

- [ ] **Schritt 3: Die minimale Umsetzung schreiben**

Neue Methode in `HistoryStore`:

```python
    def _bytes_of_newest_content(self, repo: Repo, key: str, revisions: list) -> int:
        """The length of the newest state of `key` that had any.

        For a live dashboard that is the state at HEAD and the first
        revision answers. For a deleted one the newest revision is the
        deletion commit, whose tree no longer holds the file at all - so
        the loop steps back to the state before it, which is exactly what
        a restore would bring back.

        Zero where nothing is found. A dashboard that never held content
        cannot occur through `write_snapshot`, but a history rewritten by
        an interrupted `forget` is not worth an exception here.
        """
        path = f"{key}.yaml"
        for revision in revisions:
            blob_id = self._blob_at(repo, path, revision)
            if blob_id is None:
                continue
            try:
                return len(repo[blob_id].data)
            except KeyError:
                # Pruned between the tree lookup and the read.
                return 0
        return 0
```

In `measure()`, vor dem `return`:

```python
        live = self.survey().live
        marks = self._versions_by_key(repo)
        wanted = set()
        for revisions in index.by_key.values():
            if revisions:
                wanted.add(revisions[0])
                wanted.add(revisions[-1])
        times = self.commit_times(wanted)

        rows = []
        for key, revisions in index.by_key.items():
            if not revisions:
                continue
            rows.append(
                DashboardFacts(
                    key=key,
                    revisions=len(revisions),
                    bytes=self._bytes_of_newest_content(repo, key, revisions),
                    versions=marks.get(key, 0),
                    first=times.get(revisions[-1], 0),
                    last=times.get(revisions[0], 0),
                    gone=key not in live,
                )
            )
        rows.sort(key=lambda row: (-row.revisions, row.key))
```

Und `dashboards=tuple(rows)` in den `Measurement(...)`-Aufruf aufnehmen. `marks` ersetzt dort den zweiten Aufruf von `_versions_by_key`, die Gesamtzahl bleibt `len(repo.refs.as_dict(b"refs/tags"))`.

> **Warum die Gesamtzahl *nicht* die Summe der Zeilen ist:** Eine Marke ohne Schrägstrich — `refs/tags/v1` — gehört keinem Dashboard. `_versions_by_key` übergeht sie mit Absicht, denn sie in eine Dashboard-Zeile zu schreiben hieße, sie dem falschen zuzuordnen. In der Gesamtzahl muss sie trotzdem auftauchen, sonst zählt der Bericht weniger Marken, als das Repository hat. Dass Summe der Zeilen und Gesamtzahl auseinandergehen dürfen, ist der richtige Zustand, kein Fehler.

- [ ] **Schritt 4: Lauf zur Bestätigung, dass er durchläuft**

Lauf: `python3 -m pytest tests/test_measure.py -v`
Erwartet: PASS, fünfzehn Fälle.

- [ ] **Schritt 5: Die gesamte Suite laufen lassen**

Lauf: `python3 -m pytest tests/ -q`
Erwartet: `0 failed`.

- [ ] **Schritt 6: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_measure.py
git commit -m "Give every dashboard its own row in the measurement"
```

---

## Aufgabe 4: Messen, was ein `measure()` kostet ✅ erledigt am 2026-09-19

**Erledigt.** Die Messung lief, und sie hat mehr ergeben als eine Zahl: Die Kostenannahme in Spec-Entscheidung B3 war falsch. Beides steht jetzt in der Spec, Abschnitt »Was gemessen wurde« und B3 selbst.

| | |
|---|---|
| warmes `measure()` | 154,6 ms (zweiter Lauf 193 ms) |
| kaltes `measure()` | 6.981 ms |
| Verzeichnis-Walk | 10,0 ms — nur 6 % |
| wo die Zeit steckt | Blob-Längen 67,9 ms, `commit_times` 45,2 ms |
| **Entschieden** | **`MEASURE_INTERVAL = timedelta(minutes=15)`** |

**Für Aufgabe 6 ist das die verbindliche Zahl:** In `const.py` steht `timedelta(minutes=15)`, und der Kommentar darüber verweist auf diese Aufgabe.

Der Ablauf, mit dem gemessen wurde, bleibt hier stehen — falls jemand gegen eine andere Anlage nachmessen will:

- [ ] **Schritt 1: Gegen die Prüfbank messen**

Der Container muss laufen (`docker compose -f docker/compose.yaml up -d`). Über `stdin`, weil nur `custom_components/` hineingereicht ist:

```bash
docker exec -i dashboard-history-test python3 - <<'PY'
import sys, time
sys.path.insert(0, "/config/custom_components/dashboard_history")
from store import HistoryStore

store = HistoryStore("/config/dashboard_history")

start = time.perf_counter()
first = store.measure()
cold = time.perf_counter() - start

start = time.perf_counter()
store.measure()
warm = time.perf_counter() - start

start = time.perf_counter()
store._measure_disk()
walk = time.perf_counter() - start

print(f"cold (caches empty) {cold*1000:8.1f} ms")
print(f"warm (HEAD unchanged) {warm*1000:8.1f} ms")
print(f"of which the walk    {walk*1000:8.1f} ms")
print(f"{first.revisions} revisions, {len(first.dashboards)} dashboards, "
      f"{first.versions} marks, {first.bytes_logical/1048576:.1f} MB")
PY
```

- [ ] **Schritt 2: Das Ergebnis vorlegen und das Intervall entscheiden lassen**

Die Spec gibt die Leitplanken: unter 50 ms darf es enger als 15 Minuten werden, bei mehreren hundert Millisekunden weiter. Der **warme** Wert ist der, der im Betrieb zählt — die Caches greifen dort, außer direkt nach einem Schreibvorgang.

Weicht eine Zahl stark von der Erwartung ab, stimmt eine Annahme nicht mehr: dann anhalten, nicht die Schwelle anpassen.

- [ ] **Schritt 3: Die Zahl in der Spec nachtragen**

Die entschiedene Zahl und die drei Messwerte in `docs/superpowers/specs/2026-09-19-beobachten-design.md` eintragen, Abschnitt »Was noch gemessen werden muss« — die Tabelle dort steht genau dafür bereit.

```bash
git add docs/superpowers/specs/2026-09-19-beobachten-design.md
git commit -m "Put a measured number where the guess stood"
```

---

## Aufgabe 5: `report.py` — der Vertrag, die IDs, der Datenschutz

**Dateien:**
- Erstellen: `custom_components/dashboard_history/report.py`
- Test: `tests/test_report.py` (neu)

**Schnittstellen:**
- Benutzt: `store.Measurement`, `store.DashboardFacts`.
- Liefert: `report.dashboard_id(key: str, secret: str) -> str` und `report.build(measurement, secret, *, daily_versions: bool, measured_at: float | None, stale: bool) -> dict`. Aufgabe 8 ruft `build()`, Aufgabe 7 ruft `dashboard_id()`.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

`tests/test_report.py`:

```python
"""Tests for the report a tester can send back."""

import pytest
import report
from store import DashboardFacts, Measurement

SECRET = "0123456789abcdef0123456789abcdef"

FACTS = Measurement(
    revisions=3,
    oldest=1740873600,   # 2025-03-02 00:00:00 UTC
    newest=1758153600,   # 2025-09-18 00:00:00 UTC
    newest_key="wohnzimmer",
    versions=2,
    dashboards=(
        DashboardFacts("wohnzimmer", 2, 268341, 2, 1740873600, 1758153600, False),
        DashboardFacts("heizung-keller", 1, 4012, 0, 1740873600, 1740873600, True),
    ),
    bytes_logical=9182768,
    bytes_allocated=9629696,
    bytes_git_logical=8627657,
    bytes_worktree_logical=555111,
    loose_objects=18,
    packs=1,
)


def built(**kwargs):
    settings = dict(daily_versions=True, measured_at=1758196800.0, stale=False)
    settings.update(kwargs)
    return report.build(FACTS, SECRET, **settings)


def test_the_four_blocks_are_all_there():
    body = built()
    assert set(body) == {
        "schema", "measured_at", "stale",
        "environment", "settings", "totals", "dashboards",
    }


def test_totals_carry_every_field_of_the_contract():
    totals = built()["totals"]
    assert totals["dashboards_live"] == 1
    assert totals["dashboards_gone"] == 1
    assert totals["dashboards_ever"] == 2
    assert totals["revisions"] == 3
    assert totals["versions"] == 2
    assert totals["bytes_logical"] == 9182768
    assert totals["bytes_allocated"] == 9629696
    assert totals["loose_objects"] == 18
    assert totals["packs"] == 1


def test_dates_are_days_and_carry_no_time_of_day():
    body = built()
    assert body["totals"]["oldest"] == "2025-03-02"
    assert body["totals"]["newest"] == "2025-09-18"
    for row in body["dashboards"]:
        assert "T" not in row["first"] and "T" not in row["last"]


def test_measured_at_is_the_only_timestamp_and_is_utc():
    assert built()["measured_at"].endswith("+00:00")


def test_an_empty_history_reports_honest_zeros():
    body = report.build(
        Measurement(), SECRET, daily_versions=False, measured_at=1758196800.0, stale=False
    )
    assert body["dashboards"] == []
    assert body["totals"]["revisions"] == 0
    assert body["totals"]["dashboards_ever"] == 0
    assert body["totals"]["oldest"] is None
    assert body["environment"]["dulwich"]


def test_never_measured_is_not_the_same_as_measured_and_empty():
    body = report.build(
        None, SECRET, daily_versions=False, measured_at=None, stale=True
    )
    assert body["measured_at"] is None
    assert body["stale"] is True
    # No totals at all, rather than a block of zeros: a reader must be
    # able to tell "nothing recorded" from "nothing measured yet".
    assert body["totals"] == {}
    assert body["dashboards"] == []
    # The two fields that answer something even here.
    assert body["environment"]["dulwich"]
    assert "yaml_c_loader" in body["environment"]


def test_dashboards_are_sorted_by_revisions_and_flag_the_gone_ones():
    rows = built()["dashboards"]
    assert rows[0]["revisions"] == 2
    assert rows[0]["gone"] is False
    assert rows[1]["gone"] is True


# -- the ids -----------------------------------------------------------


def test_the_same_key_and_secret_give_the_same_id():
    assert report.dashboard_id("home", SECRET) == report.dashboard_id("home", SECRET)


def test_a_different_key_gives_a_different_id():
    assert report.dashboard_id("home", SECRET) != report.dashboard_id("away", SECRET)


def test_a_different_secret_gives_a_different_id_for_the_same_key():
    other = "ffffffffffffffffffffffffffffffff"
    assert report.dashboard_id("home", SECRET) != report.dashboard_id("home", other)


def test_an_id_is_eight_hex_characters():
    found = report.dashboard_id("home", SECRET)
    assert len(found) == 8
    assert all(c in "0123456789abcdef" for c in found)


# -- the one that keeps this file shareable ----------------------------


def _every_string(value):
    """Every string anywhere in the structure, keys included."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _every_string(item)
    elif isinstance(value, list):
        for item in value:
            yield from _every_string(item)
    elif isinstance(value, str):
        yield value


def test_no_dashboard_name_survives_into_the_report():
    body = built()
    haystack = "\n".join(_every_string(body))
    for name in ("wohnzimmer", "heizung-keller"):
        assert name not in haystack, f"{name!r} leaked into the report"
```

- [ ] **Schritt 2: Lauf zur Bestätigung, dass er fehlschlägt**

Lauf: `python3 -m pytest tests/test_report.py -v`
Erwartet: FAIL mit `ModuleNotFoundError: No module named 'report'`.

- [ ] **Schritt 3: Die minimale Umsetzung schreiben**

`custom_components/dashboard_history/report.py`:

```python
"""The report a tester can hand back, and nothing that identifies them.

Free of Home Assistant on purpose. The one test that matters in this
module - that no dashboard name, path or title survives into the file -
has to run in plain `pytest`, or it is the least often executed test in
the project. See the spec, decision B6.

What this module builds is the `data` block of a diagnostics download.
Home Assistant wraps its own envelope around it (system info including
the timezone, every installed custom integration, the manifest). That
envelope is outside this module's reach and outside its promise; what
is promised here is that this block says nothing about the dashboards
of the installation it came from.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

import yaml

SCHEMA = 1


def dashboard_id(key: str, secret: str) -> str:
    """A stable, opaque name for one dashboard.

    Keyed, not plain. Dashboard names are short and ordinary -
    `wohnzimmer`, `energie`, `garten` - and a dictionary resolves an
    unsalted hash of one in seconds. A plain digest would claim an
    irreversibility it does not have.

    `hmac` rather than hashing the two strings glued together: it is one
    line of the standard library either way, and nobody has to decide
    later which of the two came first or what separated them.

    Eight hex characters, short enough to say out loud in an issue. At
    fifty dashboards the chance of two colliding is about 3 in 10
    million; should it ever happen, the length grows to twelve - not
    beforehand on suspicion.
    """
    digest = hmac.new(secret.encode("utf-8"), key.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:8]


def _day(seconds: int | None) -> str | None:
    """A timestamp as a day, in UTC, or None.

    Day-granular everywhere, including the newest capture, although the
    sensor carries the full timestamp locally. A time of day says
    nothing about size and something about the habits of whoever sent
    the file.
    """
    if not seconds:
        return None
    return datetime.fromtimestamp(seconds, UTC).strftime("%Y-%m-%d")


def _environment() -> dict:
    """The two things Home Assistant's own envelope does not carry.

    Everything else - HA version, Python version, architecture,
    installation type, this integration's manifest - is already in the
    envelope, and a value reported twice is a value that can disagree
    with itself.
    """
    try:
        import dulwich

        version = ".".join(str(part) for part in dulwich.__version__)
    except Exception:  # noqa: BLE001
        version = None
    return {
        "dulwich": version,
        # Decides a factor of 8-9 when loading, and without it no other
        # number in this file can be compared with anybody else's. See
        # `.claude/lessons.md`.
        "yaml_c_loader": hasattr(yaml, "CSafeLoader"),
    }


def build(
    measurement,
    secret: str,
    *,
    daily_versions: bool,
    measured_at: float | None,
    stale: bool,
) -> dict:
    """The `data` block, built field by field.

    `measurement` may be `None`, meaning no measurement has ever
    succeeded. That is reported as empty `totals` rather than as zeros,
    because zeros are what a real but empty history looks like.

    Additive, never redacted afterwards. Home Assistant offers
    `async_redact_data` to black out fields on the way out, and that is
    the wrong way round: whoever collects everything and then strikes
    some of it out publishes, at the next new field, exactly the one
    nobody thought of. What is not named here does not exist in the
    result.
    """
    if measurement is None:
        # Never measured, which is not the same as measured and empty.
        # An empty history has a `totals` block of honest zeros; a
        # measurement that never happened has no totals at all, and a
        # reader has to be able to tell the two apart. Spec, B10.
        return {
            "schema": SCHEMA,
            "measured_at": None,
            "stale": True,
            "environment": _environment(),
            "settings": {"daily_versions": daily_versions},
            "totals": {},
            "dashboards": [],
        }
    rows = [
        {
            "id": dashboard_id(facts.key, secret),
            "revisions": facts.revisions,
            "bytes": facts.bytes,
            "versions": facts.versions,
            "first": _day(facts.first),
            "last": _day(facts.last),
            "gone": facts.gone,
        }
        for facts in measurement.dashboards
    ]
    gone = sum(1 for facts in measurement.dashboards if facts.gone)
    live = len(measurement.dashboards) - gone
    return {
        "schema": SCHEMA,
        "measured_at": (
            datetime.fromtimestamp(measured_at, UTC).isoformat()
            if measured_at
            else None
        ),
        "stale": stale,
        "environment": _environment(),
        "settings": {"daily_versions": daily_versions},
        "totals": {
            "dashboards_live": live,
            "dashboards_gone": gone,
            # Written out rather than left to be worked out, so that an
            # inconsistency in the report shows up instead of cancelling
            # itself.
            "dashboards_ever": len(measurement.dashboards),
            "revisions": measurement.revisions,
            "versions": measurement.versions,
            "oldest": _day(measurement.oldest),
            "newest": _day(measurement.newest),
            "bytes_logical": measurement.bytes_logical,
            "bytes_allocated": measurement.bytes_allocated,
            "bytes_git_logical": measurement.bytes_git_logical,
            "bytes_worktree_logical": measurement.bytes_worktree_logical,
            "loose_objects": measurement.loose_objects,
            "packs": measurement.packs,
        },
        "dashboards": rows,
    }
```

- [ ] **Schritt 4: Lauf zur Bestätigung, dass er durchläuft**

Lauf: `python3 -m pytest tests/test_report.py -v`
Erwartet: PASS, vierzehn Fälle.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/report.py tests/test_report.py
git commit -m "Build a report that says nothing about the dashboards"
```

---

## Aufgabe 6: Der Coordinator und die Plattform, hin und zurück

**Dateien:**
- Erstellen: `custom_components/dashboard_history/coordinator.py`
- Ändern: `custom_components/dashboard_history/const.py`
- Ändern: `custom_components/dashboard_history/__init__.py`

**Schnittstellen:**
- Benutzt: `HistoryStore.measure()` aus Aufgabe 1–3.
- Liefert: `coordinator.MeasurementCoordinator` mit `.data: Measurement | None`; liegt unter `hass.data[DOMAIN]["coordinator"]`. Aufgabe 7 und 8 lesen es.

- [ ] **Schritt 1: `const.py` ergänzen**

```python
# The first entity platform of this integration. A list, because
# `async_forward_entry_setups` and `async_unload_platforms` both want one
# and a mismatch between the two leaves entities behind after a reload.
PLATFORMS = [Platform.SENSOR]

# How often the measurement is taken when nothing is being recorded. The
# event does the rest, and does it sooner. Measured before it was set;
# see the plan of 2026-09-19, task 4.
MEASURE_INTERVAL = timedelta(minutes=15)

# Where the per-installation secret behind the report ids lives, inside
# `entry.data`. Not in the repository folder: that is the one directory
# the README invites people to look into, and it is copied as a whole by
# anyone who shares their history to help with a bug.
DATA_REPORT_SECRET = "report_secret"
```

Dazu oben `from datetime import timedelta` und `from homeassistant.const import Platform`.

> `const.py` importiert damit Home Assistant. Das tut es über `voluptuous` hinaus bisher nicht — aber `const.py` steht nicht auf der Liste der HA-freien Module in `CLAUDE.md`, und `Platform` ist die Aufzählung, die HA selbst für genau diesen Zweck anbietet.

- [ ] **Schritt 2: Den Coordinator schreiben**

`custom_components/dashboard_history/coordinator.py`:

```python
"""One measurement, shared by the sensors and the report."""

from __future__ import annotations

import logging
import time

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import DOMAIN, MEASURE_INTERVAL
from .store import HistoryStore, Measurement

_LOGGER = logging.getLogger(__name__)


class MeasurementCoordinator(DataUpdateCoordinator[Measurement]):
    """Takes the measurement, on a timer and on every recorded change."""

    def __init__(self, hass: HomeAssistant, store: HistoryStore) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=MEASURE_INTERVAL,
        )

        self._store = store
        # When the measurement in `self.data` was taken. Carried here
        # because `DataUpdateCoordinator` has no such field: checked
        # against Home Assistant 2026.8.3 on 2026-09-19, there is no
        # `last_update_time`, and the report has to be able to say how
        # old its numbers are.
        #
        # None until the first success, and deliberately *not* touched
        # when a refresh fails: the timestamp belongs to the numbers in
        # `self.data`, which a failed refresh leaves alone. Moving it
        # would date old numbers to now.
        self.measured_at: float | None = None

    async def _async_update_data(self) -> Measurement:
        """Measure, off the event loop.

        A directory walk over hundreds of loose objects is blocking work
        and belongs in an executor - the hard rule, and this is the only
        place in this initiative that touches the disk at all.

        An unreadable store raises out of `measure` and arrives here as
        `UpdateFailed`, which is what keeps the last good numbers in
        `self.data` and lets the report call itself stale.
        """
        try:
            found = await self.hass.async_add_executor_job(self._store.measure)
        except OSError as error:
            raise UpdateFailed(f"could not measure the history: {error}") from error
        self.measured_at = time.time()
        return found
```

- [ ] **Schritt 3: `__init__.py` ändern — hin**

In `async_setup_entry`, nach dem Anlegen von `capture` und `milestones`:

```python
    coordinator = MeasurementCoordinator(hass, store)
    hass.data[DOMAIN] = {
        "store": store,
        "capture": capture,
        "milestones": milestones,
        "coordinator": coordinator,
    }
```

Und hinter `await panel.async_register(hass)`:

```python
    async def _remeasure(_event) -> None:
        await coordinator.async_request_refresh()

    # Through `entry.async_on_unload`, so that unloading drops it. A
    # listener remembered in a second place is a listener forgotten in
    # one of them, and after a reload it would measure against a store
    # nobody uses any more.
    entry.async_on_unload(hass.bus.async_listen(EVENT_HISTORY_UPDATED, _remeasure))
```

> `async_request_refresh` und nicht `async_refresh`: Der Debouncer des Coordinators fängt genau den Schwall ab, den ein `restore_state` erzeugt, wenn viele Dashboards in einem Zug geschrieben werden. Der Download in Aufgabe 8 nimmt aus demselben Grund die ungebremste Form.

> **`async_forward_entry_setups` steht hier ausdrücklich noch nicht.** `sensor.py` entsteht erst in Aufgabe 7, und eine Plattform anzumelden, die es nicht gibt, lässt das Einrichten mit einem Fehler im Protokoll enden. Anmeldung und Abbau kommen deshalb gemeinsam mit der Datei, die sie betreffen — Aufgabe 7, Schritt 3. Diese Aufgabe hinterlässt einen Stand, der startet und misst, nur eben noch nichts anzeigt.

Der erste Refresh wird im bereits vorhandenen Hintergrundtask `_async_open` angestoßen, ganz am Ende:

```python
    # Last, and deliberately: the first measurement of an empty history
    # is an honest zero, but a measurement taken after the opening pass
    # is the one somebody wants to see on the integration page.
    await coordinator.async_refresh()
```

Dazu die Importe: `EVENT_HISTORY_UPDATED` aus `.const` und `MeasurementCoordinator` aus `.coordinator`. **`PLATFORMS` noch nicht** — es wird hier nirgends benutzt, und ein unbenutzter Import ist eine Zeile, die beim Lesen eine Absicht behauptet, die es noch nicht gibt. Es kommt in Aufgabe 7 dazu. `_async_open` bekommt den Coordinator als weiteren Parameter.

- [ ] **Schritt 4: Prüfen, dass die Integration überhaupt noch startet**

`__init__.py` hat sich geändert, also **Container neu starten** — der Abschnitt »Für den Umsetzer« sagt, warum ein Reload hier nicht genügt und wie das Warten aussieht.

Lauf danach: `python3 tests/integration/run_checks.py`
Erwartet: `0 failed` wie vor der Änderung. Es prüft hier noch nichts Neues; es prüft, dass nichts Altes kaputtgegangen ist — insbesondere, dass ein Coordinator ohne Entitäten niemandem im Weg steht.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/const.py \
        custom_components/dashboard_history/coordinator.py \
        custom_components/dashboard_history/__init__.py
git commit -m "Take the measurement on a timer and on every change"
```

---

## Aufgabe 7: Die fünf Entitäten

**Dateien:**
- Erstellen: `custom_components/dashboard_history/sensor.py`
- Ändern: `custom_components/dashboard_history/strings.json`, `custom_components/dashboard_history/translations/en.json`

**Schnittstellen:**
- Benutzt: `MeasurementCoordinator` aus Aufgabe 6, `report.dashboard_id` aus Aufgabe 5, `DATA_REPORT_SECRET` aus Aufgabe 6.
- Liefert: fünf Entitäten unter `sensor.dashboard_history_*`.

- [ ] **Schritt 1: Das Secret dorthin legen, wo beide es holen**

In `report.py` ergänzen — HA-frei, deshalb hier und nicht in `diagnostics.py`:

```python
import secrets


def new_secret() -> str:
    """A fresh per-installation secret for the report ids."""
    return secrets.token_hex(16)
```

Und in `coordinator.py` eine Funktion, die beide Verbraucher benutzen:

```python
from homeassistant.config_entries import ConfigEntry

from . import report
from .const import DATA_REPORT_SECRET


def report_secret(hass: HomeAssistant, entry: ConfigEntry) -> str:
    """The installation's own secret, made on first need.

    On first need rather than in the config flow, so that an
    installation set up before this existed needs no migration and
    `VERSION` stays at 1. Writing it fires no reload: no update listener
    is attached to this entry, and `config_flow.py` says why.

    First need is the first refresh of the sensors, not the first
    report - the id mapping hangs off an entity attribute and is there
    long before anybody downloads anything.
    """
    existing = entry.data.get(DATA_REPORT_SECRET)
    if existing:
        return existing
    made = report.new_secret()
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, DATA_REPORT_SECRET: made}
    )
    return made
```

`report_secret` ist eine Modulfunktion und **keine** Methode des Coordinators — sie bekommt den Eintrag von ihrem Aufrufer. Die Signatur `MeasurementCoordinator(hass, store)` aus Aufgabe 6 bleibt damit unverändert.

- [ ] **Schritt 2: `sensor.py` schreiben**

```python
"""What the history costs and holds, as five diagnostic entities."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import report
from .const import DOMAIN, OPTION_DAILY_VERSIONS
from .coordinator import MeasurementCoordinator, report_secret
from .store import Measurement


@dataclass(frozen=True, kw_only=True)
class Reading(SensorEntityDescription):
    """One number and the detail that belongs beside it.

    The detail travels as attributes rather than as more entities: five
    entities are a device page somebody reads, fifteen are one they skim
    past, and a median belongs to its count rather than beside it.
    """

    value: Callable[[Measurement], object]
    extra: Callable[[Measurement, str, bool], dict] = lambda m, s, d: {}


def _median(numbers: list[int]) -> int:
    if not numbers:
        return 0
    ordered = sorted(numbers)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) // 2


READINGS: tuple[Reading, ...] = (
    Reading(
        key="last_capture",
        translation_key="last_capture",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda m: (
            datetime.fromtimestamp(m.newest, UTC) if m.newest else None
        ),
        extra=lambda m, secret, daily: {
            "dashboard": (
                report.dashboard_id(m.newest_key, secret) if m.newest_key else None
            )
        },
    ),
    Reading(
        key="size",
        translation_key="size",
        device_class=SensorDeviceClass.DATA_SIZE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        suggested_unit_of_measurement=UnitOfInformation.MEGABYTES,
        state_class=SensorStateClass.MEASUREMENT,
        # The allocated figure is the state, because that is what costs a
        # user disk space. Where the platform has no `st_blocks` -
        # Windows - it is absent and the logical sum stands in.
        value=lambda m: (
            m.bytes_allocated if m.bytes_allocated is not None else m.bytes_logical
        ),
        extra=lambda m, secret, daily: {
            "bytes_logical": m.bytes_logical,
            "bytes_allocated": m.bytes_allocated,
            "bytes_git": m.bytes_git_logical,
            "bytes_worktree": m.bytes_worktree_logical,
            "loose_objects": m.loose_objects,
            "packs": m.packs,
        },
    ),
    Reading(
        key="revisions",
        translation_key="revisions",
        # `measurement`, not `total_increasing`: `forget` takes states
        # away, and a counter declared to only ever rise would look to
        # Home Assistant like an overflow every time one runs.
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda m: m.revisions,
        extra=lambda m, secret, daily: {
            "busiest": max((d.revisions for d in m.dashboards), default=0),
            "median": _median([d.revisions for d in m.dashboards]),
            "oldest": (
                datetime.fromtimestamp(m.oldest, UTC).isoformat() if m.oldest else None
            ),
        },
    ),
    Reading(
        key="dashboards",
        translation_key="dashboards",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda m: sum(1 for d in m.dashboards if not d.gone),
        extra=lambda m, secret, daily: {
            "gone": sum(1 for d in m.dashboards if d.gone),
            "ever": len(m.dashboards),
            # The lookup table, and the reason it lives on an entity
            # rather than in the report: attributes stay on this
            # installation. Somebody asked about `a3f81c92` looks here
            # and knows which dashboard is meant. Every dashboard ever,
            # the deleted ones included - they have a row in the report
            # too, and those are the ones worth asking about.
            "ids": {report.dashboard_id(d.key, secret): d.key for d in m.dashboards},
        },
    ),
    Reading(
        key="versions",
        translation_key="versions",
        state_class=SensorStateClass.MEASUREMENT,
        value=lambda m: m.versions,
        extra=lambda m, secret, daily: {
            "daily_versions": daily,
            "most": max((d.versions for d in m.dashboards), default=0),
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Put the five readings up."""
    coordinator: MeasurementCoordinator = hass.data[DOMAIN]["coordinator"]
    add(HistoryReading(coordinator, entry, reading) for reading in READINGS)


class HistoryReading(CoordinatorEntity[MeasurementCoordinator], SensorEntity):
    """One measured number, with its detail beside it."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    entity_description: Reading

    def __init__(
        self,
        coordinator: MeasurementCoordinator,
        entry: ConfigEntry,
        reading: Reading,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = reading
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{reading.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Dashboard History",
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self):
        """The number, or None until the first measurement is in.

        None rather than "unavailable" on an empty history: zero states
        recorded is an answer, not a failure. Only a measurement that
        has not happened yet shows nothing.
        """
        if self.coordinator.data is None:
            return None
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return self.entity_description.extra(
            self.coordinator.data,
            report_secret(self.hass, self._entry),
            self._entry.options.get(OPTION_DAILY_VERSIONS, True),
        )
```

- [ ] **Schritt 3: Die Plattform anmelden und ihren Abbau einbauen**

Erst jetzt, weil es `sensor.py` erst jetzt gibt. In `async_setup_entry`, hinter `await panel.async_register(hass)`:

```python
    # The platform goes up, the first refresh is not waited for. The
    # reason is two screens further down in this file: the opening pass
    # was moved into a background task on 2026-09-07 because it cost
    # 6.2 s of a 7.3 s setup and Home Assistant said so in the log.
    # Sensors that read `unknown` for a minute are harmless; a start
    # that waits for a directory walk is not.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
```

`PLATFORMS` jetzt zu den Importen aus `.const` hinzufügen.

Und `async_unload_entry` vollständig ersetzen:

```python
async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Tear the integration down.

    The platform goes first and the runtime data only if it went: the
    entities read from `hass.data`, so emptying it before they are gone
    leaves them reading into nothing. This is the first entity platform
    of this integration, which is why there was no unload for one until
    now - without it, a reload leaves entities and an event listener
    hanging on a store nobody uses any more.

    The listener itself needs nothing here. It was registered through
    `entry.async_on_unload`, so Home Assistant drops it at exactly this
    point, and a second place to remember it is a second place to forget
    it.
    """
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    panel.async_unregister(hass)
    data = hass.data.pop(DOMAIN, None)
    if data and (milestones := data.get("milestones")) is not None:
        milestones.async_disarm()
    if data and (capture := data.get("capture")) is not None:
        await capture.async_stop()
    return True
```

- [ ] **Schritt 4: Die Namen übersetzen**

In `strings.json` **und** `translations/en.json` denselben Block ergänzen, auf oberster Ebene neben `config` und `options`:

```json
  "entity": {
    "sensor": {
      "last_capture": { "name": "Last capture" },
      "size": { "name": "Size" },
      "revisions": { "name": "Recorded states" },
      "dashboards": { "name": "Dashboards" },
      "versions": { "name": "Versions" }
    }
  }
```

- [ ] **Schritt 5: Gegen die laufende Anlage prüfen**

Neue Python-Dateien und ein geändertes `__init__.py`, also erst **Container neu starten**.

```bash
python3 tests/integration/run_checks.py
```

Erwartet: `0 failed`. Danach von Hand in der Oberfläche nachsehen: *Einstellungen → Geräte & Dienste → Dashboard History* zeigt ein Gerät mit fünf Diagnose-Entitäten, und *Entwicklerwerkzeuge → Zustände* zeigt am Sensor »Dashboards« das Attribut `ids`.

- [ ] **Schritt 6: Committen**

```bash
git add custom_components/dashboard_history/sensor.py \
        custom_components/dashboard_history/report.py \
        custom_components/dashboard_history/coordinator.py \
        custom_components/dashboard_history/strings.json \
        custom_components/dashboard_history/translations/en.json \
        custom_components/dashboard_history/__init__.py
git commit -m "Show what the history costs, as five diagnostics"
```

---

## Aufgabe 8: Der Download

**Dateien:**
- Erstellen: `custom_components/dashboard_history/diagnostics.py`

**Schnittstellen:**
- Benutzt: `MeasurementCoordinator`, `report_secret`, `report.build`.

- [ ] **Schritt 1: `diagnostics.py` schreiben**

```python
"""The `data` block of a diagnostics download.

Fifteen lines, and that is the design: everything worth testing lives in
`report.py`, which imports no Home Assistant and is therefore reachable
from plain `pytest`.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import report
from .const import DOMAIN, OPTION_DAILY_VERSIONS
from .coordinator import MeasurementCoordinator, report_secret


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Measure again, then report what the sensors now show.

    `async_refresh` and not `async_request_refresh`: the debounced form
    would only add delay here. A diagnostics download is a rare,
    deliberate act, and a directory walk for it is affordable.

    Reading `coordinator.data` afterwards is what makes the promise true
    that the sensors show what the file says - the entities are written
    from this same refresh. Measuring separately would leave the two
    disagreeing by one interval.
    """
    coordinator: MeasurementCoordinator = hass.data[DOMAIN]["coordinator"]
    await coordinator.async_refresh()

    # None where no measurement has ever succeeded - a download in the
    # first seconds after a start, or a store that cannot be read at
    # all. `report.build` turns that into empty totals rather than into
    # zeros, because zeros are what a real but empty history looks like.
    return report.build(
        coordinator.data,
        report_secret(hass, entry),
        daily_versions=entry.options.get(OPTION_DAILY_VERSIONS, True),
        # The coordinator's own timestamp. `DataUpdateCoordinator` has
        # no `last_update_time` - checked against 2026.8.3 - and it
        # belongs to the numbers in `coordinator.data`, which a failed
        # refresh leaves untouched. So a stale report is dated to when
        # its numbers were taken, not to when somebody asked for them.
        measured_at=coordinator.measured_at,
        # Stale when this refresh did not succeed, however good the
        # numbers underneath still are. A file that carries an obviously
        # old measuring time is usable; one that hides its age is worse
        # than none.
        stale=not coordinator.last_update_success,
    )
```

> **`measurement` ist hier schlicht `coordinator.data`** — `None`, solange nie eine Messung durchkam, sonst die letzte erfolgreiche. Die Unterscheidung »nie gemessen« gegen »leer gemessen« trifft `report.build`, nicht diese Datei; hier eine zweite Fallunterscheidung zu bauen hieße, sie an zwei Stellen richtig halten zu müssen.

- [ ] **Schritt 2: Den Download von Hand holen**

Erst **Container neu starten** — `diagnostics.py` ist neu, und HA sucht das Modul nur beim Einrichten.

```bash
python3 - <<'PY'
import json, requests, pathlib, sys
sys.path.insert(0, "tests/integration")
from run_checks import BASE, token, entry_id
access = token()
body = requests.get(
    f"{BASE}/api/diagnostics/config_entry/{entry_id(access)}",
    headers={"Authorization": f"Bearer {access}"}, timeout=60,
).json()
print(json.dumps(body["data"], indent=2)[:2000])
PY
```

Erwartet: ein `data`-Block mit `schema`, `measured_at`, `stale`, `environment`, `settings`, `totals`, `dashboards` — und in `dashboards` nur IDs.

- [ ] **Schritt 3: Committen**

```bash
git add custom_components/dashboard_history/diagnostics.py
git commit -m "Hand the measurement out as a downloadable report"
```

---

## Aufgabe 9: Was `pytest` strukturell nicht erreicht

**Dateien:**
- Ändern: `tests/integration/run_checks.py`

- [ ] **Schritt 1: Die vier Prüfungen ergänzen**

Am Ende des Prüflaufs, im Stil der vorhandenen `check(...)`-Aufrufe:

```python
def diagnostics(access: str) -> dict:
    """The file a tester would attach to an issue, as downloaded."""
    answer = requests.get(
        f"{BASE}/api/diagnostics/config_entry/{entry_id(access)}",
        headers={"Authorization": f"Bearer {access}"},
        timeout=120,
    )
    return answer.json() if answer.ok else {}


def _strings(value):
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


# -- the measuring ------------------------------------------------------

# Resolved through the registry rather than spelled out. An entity_id is
# derived from the entity's *name*, not from its description key - the
# reading whose key is `revisions` is called "Recorded states" and
# therefore lives at `sensor.dashboard_history_recorded_states`. Writing
# the ids out by hand means renaming a label silently breaks the checks.
readings = entity_ids(access)
check(
    "all five readings are registered",
    set(readings) == {"last_capture", "size", "revisions", "dashboards", "versions"},
    f"got {sorted(readings)}",
)

# The secret is observed through its effect, not read out: no API hands
# out `entry.data`. `stored_daily_versions` had to learn the same thing
# on 2026-09-05 about `entry.options` - the entry endpoint returns
# seventeen fields and neither of those two among them.
#
# Before the first download, and that is the point of asking here: the
# id mapping needs the secret at the *first refresh*, long before
# anybody asks for a file. Asked after the download it would prove
# nothing, because the download makes one too.
before_ids = entity_attributes(access, readings["dashboards"]).get("ids", {})
check(
    "the ids exist before any report was downloaded",
    bool(before_ids)
    and all(
        len(i) == 8 and all(c in "0123456789abcdef" for c in i) for i in before_ids
    ),
    f"ids={sorted(before_ids)[:3]}",
)

names = list(before_ids.values())
# Without this the privacy check below passes on an empty mapping, which
# is the one case where it proves nothing at all.
check(
    "there is at least one dashboard to be careless with",
    bool(names),
    f"ids={names}",
)

downloaded = diagnostics(access)
body = downloaded.get("data", {})

check(
    "the report carries all four blocks",
    {"environment", "settings", "totals", "dashboards"} <= set(body),
    f"got {sorted(body)}",
)

# The whole downloaded file, not just the part we built. The pytest case
# cannot see Home Assistant's envelope - it does not exist there - and
# the envelope is exactly what the first draft of the spec overlooked.
# A test that checks only what you built yourself would not have found it.
haystack = "\n".join(_strings(downloaded))
leaked = [name for name in names if name and name in haystack]
check(
    "no dashboard name appears anywhere in the downloaded file",
    not leaked,
    f"leaked={leaked}",
)

states = {key: entity_state(access, entity) for key, entity in readings.items()}
check(
    "the sensors show what the report says",
    str(body["totals"]["revisions"]) == states["revisions"]
    and str(body["totals"]["dashboards_live"]) == states["dashboards"],
    f'report={body["totals"]["revisions"]}/{body["totals"]["dashboards_live"]} '
    f'sensors={states["revisions"]}/{states["dashboards"]}',
)

# -- and what a reload leaves behind ------------------------------------

reload_entry(access)

after = entity_ids(access)
check(
    "a reload leaves exactly the five readings, none orphaned",
    set(after) == set(readings)
    and count_entities(access, "sensor.dashboard_history") == 5,
    f"{sorted(after)} / {count_entities(access, 'sensor.dashboard_history')}",
)
check(
    "the ids survive a reload unchanged",
    entity_attributes(access, after["dashboards"]).get("ids", {}) == before_ids,
    "a changed id means a new secret was made where one existed",
)

# Counting entities is not enough: a listener left hanging on the old
# store would still be subscribed, and a coordinator left behind would
# still be running. What proves the wiring is intact is that a *new*
# change still moves the timestamp - and a second listener would show up
# as a doubled measurement, which the revision count would disagree with.
stamp_before = entity_state(access, after["last_capture"])
revisions_before = int(entity_state(access, after["revisions"]))
asyncio.run(touch_probe(access))
time.sleep(5)
check(
    "after a reload a recorded change still moves the timestamp",
    entity_state(access, after["last_capture"]) != stamp_before,
    f"still {stamp_before}",
)
check(
    "and it moves it exactly once",
    int(entity_state(access, after["revisions"])) == revisions_before + 1,
    f"{revisions_before} -> {entity_state(access, after['revisions'])}",
)

Dazu die Helfer, neben die vorhandenen gesetzt:

```python
def entity_ids(access: str) -> dict[str, str]:
    """This integration's readings, by the key in their unique id.

    Through the entity registry rather than by writing the ids out,
    because an entity_id is derived from the entity's *name* and not
    from its description key: the reading keyed `revisions` is called
    "Recorded states" and therefore lands at
    `sensor.dashboard_history_recorded_states`. Ids written by hand
    would break silently the first time a label is reworded.

    `config/entity_registry/list` does carry `unique_id`, although the
    websocket module never mentions the word - the field comes out of
    `RegistryEntry.as_partial_dict`. Checked against 2026.8.3 rather
    than grepped for.
    """
    identifier = entry_id(access)

    async def ask() -> list:
        async with Socket(access) as socket:
            return await socket.call("config/entity_registry/list")

    prefix = f"{identifier}_"
    return {
        row["unique_id"][len(prefix):]: row["entity_id"]
        for row in asyncio.run(ask())
        if row.get("config_entry_id") == identifier
        and str(row.get("unique_id", "")).startswith(prefix)
    }


def _state(access: str, entity_id: str) -> dict:
    """One entity as Home Assistant reports it, or an empty dict."""
    answer = requests.get(
        f"{BASE}/api/states/{entity_id}",
        headers={"Authorization": f"Bearer {access}"},
        timeout=30,
    )
    return answer.json() if answer.ok else {}


def entity_state(access: str, entity_id: str) -> str | None:
    return _state(access, entity_id).get("state")


def entity_attributes(access: str, entity_id: str) -> dict:
    return _state(access, entity_id).get("attributes", {})


def count_entities(access: str, prefix: str) -> int:
    """How many entities carry this prefix."""
    answer = requests.get(
        f"{BASE}/api/states",
        headers={"Authorization": f"Bearer {access}"},
        timeout=60,
    )
    if not answer.ok:
        return 0
    return sum(1 for state in answer.json() if state["entity_id"].startswith(prefix))


def diagnostics(access: str) -> dict:
    """The file a tester would attach to an issue, as downloaded."""
    answer = requests.get(
        f"{BASE}/api/diagnostics/config_entry/{entry_id(access)}",
        headers={"Authorization": f"Bearer {access}"},
        timeout=120,
    )
    return answer.json() if answer.ok else {}


def _strings(value):
    """Every string anywhere in the structure, keys included."""
    if isinstance(value, dict):
        for key, item in value.items():
            yield key
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)
    elif isinstance(value, str):
        yield value


async def touch_probe(access: str) -> None:
    """Record one more change, on the probe dashboard this script owns.

    `dh-probe-check` and nothing else - by its exact name. A test that
    deletes or rewrites by prefix swept up somebody's real dashboard on
    2026-09-01, and the comment at that call site says why that stays
    remembered.
    """
    async with Socket(access) as socket:
        await socket.call(
            "lovelace/config/save",
            url_path="dh-probe-check",
            config={
                "views": [
                    {
                        "path": "probe",
                        "title": "Probe",
                        "cards": [
                            {"type": "heading", "heading": "Nach dem Reload"},
                            {"type": "tile", "entity": "sun.sun"},
                        ],
                    }
                ]
            },
        )
        await _wait_until_recorded(socket, "dh-probe-check")
```

> `touch_probe` setzt voraus, dass `dh-probe-check` existiert — das Skript legt es weiter oben selbst an (Zeile 640 ff.), und dieser Abschnitt läuft danach. Falls die Reihenfolge einmal umgestellt wird, muss dieser Block mitwandern.

- [ ] **Schritt 2: Laufen lassen**

Hier reicht der Container, wie er steht — `run_checks.py` läuft außerhalb und hat sich als einziges geändert.

```bash
python3 tests/integration/run_checks.py
```

Erwartet: `0 failed`, zehn neue `ok`-Zeilen.

Schlägt »the sensors show what the report says« fehl, ist die Reihenfolge in `diagnostics.py` falsch herum — `async_refresh` muss **vor** dem Lesen von `coordinator.data` stehen (B10).

- [ ] **Schritt 3: Committen**

```bash
git add tests/integration/run_checks.py
git commit -m "Check the file that leaves the house, not just ours"
```

---

## Aufgabe 10: Was die Leute lesen

**Dateien:**
- Ändern: `CLAUDE.md`, `README.md`, `docs/superpowers/status.md`

- [ ] **Schritt 1: `CLAUDE.md` — `report.py` auf die Liste**

Die harte Regel nennt heute sechs Module. `report.py` gehört dazu:

> **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py`, `store.py`, `report.py`, and `keys.py` stay free of Home Assistant.**

- [ ] **Schritt 2: `README.md` — die Bitte an Tester**

> **Hier ist eine Rückfrage fällig.** Der Wortlaut ist eine öffentliche Äußerung in einem öffentlichen Repository. Vorher zeigen.

Der Abschnitt muss drei Dinge sagen und nicht mehr:

1. **Wie man den Bericht erzeugt** — Einstellungen → Geräte & Dienste → Dashboard History → Diagnose herunterladen.
2. **Was er enthält und was nicht** — Zahlen über die Historie, Dashboards nur als IDs; keine Namen, keine Titel, keine Inhalte.
3. **Was Home Assistant selbst beilegt** — Systeminformationen einschließlich Zeitzone, und die Liste aller installierten Custom-Integrationen. Wer das nicht mitschicken möchte, kopiert den `data`-Block heraus und schickt nur den; darin steht alles, worauf es ankommt.

Punkt 3 ist der, den ein Hinweis leicht unterschlägt, und genau der, den ein Tester im Nachhinein übelnehmen würde.

- [ ] **Schritt 3: `status.md` nachziehen**

Zeile B von »Spec geschrieben, noch nicht gebaut« auf »Erledigt« setzen und auf diesen Plan verweisen. Die Modulübersicht um `report.py`, `coordinator.py`, `sensor.py` und `diagnostics.py` ergänzen. Und — falls Aufgabe 4 eine Zahl geliefert hat, die es wert ist — das gemessene Intervall dort vermerken, wo die übrigen Laufzeiten stehen.

Vorhaben C steht damit nicht auf »begonnen«: Es wartet jetzt nicht mehr auf B, sondern auf Messwerte von Testern. Das ist ein anderer Zustand und gehört so hingeschrieben.

- [ ] **Schritt 4: Committen**

```bash
git add CLAUDE.md README.md docs/superpowers/status.md
git commit -m "Say how to send numbers back, and what goes with them"
```

---

## Was am Ende wahr sein muss

- `python3 -m pytest tests/ -q` — `0 failed`.
- `python3 tests/integration/run_checks.py` — `0 failed`, mit den zehn neuen Zeilen, **nach einem Container-Neustart** und nicht nach einem blossen Reload.
- Auf der Integrationsseite steht ein Gerät mit fünf Diagnose-Entitäten.
- Ein Diagnose-Download enthält im `data`-Block keinen einzigen Dashboard-Namen.
- Ein Reload hinterlässt genau fünf Entitäten, und eine danach erfasste Änderung bewegt den Zeitstempel **genau einmal** — das ist der Nachweis gegen einen zweiten Listener, den blosses Zählen nicht erbringt.
- `import homeassistant` kommt in `store.py` und `report.py` nicht vor:
  ```bash
  grep -l "import homeassistant" custom_components/dashboard_history/{store,report,yaml_io,analyze,restore,versions,keys}.py
  ```
  Erwartet: keine Ausgabe.
