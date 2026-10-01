# Ungespeicherte Änderungen in der Dashboard-Liste – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Jedes Dashboard in der Liste links, dessen neueste Änderung noch von keiner Version getragen wird, bekommt einen orangen Streifen und ein kleines Zähl-Chip mit der Zahl der Änderungen seit der letzten Version – in Simple und Advanced, auch ohne Auswahl, und der Streifen bleibt orange, wenn das Dashboard ausgewählt ist (GitHub Issue #49).

**Architecture:** Drei Aufgaben. Aufgabe 1 (Server) ergänzt `HistoryStore.unversioned_counts()`: je Dashboard die Position der neuesten versionierten Änderung im bereits vorhandenen `RevisionIndex` (HEAD-gecacht), und das Tag-Ziel je Tag in einem kleinen, an die unveränderliche Tag-SHA gebundenen Cache – so kostet die Frage nach einem neuen oder entfernten Tag keine Neulesung aller Tag-Objekte. Index und Tag-Refs sind zwei getrennte Lesungen; damit sie nach Entscheidung 24 keine zwei Generationen eines gleichzeitigen `forget` mischen, läuft die Zählung im vorhandenen `_retrying_a_forget_race`, und `async_dashboards` bekommt Namen (`survey`) **und** Zähler aus einem einzigen Store-Aufruf `dashboard_listing()` mit demselben Rennschutz. Das Ergebnis erscheint als Feld `unversioned` (Ganzzahl, 0 = aufgeräumt) je Eintrag. Aufgabe 2 (Panel) liest dieses Feld in `_renderDashboard`, setzt die Klasse `untidy` und das Chip und ergänzt zwei CSS-Regeln. Aufgabe 3 ist die Gesamtprüfung samt Messung und Prüfung im Testcontainer.

**Review-Stand:** Dieser Plan wurde am 2026-10-01 von vier unabhängigen Läufen geprüft (Codex Terra und Astra, Gemini Terra und Astra; `reviews/2026-10-01-issue-49-plan-review-terra.md`, `-astra.md`, `-terra-gemini.md`, `-astra-gemini.md`). Alle vier fanden dasselbe kritische Problem (zwei getrennte Lesungen mischen Generationen bei einem gleichzeitigen `forget`, Entscheidung 24); es ist in dieser Fassung behoben und durch zwei deterministische Tests abgesichert. Die weiteren Befunde sind an den betroffenen Stellen eingearbeitet.

**Tech Stack:** Python 3.12+ (dulwich, `store.py` bleibt frei von Home Assistant), plain Custom Element ohne Build-Schritt, pytest mit Node-Stand-in für Panel-Logik.

**Spec:** Kein eigenes Spec-Dokument. Bindend ist Issue #49 (Anzeige, Ziel) und dieser Plan. Die Spec `specs/2026-08-30-dashboard-history-design.md` bleibt bei Widersprüchen bindend; berührt sind nur ihre harten Regeln (siehe Global Constraints).

## Entscheidungen, die dieser Plan trifft (und warum)

- **Definition von »untidy«: die neueste aufgezeichnete Änderung des Dashboards trägt keine Version.** Das ist dieselbe Frage, die die »Right now«-Karte stellt (»The dashboard has changed since vX«). Eine Sonderregel für automatische Versionen gibt es nicht und braucht es nicht: Eine Tagesmarke wird beim ersten Speichern des *folgenden* Tages auf den letzten Stand des *Vortags* gesetzt (`milestones.py::_async_mark_day`, `versions.py::end_of_previous_day`), liegt also nie auf dem neuesten Stand. Das initiale `v1.0.0` (der »Floor«) sitzt auf dem ältesten Stand; ein Dashboard mit genau diesem einen Stand ist aufgeräumt, jede weitere Änderung macht es orange.
- **Der Zähler zählt aufgezeichnete Änderungen, nicht Netto-Unterschiede.** Eine Karte fünfmal hoch und runter geschoben ergibt 5. Das ist dieselbe Zählung, nach der die History-Liste Zeilen zeigt. Der Zähler ist die Position der neuesten versionierten Änderung in `index.by_key[key]` (neueste zuerst); ohne jede Version ist es die Gesamtzahl.
- **Gelöschte Dashboards bekommen nie Streifen oder Chip** (`exists` ist falsch → 0). Dashboards unter »Not in the sidebar« bekommen sie, denn sie sind genauso unversioniert.
- **Rennschutz gegen `forget` (Entscheidung 24, bindend):** Der Zähler braucht zwei getrennte Lesungen (Index, dann Tag-Refs). Läuft ein `forget` dazwischen vollständig durch, trägt jeder überlebende Commit eine neue SHA; der Zähler verglich dann alte Revisionen mit neuen Tag-Zielen und lieferte stillschweigend »alles unversioniert« (von zwei Reviewern mit einem Hook reproduziert: `{'gone': 2, 'home': 1}` statt `{'home': 0}`). `_naming_a_forget_race` hilft nicht, es prüft erfolgreiche Antworten nicht. Deshalb läuft die Zählung im vorhandenen `HistoryStore._retrying_a_forget_race` (HEAD- und Checkpoint-Prüfung, höchstens drei Versuche), dessen Typannotation dafür von `list[Change]` auf einen `TypeVar` verallgemeinert wird. Ein Ergebnis aus zwei Aufrufen (`survey` und Zähler) hätte dieselbe Lücke zwischen den Aufrufen; deshalb ein einziger Store-Aufruf `dashboard_listing()`.
- **Nicht Teil dieses Plans:** Vergleich der Live-Konfiguration mit HEAD (`same_as_now`), ein Filter oder eine Sortierung nach »untidy«, ein Zähler in der »Right now«-Karte, ein Eintrag im CHANGELOG (der entsteht beim Release), Änderungen an `_refresh`/Events.
- **Warum an `_refresh` nichts zu ändern ist:** `_refresh` (`panel.js`, Zeile ~1051) lädt bei jedem Schreibvorgang (`_reloadAfterWrite`) und bei jeder aufgezeichneten Änderung (`_onRecorded`) die Dashboard-Liste neu, `_onRecorded` für fremde Dashboards über `_loadDashboardsQuietly`. Ein neues oder entferntes Tag und eine neue Änderung erreichen die Liste damit ohnehin; der Server muss nur das frische Feld liefern, also darf das Ergebnis **nicht** an HEAD gecacht werden (ein Tag verschiebt HEAD nicht).

## Global Constraints

- **Sprache:** Code, Kommentare, Docstrings, Log-Meldungen, Commit-Messages englisch. Dieser Plan ist deutsch (Projekt-Konvention für `docs/superpowers/`).
- **Kein `git`-Aufruf im Produktcode, nur `dulwich`.** Keine Änderung an Home-Assistant-Interna.
- **`store.py` bleibt frei von Home Assistant** (`lint-imports` prüft das). Die neue Methode steht in `store.py`, nicht in `operations.py`.
- **Blockierende Arbeit gehört in einen Executor:** `operations.async_dashboards` ruft `store.unversioned_counts` über `hass.async_add_executor_job` auf, nie direkt.
- **Nichts blockiert den HA-Start.** `unversioned_counts()` und `dashboard_listing()` antworten bei fehlendem Repository oder fehlendem HEAD (frisch angelegtes, noch leeres Repository) leer (`{}` beziehungsweise leerer `Survey`). Einen Zustand »Index noch nicht gebaut« gibt es nicht: `_revision_index` baut ihn synchron, ein zweiter Leser wartet am Lock; `None` heißt dort »kein HEAD«.
- **Leseaufrufe, die zwei Store-Lesungen verbinden, laufen im Rennschutz** (`_retrying_a_forget_race`, Entscheidung 24) – nie als zwei getrennte Executor-Jobs hintereinander.
- **Keine Backticks und kein `${` in `style.js`** – geprüft durch `tests/test_panel_assets.py::test_the_style_is_one_unbroken_template_literal` und `::test_no_substitution_hides_in_the_stylesheet`. Auch nicht in CSS-Kommentaren.
- **`tools/complexity_ratchet.py` und `lint-imports` bleiben grün.** `async_dashboards` steht nicht in `tools/complexity-baseline.json`; keine Funktion darf neu hineinwandern. Die Baseline wird **nicht** angefasst.
- **Kein Test mit Zeitgrenze.** Messungen werden berichtet, nicht als Assertion festgeschrieben (vgl. Commit 7d4893b: flaky Obergrenzen).
- **Kein bestehender Test wird geändert.**
- **Arbeit auf einem Branch** `issue-49-unversioned-marker`, nicht auf `main`. Zwei Commits (je Aufgabe 1 und 2), Aufgabe 3 committet nichts.
- **Commits:** Englisch, Imperativ im Subject, höchstens 50 Zeichen, Leerzeile, Body mit dem *Warum*, höchstens 72 Zeichen je Zeile, Schluss `Refs #49.` (der letzte Commit, Aufgabe 2, `Closes #49.`). Eine Commit-Message darf nur behaupten, was dieser Commit tatsächlich ändert.
- **Kein Push, kein Tag, kein Merge** ohne ausdrückliches Go des Nutzers.
- Die Umsetzung bekommt **keine uncommitteten lokalen Änderungen** als Voraussetzung: Ausgangspunkt ist `main` am Commit `4f8fd3a` oder neuer, Arbeitsbaum sauber.

## Review Focus

Eingaben und Zustände, die der Plan nicht von selbst durch einen Aufgaben-Test abdecken würde – am wahrscheinlichsten zuerst. Jede Zeile hat unten einen Test.

1. **Ein `forget` läuft zwischen dem Lesen des Index und dem Lesen der Tag-Refs durch.** Erwartet: die Antwort gehört vollständig einer Generation (`{'home': 0}`), nicht »alles unversioniert«; ebenso liefert `dashboard_listing()` Namen und Zähler derselben Generation. Aufgabe 1: `test_a_forget_between_the_two_reads_cannot_mix_generations`, `test_the_listing_never_mixes_names_and_counts_of_two_generations`.
2. **Ein Tag kommt hinzu oder fällt weg, ohne dass HEAD sich bewegt.** Erwartet: der nächste Aufruf sieht es (kein Cache an HEAD). Aufgabe 1: `test_a_new_version_is_seen_on_the_next_call`, `test_a_removed_version_is_noticed_on_the_next_call`.
3. **Version auf einer älteren Änderung.** Erwartet: gezählt wird nur, was neuer ist. Aufgabe 1: `test_only_changes_newer_than_the_newest_version_count`.
4. **Das Tag eines anderen Dashboards zeigt auf einen Commit dieses Dashboards.** Erwartet: es zählt nicht für dieses Dashboard (ein Tag gehört dem Schlüssel, nach dem es heißt). Aufgabe 1: `test_another_dashboards_version_does_not_tidy_this_one`.
5. **Kein Repository; angelegtes, aber noch leeres Repository (kein HEAD).** Erwartet: leer, keine Ausnahme. Aufgabe 1: `test_a_store_without_a_repository_answers_nothing`, `test_a_repository_without_a_commit_answers_nothing`.
6. **Mehrere Tags auf demselben Commit.** Erwartet: wie ein Tag. Aufgabe 1: `test_two_versions_on_one_state_count_once`.
7. **Der Tag-Cache wird versehentlich abgeschaltet.** Erwartet: ein unveränderter Tag wird beim zweiten Aufruf nicht noch einmal aus dem Objektspeicher gelesen. Aufgabe 1: `test_an_unchanged_version_is_not_read_again`.
8. **Die Verkabelung bis zur WebSocket-Antwort.** Erwartet: ein Wert, der stimmt, nicht nur irgendeine Ganzzahl (Version auf dem neuesten Stand ergibt 0, nach dem Entfernen die erwartete Zahl) und 0 für ein tatsächlich gelöschtes Dashboard. Aufgabe 1, Schritt 8 (`run_checks.py`).
9. **Gelöschtes Dashboard, Chip mit `unversioned > 0` im Datensatz.** Erwartet: weder Streifen noch Chip. Aufgabe 2: `test_a_deleted_dashboard_never_carries_the_mark`.
10. **Server ohne das neue Feld (älteres Backend, Test-Daten ohne `unversioned`).** Erwartet: kein Streifen, kein Chip, kein Fehler. Aufgabe 2: `test_a_dashboard_the_server_gave_no_count_for_carries_no_mark`.
11. **Ausgewähltes, ungespeichertes Dashboard.** Erwartet: `aria-current="true"` **und** `untidy` am selben Knoten, und die CSS-Regel für Orange schlägt die für Blau. Aufgabe 2: `test_the_selected_dashboard_keeps_the_mark`, `test_the_orange_rule_comes_after_the_blue_one`.
12. **Der Text für Screenreader am Chip.** Erwartet: vorhanden und mit dem richtigen Inhalt. Aufgabe 2: `test_the_chip_is_read_out_in_words`.

---

## Aufgabe 1: Server – `unversioned_counts`, `dashboard_listing` und das Feld `unversioned`

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (Import von `TypeVar` und `_T` am Dateianfang; Typannotation von `_retrying_a_forget_race`, Zeile ~2523; neues Attribut in `__init__` bei Zeile ~644; vier neue Methoden direkt nach `survey`, also nach `return found` bei Zeile ~3443)
- Modify: `custom_components/dashboard_history/operations.py:406-435` (`async_dashboards`)
- Modify: `tests/integration/run_checks.py` (drei Stellen, Schritt 8)
- Test: `tests/test_unversioned.py` (neu)

**Interfaces:**
- Consumes: `HistoryStore._repo()`, `HistoryStore._revision_index(repo)` (liefert `RevisionIndex` mit `by_key: dict[str, list[str]]`, neueste zuerst, oder `None` ohne HEAD), `HistoryStore.survey()`, `HistoryStore._retrying_a_forget_race(repo, build)`, `_as_text`, `Survey`, `Repo.refs.as_dict(b"refs/tags")`.
- Produces:
  - `HistoryStore.unversioned_counts(self) -> dict[str, int]` – je Schlüssel mit aufgezeichneten Änderungen die Zahl der Änderungen **neuer** als die neueste von diesem Schlüssel versionierte (0 = die neueste trägt eine Version); ohne Version die Gesamtzahl. `{}` ohne Repository oder ohne HEAD. Läuft im Rennschutz gegen `forget`.
  - `HistoryStore.dashboard_listing(self) -> tuple[Survey, dict[str, int]]` – `survey()` und die Zähler aus **einem** Rennschutz-Durchlauf, also aus derselben Generation. Ohne Repository `(Survey([], set(), {}), {})`.
  - `HistoryStore._count_unversioned(self, repo) -> dict[str, int]` – die Zählung ohne Rennschutz; nur von den beiden obigen aufgerufen.
  - `HistoryStore._marked_revisions(self, repo) -> dict[str, set[str]]` – Schlüssel → Menge der Commits, die eines seiner Tags tragen.
  - `HistoryStore._retrying_a_forget_race` ist generisch: `build: Callable[[], _T]` → `_T`. Verhalten unverändert.
  - WebSocket-Antwort `dashboard_history/dashboards`: jeder Eintrag bekommt `"unversioned": int` (nur für lebende Dashboards > 0, sonst 0).

- [ ] **Schritt 1: Branch anlegen**

```bash
git switch -c issue-49-unversioned-marker
git status --short
```
Erwartet: leere Ausgabe von `status` (sauberer Baum).

- [ ] **Schritt 2: Die fehlschlagenden Tests schreiben**

Neue Datei `tests/test_unversioned.py`:

```python
"""Tests for how many changes a dashboard holds that no version carries."""

import pytest
from dulwich.repo import Repo
from store import HistoryStore


@pytest.fixture
def store(tmp_path):
    s = HistoryStore(tmp_path / "history")
    s.ensure()
    return s


def test_a_store_without_a_repository_answers_nothing(tmp_path):
    nothing = HistoryStore(tmp_path / "nothing")
    assert nothing.unversioned_counts() == {}
    survey, counts = nothing.dashboard_listing()
    assert survey.names == [] and survey.live == set()
    assert counts == {}


def test_a_repository_without_a_commit_answers_nothing(store):
    # `ensure()` made the repository, nothing has been recorded yet: no
    # HEAD, so no index to read. Not the same case as no repository.
    assert store.unversioned_counts() == {}
    survey, counts = store.dashboard_listing()
    assert survey.names == [] and counts == {}


def test_without_any_version_every_change_counts(store):
    store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("home", "a: 2\n", "second")
    store.write_snapshot("home", "a: 3\n", "third")
    assert store.unversioned_counts() == {"home": 3}


def test_a_version_on_the_newest_change_leaves_nothing_unversioned(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", newest)
    assert store.unversioned_counts() == {"home": 0}


def test_only_changes_newer_than_the_newest_version_count(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    second = store.write_snapshot("home", "a: 2\n", "second")
    store.write_snapshot("home", "a: 3\n", "third")
    store.write_snapshot("home", "a: 4\n", "fourth")
    store.create_version("home/v1.0.0", "First", "", first)
    store.create_version("home/v1.0.1", "Second", "", second)
    # Two states sit in front of the newest version, not three: the
    # older version does not add to it.
    assert store.unversioned_counts() == {"home": 2}


def test_dashboards_are_counted_apart(store):
    home = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    store.write_snapshot("other", "b: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", home)
    assert store.unversioned_counts() == {"home": 0, "other": 2}


def test_another_dashboards_version_does_not_tidy_this_one(store):
    home = store.write_snapshot("home", "a: 1\n", "first")
    store.write_snapshot("other", "b: 1\n", "first")
    # A tag belongs to the key in its name, wherever it points.
    store.create_version("other/v1.0.0", "Odd", "", home)
    assert store.unversioned_counts()["home"] == 1


def test_two_versions_on_one_state_count_once(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "One", "", newest)
    store.create_version("home/v1.0.1", "Two", "", newest)
    assert store.unversioned_counts() == {"home": 0}


def test_a_new_version_is_seen_on_the_next_call(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    assert store.unversioned_counts() == {"home": 2}
    # HEAD did not move between the two calls: a tag does not move it.
    store.create_version("home/v1.0.0", "First", "", newest)
    assert store.unversioned_counts() == {"home": 0}


def test_a_removed_version_is_noticed_on_the_next_call(store):
    store.write_snapshot("home", "a: 1\n", "first")
    newest = store.write_snapshot("home", "a: 2\n", "second")
    store.create_version("home/v1.0.0", "First", "", newest)
    assert store.unversioned_counts() == {"home": 0}
    store.remove_version("home", "home/v1.0.0")
    assert store.unversioned_counts() == {"home": 2}


def test_a_change_after_the_version_is_counted(store):
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    assert store.unversioned_counts() == {"home": 0}
    store.write_snapshot("home", "a: 2\n", "second")
    assert store.unversioned_counts() == {"home": 1}


def test_an_unchanged_version_is_not_read_again(store, monkeypatch):
    # The point of `_tag_targets`: loading every tag object costs half a
    # second at a year of automatic versions, and the panel asks on every
    # recorded change. A refactoring that drops the cache would still pass
    # every test above; this one is what fails.
    first = store.write_snapshot("home", "a: 1\n", "first")
    store.create_version("home/v1.0.0", "First", "", first)
    store.unversioned_counts()  # fills the cache
    tags = set(Repo(str(store.path)).refs.as_dict(b"refs/tags").values())
    assert tags
    looked_up = []
    original = Repo.__getitem__

    def spying(self, name):
        looked_up.append(name)
        return original(self, name)

    monkeypatch.setattr(Repo, "__getitem__", spying)
    store.unversioned_counts()
    # The spy is live (commits are still looked up through it) and the
    # tag objects are not among what it saw.
    assert looked_up
    assert not tags & set(looked_up)


def _forget_once_between_the_two_reads(store, forgotten):
    """Make a `forget` run exactly between reading the index and the refs.

    The same interruption a second executor thread causes, without a
    thread: the first call of `_marked_revisions` runs `forget` first,
    then reads as usual. Once only, so a retry reads undisturbed.
    """
    original = store._marked_revisions

    def interrupted(repo):
        store._marked_revisions = original
        store.forget(forgotten)
        return original(repo)

    store._marked_revisions = interrupted


def test_a_forget_between_the_two_reads_cannot_mix_generations(store):
    store.write_snapshot("gone", "a: 1\n", "gone")
    home = store.write_snapshot("home", "a: 1\n", "home")
    store.create_version("home/v1.0.0", "First", "", home)
    _forget_once_between_the_two_reads(store, "gone")
    # Without the retry this is {"gone": 1, "home": 1}: the index still
    # holds the commits from before the rewrite, the tags already point
    # at the new ones, and nothing matches.
    assert store.unversioned_counts() == {"home": 0}


def test_the_listing_never_mixes_names_and_counts_of_two_generations(store):
    store.write_snapshot("gone", "a: 1\n", "gone")
    home = store.write_snapshot("home", "a: 1\n", "home")
    store.create_version("home/v1.0.0", "First", "", home)
    _forget_once_between_the_two_reads(store, "gone")
    survey, counts = store.dashboard_listing()
    assert survey.names == ["home"]
    assert counts == {"home": 0}
```

- [ ] **Schritt 3: Prüfen, dass sie fehlschlagen**

Run: `python3 -m pytest tests/test_unversioned.py -v`
Erwartet: alle schlagen mit `AttributeError: 'HistoryStore' object has no attribute 'unversioned_counts'` (beziehungsweise `dashboard_listing`) fehl.

`remove_version(key, name)` nimmt den vollen Tag-Namen (`"home/v1.0.0"`); `_owns` verlangt den Präfix `home/` ohnehin. Die Form im Test ist also die richtige.

- [ ] **Schritt 4: Typannotation, Import und Attribut**

1. In `store.py` oben bei den Imports (Zeile ~104, nach `from pathlib import Path`) ergänzen: `from typing import TypeVar`. Direkt unter `_LOGGER = logging.getLogger(__name__)` (Zeile ~125) ergänzen:

```python
_T = TypeVar("_T")
```

2. `_retrying_a_forget_race` (Zeile ~2523) verallgemeinern: die Signatur wird

```python
    def _retrying_a_forget_race(
        self, repo: Repo, build: Callable[[], _T]
    ) -> _T:
```

Nichts am Rumpf oder am Docstring ändern. Die zwei vorhandenen Aufrufer (`list_changes` bei Zeile ~2437 und `search_changes` bei Zeile ~2984) liefern weiter `list[Change]`.

3. In `HistoryStore.__init__`, direkt unter dem Block von `self._survey` (Zeile ~644) einfügen:

```python
        # Where each tag points, keyed by the tag object's own sha. A
        # sha names one immutable object, so an entry can never go
        # stale - it can only stop being asked for, and
        # `_marked_revisions` rebuilds the whole mapping from the refs
        # that exist on every call, which drops those. Read once per
        # tag instead of once per call: loading every tag object costs
        # 492 ms at 3650 tags (see `_each_tag`), and the panel asks on
        # every recorded change. Replaced as a whole, never mutated, so
        # two executor threads at worst both rebuild it.
        self._tag_targets: dict[bytes, str] = {}
```

- [ ] **Schritt 5: Die vier Methoden schreiben**

In `store.py` direkt nach `survey` (nach dem `return found` bei Zeile ~3443, vor `@_naming_a_forget_race def measure`) einfügen:

```python
    def _marked_revisions(self, repo: Repo) -> dict[str, set[str]]:
        """Which commits carry a version, by the dashboard the version names.

        The owner is read off the ref name, split from the right like
        `_versions_by_key`: a key may hold a slash itself. A tag
        without a slash belongs to no dashboard and is left out.

        The commit a tag points at needs the tag object, which is read
        once per tag and then remembered in `_tag_targets`. A
        lightweight tag is the ref straight to the commit, an annotated
        one points at a tag object whose `object` is the commit - the
        same two shapes `_version_from` tells apart.
        """
        known = self._tag_targets
        current: dict[bytes, str] = {}
        marked: dict[str, set[str]] = {}
        for ref, sha in repo.refs.as_dict(b"refs/tags").items():
            if b"/" not in ref:
                continue
            target = known.get(sha)
            if target is None:
                try:
                    found = repo[sha]
                except KeyError:
                    # Listed a moment ago and gone now: a `forget` is
                    # rewriting the tags. Same skip as `_each_tag`.
                    continue
                target = _as_text(
                    found.object[1] if hasattr(found, "object") else found.id
                )
            current[sha] = target
            owner = ref.rsplit(b"/", 1)[0].decode()
            marked.setdefault(owner, set()).add(target)
        self._tag_targets = current
        return marked

    def _count_unversioned(self, repo: Repo) -> dict[str, int]:
        """The count itself, with no protection against a `forget`.

        Two reads, the index and then the tag refs, and a `forget` that
        completes between them leaves the first holding commits from
        before the rewrite while the second sees tags already pointing
        at the new ones: nothing matches, and every change counts. Only
        ever called from inside `_retrying_a_forget_race`, which is what
        notices and reads both again.
        """
        index = self._revision_index(repo)
        if index is None:
            return {}
        marked = self._marked_revisions(repo)
        counts: dict[str, int] = {}
        for key, revisions in index.by_key.items():
            carrying = marked.get(key, set())
            counts[key] = next(
                (at for at, revision in enumerate(revisions) if revision in carrying),
                len(revisions),
            )
        return counts

    def unversioned_counts(self) -> dict[str, int]:
        """How many changes each dashboard holds that no version carries.

        The position of the newest version-bearing change in the
        dashboard's own revisions, which the index keeps newest first -
        so 0 means the newest change carries a version, and a dashboard
        with no version at all counts every change it has. The question
        the panel's "Right now" card asks, answered for all dashboards
        at once.

        Not cached by HEAD, unlike `survey`: a new or removed version
        does not move HEAD. The revisions come from the index, which is
        cached by HEAD; the tags are listed by ref on every call and
        only their targets are remembered.

        Empty where there is no repository, or nothing recorded yet and
        so no HEAD to build an index at.
        """
        repo = self._repo()
        if repo is None:
            return {}
        return self._retrying_a_forget_race(repo, lambda: self._count_unversioned(repo))

    def dashboard_listing(self) -> tuple[Survey, dict[str, int]]:
        """`survey` and `unversioned_counts` out of one generation.

        Two calls would leave a gap between them for a `forget` to run
        through: names from before the rewrite next to counts from
        after, or the other way round, and no error anywhere. Decision
        24. One attempt reads both, and `_retrying_a_forget_race` reads
        both again if HEAD moved or a `forget` was still unfinished.
        """
        repo = self._repo()
        if repo is None:
            return Survey([], set(), {}), {}
        return self._retrying_a_forget_race(
            repo, lambda: (self.survey(), self._count_unversioned(repo))
        )
```

- [ ] **Schritt 6: Prüfen, dass die Tests bestehen – und dass der Rennschutz sie trägt**

Run: `python3 -m pytest tests/test_unversioned.py -v`
Erwartet: alle bestanden.

Dann **den Test auf Aussagekraft prüfen**: in `unversioned_counts` vorübergehend `return self._retrying_a_forget_race(repo, lambda: self._count_unversioned(repo))` durch `return self._count_unversioned(repo)` ersetzen und `test_a_forget_between_the_two_reads_cannot_mix_generations` laufen lassen. Erwartet: schlägt fehl mit `{'gone': 1}` zu viel in der Antwort. Danach die Zeile **wiederherstellen**. Läuft der Test auch ohne Rennschutz grün, ist er wertlos – melden, nicht weitermachen.

Schlagen die Tests für neue oder entfernte Tags fehl, **nicht** den Test lockern: der Cache oder die Tag-Liste ist falsch. Zuerst prüfen, ob `repo.refs.as_dict(b"refs/tags")` die Refs ohne Präfix liefert (wie `_each_tag` voraussetzt) und ob `sha` als `bytes` ankommt.

- [ ] **Schritt 7: `async_dashboards` den Aufruf und das Feld geben**

In `operations.py`, `async_dashboards` (Zeile ~414), die Zeile `found = await hass.async_add_executor_job(store.survey)` ersetzen durch:

```python
    # One call for the names and the counts: two would leave a gap for a
    # `forget` to run through (decision 24). Not part of `survey` alone,
    # which is cached by HEAD while a version does not move HEAD.
    found, unversioned = await hass.async_add_executor_job(store.dashboard_listing)
```

und im Eintrag (Zeile ~428 ff.) das Feld `"unversioned"` ergänzen:

```python
        dashboards.append(
            {
                "key": key,
                "title": info.get("title") or key,
                "icon": info.get("icon"),
                "exists": exists,
                # Changes no version carries. A dashboard that is gone has
                # nothing left to put a version on, and the panel marks
                # only live ones.
                "unversioned": unversioned.get(key, 0) if exists else 0,
            }
        )
```

Den Docstring von `async_dashboards` um einen Satz ergänzen: dass `unversioned` die Zahl der Änderungen seit der neuesten Version ist.

- [ ] **Schritt 8: Drei Prüfungen in `run_checks.py`**

Dieses Skript läuft gegen die laufende Testinstanz (siehe `docker/README.md`). Es prüft die Verkabelung von `HistoryStore` bis zur WebSocket-Antwort mit Werten, die nur eine richtige Implementierung liefert.

**(a)** Direkt nach der Prüfung `"the panel's dashboard list is populated"` (Zeile ~534-539), nur die Form:

```python
        check(
            "every listed dashboard says how many changes no version carries",
            all(
                isinstance(d.get("unversioned"), int) and d["unversioned"] >= 0
                for d in listed["dashboards"]
            ),
            f"{[d.get('unversioned') for d in listed['dashboards']][:10]}",
        )
```

(Die Form allein beweist keinen Wert; die echten Werte prüft (c).)

**(b)** Beim ohnehin erzeugten Löschfall (Zeile ~747-755, `entry = next(...)` mit `"the panel offers it, under the name it last had"`) die Bedingung um `and entry["unversioned"] == 0` erweitern. Dort ist das Dashboard tatsächlich gelöscht, und die Prüfung ist nicht leer.

**(c)** In `run_remove_version` (Zeile ~3778), das ohnehin eine Version auf `changes[0]` anlegt und wieder entfernt, direkt vor `# The preview:` und nach `name = made.get("created")`/dem `check(... "a version to remove was made" ...)` die Hilfsfunktion und die erste Prüfung einfügen. Die Hilfsfunktion steht neben `listed()` und `remove()`:

```python
        async def unversioned() -> int:
            listing = await socket.call("dashboard_history/dashboards")
            return next(d["unversioned"] for d in listing["dashboards"] if d["key"] == key)
```

```python
        check(
            "the newest state carries the version just made, so nothing is unversioned",
            await unversioned() == 0,
            str(await unversioned()),
        )
```

und nach der Prüfung `"the list no longer holds it"` (nach der Entfernung) die zweite, die den erwarteten Wert aus den verbliebenen Versionen berechnet statt ihn zu raten:

```python
        remaining = {v["revision"] for v in await listed()}
        expected = next(
            (at for at, c in enumerate(changes) if c["revision"] in remaining), None
        )
        # None: no remaining version sits within the page of changes read
        # above, so the true count is beyond it and cannot be told here.
        if expected is not None:
            check(
                "taking the version away counts the changes in front of the next one",
                await unversioned() == expected,
                f"{await unversioned()} vs {expected}",
            )
```

(Die Signatur von `check` ist `check(name, ok, detail="")`, Zeile 114.)

- [ ] **Schritt 9: Die ganze Python-Bank und die zwei Wächter laufen lassen**

```bash
python3 -m pytest tests/ -q -p no:cacheprovider
python3 tools/complexity_ratchet.py
lint-imports
```
Erwartet: `0 failed` (die Gesamtzahl der Tests schwankt mit den echten Dashboards der `.storage`, nur `0 failed` zählt); Ratsche und Importverträge grün. Fehlen `ruff`/`import-linter`, installieren wie in `CLAUDE.md` beschrieben (virtualenv außerhalb des Repos).

Python-Läufe für `store.py` zusätzlich unter 3.13 und 3.14, die CI fährt sie: `~/venvs/dh313/bin/python -m pytest tests/test_unversioned.py tests/test_store.py -q -p no:cacheprovider` und dasselbe mit `dh314`. Existieren die Venvs nicht, im Handover sagen, dass dieser Schritt nicht lief.

- [ ] **Schritt 10: Commit**

```bash
git add custom_components/dashboard_history/store.py \
        custom_components/dashboard_history/operations.py \
        tests/test_unversioned.py tests/integration/run_checks.py
git commit
```

Message:

```
Count the changes no version carries

The list of dashboards could not say which ones have changes that no
version holds; only the selected dashboard knew, through its history.
The count is the position of the newest version-bearing change in the
dashboard's own revisions, which the index already keeps newest first.

Not cached by HEAD, because a new or removed version does not move it.
The tag targets are remembered per tag object sha instead: that sha
names one immutable object, and reading every tag object on each call
costs half a second at a year of automatic versions.

The count reads the index and then the tag refs, and a forget that
completes between the two leaves them in different generations: every
change would count. It runs inside the existing retry for that race,
and the list's names come from the same attempt instead of a second
call (decision 24).

Refs #49.
```

---

## Aufgabe 2: Panel – Streifen, Chip, CSS

**Files:**
- Modify: `custom_components/dashboard_history/panel.js:3203-3210` (`_renderDashboard`)
- Modify: `custom_components/dashboard_history/panel/style.js:399-404` (zwei neue Regeln hinter `.dash[aria-current="true"]`)
- Test: `tests/test_panel_behaviour.py` (Markup-Szenarien am Ende der Datei anhängen), `tests/test_panel_assets.py` (die zwei Stylesheet-Prüfungen; statische Prüfungen gehören dorthin)

**Interfaces:**
- Consumes: das Feld `unversioned` (Ganzzahl) je Eintrag von `this._dashboards` aus Aufgabe 1, `d.exists`, `d.key`, `escape()` (bereits in `panel.js` importiert).
- Produces: `<button class="dash untidy" …>` mit `<span class="pending" …>N<span class="sr"> …</span></span>` für lebende Dashboards mit `unversioned > 0`; sonst unverändertes Markup.

- [ ] **Schritt 1: Die fehlschlagenden Tests schreiben**

Am Ende von `tests/test_panel_behaviour.py` anhängen. Zuerst die Node-Szenarien (der Aufbau folgt `_SIDEBAR_SIDE`/`sidebar_side` bei Zeile ~6800; `_run_in_node` und `PACKAGE` existieren schon):

```python
# The list marks a dashboard whose newest change no version carries:
# an orange stripe and the number of changes since the last version.
_UNTIDY_SIDE = """
const el = new Panel();
el._dashboards = [
  { key: "many", title: "Many", exists: true, unversioned: 3 },
  { key: "one", title: "One", exists: true, unversioned: 1 },
  { key: "clean", title: "Clean", exists: true, unversioned: 0 },
  { key: "old", title: "Old", exists: true },
  { key: "gone", title: "Gone", exists: false, unversioned: 5 },
];
el._selected = "many";
const markup = el._renderSide();
// One entry per button, in the order they are drawn.
const buttons = markup.split("<button").slice(1).map((part) => {
  const head = part.slice(0, part.indexOf(">"));
  return {
    key: /data-key="([^"]+)"/.exec(head)[1],
    untidy: /class="dash[^"]*\\buntidy\\b/.test(head),
    current: /aria-current="true"/.test(head),
    chip: (/<span class="pending"[^>]*>(\\d+)/.exec(part) || [])[1] || null,
    title: (/<span class="pending" title="([^"]*)"/.exec(part) || [])[1] || null,
    sr: (/<span class="sr">([^<]*)<\\/span>/.exec(part) || [])[1] ?? null,
  };
});
console.log(JSON.stringify(Object.fromEntries(buttons.map((b) => [b.key, b]))));
"""


@pytest.fixture(scope="session")
def untidy_side(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "untidy_side", _UNTIDY_SIDE)


def test_a_dashboard_with_unversioned_changes_carries_the_mark(untidy_side):
    assert untidy_side["many"]["untidy"] is True
    assert untidy_side["many"]["chip"] == "3"


def test_the_chip_says_what_the_number_counts(untidy_side):
    assert untidy_side["many"]["title"] == "3 changes not saved as a version yet"
    assert untidy_side["one"]["title"] == "1 change not saved as a version yet"


def test_the_chip_is_read_out_in_words(untidy_side):
    # The visible number is the chip's own text, the hidden words follow
    # it: read together they say "3 changes not saved as a version yet".
    # Without the words a screen reader hears a bare "3" after the title.
    assert untidy_side["many"]["sr"] == " changes not saved as a version yet"
    assert untidy_side["one"]["sr"] == " change not saved as a version yet"


def test_a_clean_dashboard_carries_no_mark(untidy_side):
    assert untidy_side["clean"]["untidy"] is False
    assert untidy_side["clean"]["chip"] is None


def test_a_dashboard_the_server_gave_no_count_for_carries_no_mark(untidy_side):
    # An older backend, or a record without the field: no mark and no
    # error, the same list as before.
    assert untidy_side["old"]["untidy"] is False
    assert untidy_side["old"]["chip"] is None


def test_a_deleted_dashboard_never_carries_the_mark(untidy_side):
    assert untidy_side["gone"]["untidy"] is False
    assert untidy_side["gone"]["chip"] is None


def test_the_selected_dashboard_keeps_the_mark(untidy_side):
    assert untidy_side["many"]["current"] is True
    assert untidy_side["many"]["untidy"] is True
    assert untidy_side["one"]["current"] is False
```

Dann die zwei Prüfungen am Stylesheet, **in `tests/test_panel_assets.py`** (statische Prüfungen von Dateiinhalt, keine Verhaltenstests). Dort steht `PANEL` schon für das Paketverzeichnis; ans Dateiende anhängen:

```python
STYLE_TEXT = (PANEL / "panel" / "style.js").read_text(encoding="utf-8")


def test_the_orange_rule_comes_after_the_blue_one():
    # Both rules have the same specificity, so the one written later
    # wins. If the orange stripe is written first, a selected, unversioned
    # dashboard goes blue - the exact thing issue 49 asks not to happen.
    blue = STYLE_TEXT.index('.dash[aria-current="true"]')
    orange = STYLE_TEXT.index(".dash.untidy")
    assert blue < orange


def test_the_orange_stripe_is_the_colour_the_current_state_wears():
    rule = STYLE_TEXT[STYLE_TEXT.index(".dash.untidy"):]
    rule = rule[: rule.index("}")]
    assert "inset 3px 0 0 var(--accent-color, #ff9800)" in rule
```

- [ ] **Schritt 2: Prüfen, dass sie fehlschlagen**

Run: `python3 -m pytest tests/test_panel_behaviour.py tests/test_panel_assets.py -q -p no:cacheprovider -k "unversioned or untidy or orange or carries or keeps_the_mark or chip_is"`
Erwartet: schlagen fehl (`untidy` ist `False`, Chip `None`; `.dash.untidy` nicht gefunden → `ValueError`). Ohne `node` überspringen die Szenario-Tests sichtbar – dann Node installieren, nicht weitermachen: ein Skip beweist nichts.

- [ ] **Schritt 3: `_renderDashboard` ändern**

In `panel.js` (Zeile ~3203) ersetzen durch:

```js
  _renderDashboard(d) {
    // A deleted dashboard has nothing left to put a version on, so it
    // is never marked, whatever the record says. A record without the
    // count (an older server) reads as zero and is not marked either.
    const pending = d.exists ? Number(d.unversioned) || 0 : 0;
    const chip = pending
      ? `<span class="pending" title="${pending} ${
          pending === 1 ? "change" : "changes"
        } not saved as a version yet">${pending}<span class="sr"> ${
          pending === 1 ? "change" : "changes"
        } not saved as a version yet</span></span>`
      : "";
    return `
        <button class="dash${pending ? " untidy" : ""}" data-key="${escape(d.key)}"
                aria-current="${d.key === this._selected}">
          <span>${escape(d.title)}${d.exists ? "" : '<span class="gone">deleted</span>'}${chip}</span>
          <span class="key">${escape(d.key)}</span>
        </button>`;
  }
```

Der Docblock über der Methode (falls vorhanden) bekommt einen Satz zum Streifen. Auf die vorhandenen Einrückungen und die Kommentardichte der Umgebung achten; keine Backticks **außerhalb** der Template-Literale dieser Funktion hinzufügen.

- [ ] **Schritt 4: Das CSS ergänzen**

In `panel/style.js`, direkt hinter die Regel `.dash[aria-current="true"] { … }` (Zeile ~400-403) und vor `.dash .key` einfügen:

```css
  /* Changes no version carries. Orange, the colour the current-state
     card and its chip already wear, and it stays orange when the row
     is selected: the grey background says which one is open, the
     stripe says which ones are not saved. Written after the selected
     rule and with the same specificity on purpose - the later one wins,
     so a selected, unversioned dashboard does not go blue. */
  .dash.untidy { box-shadow: inset 3px 0 0 var(--accent-color, #ff9800); }
  .dash .pending {
    display: inline-block;
    margin-left: 6px;
    padding: 0 6px;
    border-radius: 8px;
    background: var(--accent-color, #ff9800);
    color: #fff;
    font-size: 11px;
    vertical-align: 1px;
  }
```

Keine Backticks, kein `${` in dieser Datei – auch nicht im Kommentar.

- [ ] **Schritt 5: Prüfen, dass die Tests bestehen**

Run: `python3 -m pytest tests/test_panel_behaviour.py tests/test_panel_assets.py -q -p no:cacheprovider`
Erwartet: `0 failed`, keine Skips wegen `node`.

- [ ] **Schritt 6: Commit**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py tests/test_panel_assets.py
git commit
```

Message:

```
Mark unversioned dashboards in the list

Which dashboards still hold changes no version carries was visible
only after opening each one. The list now draws an orange stripe and
a count for every such dashboard, in both modes, and the stripe stays
orange when the row is selected; the grey background already says
which one is open.

The orange rule sits after the selected one with equal specificity,
which is what makes it win, and a test pins that order.

Closes #49.
```

---

## Aufgabe 3: Gesamtprüfung, Messung, Sichtprüfung

**Files:** keine Änderungen am Code; ein Bericht im Handover.

- [ ] **Schritt 1: Alles noch einmal laufen lassen**

```bash
python3 -m pytest tests/ -q -p no:cacheprovider
python3 tools/complexity_ratchet.py
lint-imports
git status --short
git log --oneline main..HEAD
```
Erwartet: `0 failed`, Wächter grün, Arbeitsbaum sauber, genau zwei Commits.

- [ ] **Schritt 2: Messen, was die neue Abfrage kostet (nur berichten, nicht festschreiben)**

Mit diesem Skript in einem Temp-Verzeichnis außerhalb des Repos (z. B. `$(mktemp -d)`), aus dem Repo-Stamm gestartet:

```bash
python3 - <<'PY'
import sys, tempfile, time
sys.path.insert(0, "custom_components/dashboard_history")
from store import HistoryStore

s = HistoryStore(tempfile.mkdtemp() + "/history")
s.ensure()
for d in range(40):
    key = f"dash{d}"
    revs = [s.write_snapshot(key, f"a: {i}\n", f"change {i}") for i in range(20)]
    for i in range(0, 20, 2):
        s.create_version(f"{key}/v1.0.{i}", f"v{i}", "", revs[i])
for label in ("cold", "warm", "warm again"):
    t = time.perf_counter()
    s.unversioned_counts()
    print(label, round((time.perf_counter() - t) * 1000, 1), "ms")
t = time.perf_counter()
s.survey()
print("survey (for scale)", round((time.perf_counter() - t) * 1000, 1), "ms")
PY
```
Die vier Zahlen (40 Dashboards, 800 Änderungen, 400 Tags) ins Handover schreiben. Eine Zahl über 100 ms bei `warm` ist ein Befund für Claude, kein Grund, selbst umzubauen.

- [ ] **Schritt 3: Im Testcontainer prüfen**

Voraussetzungen und Fallen: `docker/README.md` und der Abschnitt »Check locally first« in `CLAUDE.md`. **Während eines HA-Neustarts nie pollen** (IP-Sperre), und **kein Test löscht nach Präfix**.

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```
Erwartet: die zwei neuen Prüfungen aus Aufgabe 1 Schritt 8 stehen auf OK. Zwei bekannte, **nicht** durch diese Änderung verursachte Befunde der Prüfbank (»a card could be dropped« u. a.) beschreiben das Auswahlrisiko von `run_checks` selbst; sie vor dem Lauf nicht »reparieren«, sondern im Handover benennen, wenn sie auftreten.

Nach einer Änderung an `panel.js` oder `panel/*.js` den Container neu starten (der Fingerprint hängt am Dateiinhalt; bei rotem Fingerprint vorher lokal nachrechnen, um Codefehler auszuschließen).

- [ ] **Schritt 4: Sichtprüfung (manuell, kann nur der Nutzer)**

Das Panel in Simple und in Advanced öffnen und prüfen:
1. Ein Dashboard mit Änderungen nach der letzten Version: oranger Streifen und Chip, auch ohne Auswahl.
2. Dasselbe Dashboard ausgewählt: Streifen bleibt orange, Hintergrund ist grau.
3. Auf »Save this as a version« klicken: Streifen und Chip verschwinden ohne Neuladen.
4. Schmales Fenster (unter 560 px, nur Liste): Chip bricht die Zeile nicht um.
5. Dunkles Theme: Chip lesbar.

Das Ergebnis bleibt im Handover **offen**, bis der Nutzer es bestätigt hat; Gemini darf es nicht als erledigt melden.

---

## Self-Review (Stand beim Schreiben)

- **Spec-Abdeckung (Issue #49):** Streifen für alle ungespeicherten Dashboards → Aufgabe 2; unabhängig von der Auswahl → Test `test_a_dashboard_with_unversioned_changes_carries_the_mark` (nicht ausgewählt) und `test_the_selected_dashboard_keeps_the_mark` (ausgewählt); bleibt orange bei Auswahl → CSS-Reihenfolge-Test; Simple und Advanced → beide Modi rendern `_renderSide` (einzige Stelle, `panel.js` Zeile ~4136, `<div class="side">${this._renderSide()}</div>`); Zähler (Nutzerwunsch im Gespräch) → Chip, Screenreader-Text durch `test_the_chip_is_read_out_in_words` abgesichert.
- **Platzhalter:** keine. Jede Code-Änderung steht ausgeschrieben; die Erwartung in `run_checks.py` (Schritt 8c) wird aus den verbliebenen Versionen berechnet, nicht geraten.
- **Namenskonsistenz:** `unversioned_counts`, `dashboard_listing`, `_count_unversioned`, `_marked_revisions`, `_tag_targets`, Feld `unversioned`, Klasse `untidy`, Chip-Klasse `pending` – in Aufgabe 1, 2 und den Tests gleich geschrieben.
- **Bekannte Grenze (bewusst):** Eine Änderung hinter dem Rücken von Home Assistant (von Hand editierte Storage-Datei) taucht erst mit dem nächsten Start in der Historie auf und färbt das Dashboard erst dann orange; der Vergleich der Live-Konfiguration mit HEAD wäre je Dashboard ein Laden der Live-Config und gehört nicht in dieses Ticket.
- **Einarbeitung der Reviews:** kritisch (Rennen mit `forget`, alle vier Läufe) → Rennschutz plus `dashboard_listing`, Beweis durch zwei Hook-Tests, deren Aussagekraft Aufgabe 1 Schritt 6 ausdrücklich prüft; wichtig (Integrationsprüfung zu schwach, leeres Repository, `.sr`) → Schritt 8, `test_a_repository_without_a_commit_answers_nothing`, `test_the_chip_is_read_out_in_words`; Hinweis (Cache-Regression, CSS-Tests in `test_panel_assets.py`, `remove_version`-Vorbehalt) → `test_an_unchanged_version_is_not_read_again`, verschoben beziehungsweise gestrichen.
