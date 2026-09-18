# Versionsmarken in einem Zug — Implementierungsplan

> **Für agentische Bearbeiter:** Die Aufgaben in der angegebenen Reihenfolge abarbeiten, die Schritte innerhalb einer Aufgabe ebenso; die Checkboxen (`- [ ]`) sind zum Abhaken da. Innerhalb von Claude Code dafür `superpowers:subagent-driven-development` oder `superpowers:executing-plans` verwenden — außerhalb genügt die Reihenfolge.
>
> **Vorher lesen:** `CLAUDE.md` im Wurzelverzeichnis. Dort stehen die harten Regeln dieses Projekts (kein `git`-Binary, kein Home Assistant in den Kernmodulen, nichts wird ohne Vorschau geschrieben), und sie gelten auch dort, wo dieser Plan sie nicht wiederholt.

**Ziel:** `_rewrite_tags` schreibt alle Versionsmarken eines `forget` in einem einzigen Dateischreibvorgang statt in einem pro Marke — gemessen 12,46 s → 0,02 s bei 782 Marken, und damit 58 % der Gesamtlaufzeit.

**Architektur:** `dulwich`s `DiskRefsContainer` bietet mit `add_packed_refs(mapping)` genau die Batch-Operation, die hier fehlt: Sie schreibt `packed-refs` **einmal** unter einem Lock, wobei ein Ziel von `None` die Ref entfernt. Die heutige Schleife wird also nicht optimiert, sondern durch ein aufgebautes Mapping und einen Aufruf ersetzt. Die Schleife bleibt bestehen — sie baut nur noch das Mapping und die neuen Tag-Objekte, statt jedes Mal die Platte anzufassen.

**Technik:** Python 3.12 (Entwicklungsmaschine) / 3.14 (Container), `dulwich` 1.2.14, `pytest`. Kein Home Assistant in `store.py`.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — Entscheidung 12 (endgültiges Löschen), Entscheidung 13 (eine Version gehört einem Dashboard), sowie der Nachtrag vom 2026-09-02 über leichtgewichtige Tags.

## Voraussetzung

Dieser Plan setzt auf `main` ab `97385e7` auf. Was er vorfindet und benutzt, ist **heute** entstanden:

- `_rewrite_tags` hat seit `af6daca` einen sechsten Parameter `say: _Progress`, und `forget` nimmt einen Fortschritts-Callback. Gegen einen älteren Stand passt der Code in Aufgabe 2 nicht.
- `97385e7` hat den Kommentar in genau der Methode berichtigt, die Aufgabe 2 ersetzt — wer auf einem älteren Stand arbeitet, schreibt die falsche Begründung zurück.

## Wo eine Rückfrage fällig ist, statt allein zu entscheiden

Drei Stellen. Überall sonst gilt: durcharbeiten.

1. **Aufgabe 3, Schritt 2.** Ob die Phase `versions` überhaupt noch gemeldet wird, hängt an einer Messung — und daran hängen der Text im Panel und zwei Dateien mehr im Commit. Das Messergebnis vorlegen, dann entscheiden lassen.
2. **Aufgabe 5.** Ein Kommentar an Issue #19 ist eine **öffentliche** Äußerung in einem öffentlichen Repository. Vorher den Wortlaut zeigen.
3. **Wenn eine Zahl stark abweicht.** Die Werte in diesem Plan sind gemessen, nicht geschätzt. Weicht eine deutlich ab, stimmt eine Annahme nicht mehr — dann anhalten, nicht die Schwelle anpassen.

## Die Testinstanz, und zwei Regeln dazu

Aufgaben 3 und 4 brauchen den Wegwerf-Container (`docker/compose.yaml`), **niemals** eine Installation, an der etwas hängt.

- **Nach einem Neustart nicht pollen.** Home Assistants IP-Sperre sperrt sonst den eigenen Zugang aus. In einem Zug warten (90 s genügen), dann einmal verbinden.
- **Nie nach Präfix löschen.** Nur der eine, ausgeschriebene Schlüssel, den der eigene Lauf angelegt hat. Was daraus einmal schiefging, steht im Nachtrag vom 2026-09-01 in `docs/superpowers/plans/2026-08-31-eigene-texte-und-klartext.md`.

## Globale Randbedingungen

- **Kein `git`-Binary.** Ausschließlich `dulwich` (Spec, harte Regel).
- **`store.py` bleibt frei von Home Assistant.** Kein `import homeassistant`, auch nicht mittelbar.
- **Beide Tag-Formen zählen.** Annotierte *und* leichtgewichtige. Ein Tag-Vorgang, der die leichtgewichtige Form still überspringt, hat `forget` schon einmal wirkungslos gemacht, während es Erfolg meldete (Spec, Nachtrag vom 2026-09-02).
- **Die Namensraum-Regel.** Marken unter `<schlüssel>/` gehören dem vergessenen Dashboard und werden **gelöscht**, nicht verschoben. Der Zaun ist `_owns`, und er kennt Schlüssel mit Schrägstrich (gemessen am 2026-09-04: `forget("foo")` nahm die Marke von `foo/bar` mit).
- **Sprache.** Code, Kommentare und Commit-Nachrichten englisch; dieser Plan deutsch (Design-Journal).
- **Tests:** `python3 -m pytest tests/ -v`. Erwartet ist »0 failed«; die Gesamtzahl schwankt mit den Dashboards der echten `.storage` und ist keine Konstante.

## Ausgangsmessung (2026-09-18, Prüfbank: 7407 Commits, 45 lebende + 25 gelöschte Dashboards, 782 Marken, 11 MB)

| Phase | Zeit | Anteil |
|---|---|---|
| `_rewrite_tags` | 13,05 s | **58 %** |
| `garbage_collect` | 4,49 s | 20 % |
| Commits umschreiben | 4,67 s | 21 % |
| alles übrige | 0,19 s | < 1 % |

Isoliert gegengemessen, 782 gepackte Marken, `packed-refs` = 58 KB:

| Vorgang | Zeit | je Marke | was er anfasst |
|---|---|---|---|
| `del repo.refs[…]` | 8,71 s | 11,1 ms | schreibt `packed-refs` neu und benennt sie um |
| `repo.refs[…] = sha` | 4,28 s | 5,5 ms | schreibt eine **lose** Ref-Datei und ruft `fsync` |
| beides, wie heute | 12,46 s | 15,9 ms | |
| `add_packed_refs`, ein Aufruf | 0,02 s | — | schreibt `packed-refs` einmal |

**Die Hälften kosten verschieden, und das ist beim Aufschreiben wichtig:** Nur das *Entfernen* fasst `packed-refs` an; das *Setzen* schreibt eine lose Datei und lässt `packed-refs` unberührt. Der Satz »jede Ref-Operation schreibt `packed-refs` neu« ist falsch und stand in der ersten Fassung dieses Plans.

---

### Aufgabe 1: Der Beweis, dass heute pro Marke geschrieben wird

Ein Test, der den Ist-Zustand festhält, bevor irgendetwas sich ändert — und der **nach** der Umstellung die neue Zusage prüft. Ohne ihn ist die Umstellung eine Behauptung über Laufzeit, die keine Testsuite je wieder nachhält.

**Der Endzustand taugt dafür nicht.** Naheliegend wäre, nach dem `forget` nachzusehen, ob lose Ref-Dateien übrig sind — und genau das war die erste Fassung dieses Plans. Sie wäre auch heute schon grün gewesen: `garbage_collect` endet mit `pack_refs()`, also packt jedes `forget` die Refs am Schluss ohnehin. Nachgewiesen im Review vom 2026-09-18. Gezählt werden muss deshalb, **wie oft `packed-refs` geschrieben wird**, und die Marken müssen vorher gepackt sein — gegen lose Refs fasst das Entfernen die Datei gar nicht erst an, und der Zähler bliebe stumm.

**Dateien:**
- Ändern: `tests/test_store.py` (anhängen)

**Schnittstellen:**
- Nutzt: `HistoryStore.write_snapshot`, `create_version`, `forget` — alle vorhanden.
- Liefert: nichts für spätere Aufgaben.

- [ ] **Schritt 1: Den fehlschlagenden Test schreiben**

Ans Ende von `tests/test_store.py`:

```python
def test_forgetting_does_not_write_packed_refs_once_per_version(
    store, monkeypatch
):
    """One write for all the marks, not one per mark.

    The cost this guards is the largest single part of a `forget`:
    measured on the test bench on 2026-09-18, 782 marks took 12.46 s,
    58 % of the whole operation, because removing a ref rewrites the
    whole `packed-refs` file and renames it into place - 11.1 ms each.

    Counted rather than looked at afterwards. The state at the end
    proves nothing: `garbage_collect` finishes with `pack_refs()`, so
    every `forget` leaves the refs packed whichever way they got there.

    Packed on purpose before the count starts: against loose refs the
    removal never touches `packed-refs` and the number would be zero
    either way.
    """
    store.write_snapshot("home", "a: 1\n", "home first")
    store.write_snapshot("gone", "b: 1\n", "gone first")
    for n in range(20):
        store.write_snapshot("home", f"a: {n + 2}\n", f"home {n}")
        store.create_version(f"home/v1.0.{n}", f"Mark {n}", "kept over the rewrite")
    store.create_version("gone/v1.0.0", "Goes away", "with its dashboard")
    store._repo().refs.pack_refs()

    writes = []
    real = dulwich.refs.GitFile

    def spy(path, mode="rb", *args, **kwargs):
        name = path if isinstance(path, bytes) else str(path).encode()
        if name.endswith(b"packed-refs") and "w" in mode:
            writes.append(name)
        return real(path, mode, *args, **kwargs)

    monkeypatch.setattr(dulwich.refs, "GitFile", spy)
    store.forget("gone")

    # Measured: 22 writes for 21 marks before the change, 2 after - the
    # batch itself and the collection's own `pack_refs`. Five leaves
    # room for a dulwich that writes once more somewhere without
    # letting a per-mark write back in.
    assert len(writes) <= 5, f"{len(writes)} writes for 21 marks"
    # And the marks that survive are still readable, under their full
    # names: `Version.name` carries the dashboard's key.
    kept = {v.name for v in store.list_versions("home")}
    assert kept == {f"home/v1.0.{n}" for n in range(20)}
```

`dulwich.refs` muss oben in `tests/test_store.py` importiert sein — `dulwich.refs` hält `GitFile` unter eigenem Namen, ein Austausch in `dulwich.file` bliebe wirkungslos.

- [ ] **Schritt 2: Den Test laufen lassen und rot sehen**

Ausführen: `python3 -m pytest tests/test_store.py::test_forgetting_does_not_write_packed_refs_once_per_version -v`

Erwartet: FAIL mit `22 writes for 21 marks` — nachgemessen am 2026-09-18, eine Schreiboperation je Marke plus die der Bereinigung.

Weicht die Zahl stark ab, aufhören und nachsehen: Dann zählt der Abfang etwas anderes als gedacht, und ein Test, der das Falsche zählt, ist schlimmer als keiner.

**Hier wird nicht committet.** Der Test bleibt rot im Arbeitsverzeichnis stehen und geht gemeinsam mit Aufgabe 2 hinein. Grund: In diesem Projekt wird jeder Commit einzeln gegen seinen eigenen Baum geprüft (`git write-tree` + `archive` + `pytest`); ein Commit mit rotem Test macht diese Prüfung wertlos, und zwar dauerhaft, weil sie danach für jede spätere Bisektion lügt.

---

### Aufgabe 2: `_rewrite_tags` auf einen Schreibvorgang umstellen

**Dateien:**
- Ändern: `custom_components/dashboard_history/store.py:1143` (`_rewrite_tags`)
- Test: `tests/test_store.py` (die vorhandenen `forget`-Tests decken das Verhalten ab)

**Schnittstellen:**
- Nutzt: `_owns(ref, key)`, `nearest: dict[bytes, bytes | None]`, `tag_class` (das `Tag` aus `dulwich.objects`), `say: _Progress`.
- Liefert: `_rewrite_tags(repo, versions, nearest, tag_class, key, say) -> None` — Signatur unverändert.

- [ ] **Schritt 1: Die Methode ersetzen**

Der Körper von `_rewrite_tags` ab `say("versions", 0, len(versions))` wird zu:

```python
        # One write for all of them. `del repo.refs[...]` rewrites the
        # whole `packed-refs` file and renames it into place, once per
        # mark; the assignment after it writes a loose file and fsyncs
        # that. Measured 2026-09-18 on the test bench with 782 packed
        # marks: 11.1 ms and 5.5 ms each, 12.46 s together, against
        # 0.02 s for the single call below.
        #
        # `add_packed_refs` takes the whole mapping at once, and a target
        # of None removes that ref - exactly the two things this method
        # does. It also unlinks any loose ref of the same name, so both
        # shapes are covered without asking which one a mark has.
        #
        # Not a transaction over all the marks, and nothing here should
        # be written as though it were: the loose files are unlinked as
        # the mapping is walked, and only the packed file is replaced in
        # one move at the end.
        say("versions", 0, len(versions))
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
        # Empty is not a special case for `add_packed_refs`; it returns
        # at once. Said here because a repository without a single mark
        # is the ordinary case for a young installation.
        repo.refs.add_packed_refs(changed)
        say("versions", len(versions), len(versions))
```

Zu beachten, weil es sich gegenüber heute ändert:

* Der Fortschritt innerhalb der Phase entfällt (`say.every`). Die Phase dauert danach Millisekunden; ein Zähler, der von 0 auf 782 springt, sagt nichts. Die Phase selbst wird weiterhin gemeldet, mit Anfang und Ende — Aufgabe 3 zieht daraus die Folgerung fürs Panel.
* Das Löschen geschieht nicht mehr **vor** dem Neusetzen, sondern beides gemeinsam. Pro Ref-Name entsteht genau ein Eintrag, also kann kein Löschen ein Setzen überschreiben.
* Ein Ref, dessen Ziel weggefallen ist (`moved is None`), wird jetzt **ausdrücklich** auf `None` gesetzt. Heute wurde er durch das vorgezogene `del` entfernt und einfach nicht neu gesetzt — dasselbe Ergebnis, aber nur, weil das `del` vorher lief. Als Mapping muss es dastehen.

- [ ] **Schritt 2: Den Test aus Aufgabe 1 laufen lassen**

Ausführen: `python3 -m pytest tests/test_store.py::test_forgetting_leaves_no_loose_tag_refs_behind -v`

Erwartet: PASS.

- [ ] **Schritt 3: Alle vorhandenen `forget`-Tests laufen lassen**

Ausführen: `python3 -m pytest tests/test_store.py -k forget -v`

Erwartet: PASS, darunter namentlich

* `test_forgetting_a_dashboard_keeps_the_versions_of_a_nested_legacy_key` — der `_owns`-Zaun bei Schlüsseln mit Schrägstrich,
* `test_forgetting_clears_the_index_and_the_working_tree_too`,
* `test_forgetting_a_dashboard_leaves_no_stale_index_behind`.

Geht einer davon rot, **nicht** nachbessern, sondern zurück zum Mapping-Aufbau: Er beschreibt eine Regel, die der Umbau verletzt hat.

- [ ] **Schritt 4: Die ganze Suite laufen lassen**

Ausführen: `python3 -m pytest tests/ -q`

Erwartet: `0 failed`. Die Gesamtzahl schwankt mit den Dashboards der echten `.storage`.

- [ ] **Schritt 5: Committen**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "Write all version marks in one go

Removing a ref rewrites the whole packed-refs file and renames it
into place, so rewriting the marks one at a time paid that cycle per
mark: measured on the test bench with 782 packed marks, 11.1 ms for
the removal and 5.5 ms for the loose file written after it - 12.46 s
together, 58 % of the entire forget. add_packed_refs takes the whole
mapping and does it in 0.02 s.

It narrows issue #19 as well, in this one phase: an interrupted
forget could be caught between write and rename once per mark, and
now once. A full forget still writes packed-refs more than once, and
this call is no transaction over all the marks - the loose refs go as
the mapping is walked."
```

---

### Aufgabe 3: Die Fortschrittsanzeige an die neue Verteilung anpassen

Nach Aufgabe 2 dauert die Phase »Versionsmarken« Millisekunden, und die verbleibende Zeit verteilt sich völlig anders. Das Panel würde sonst eine Phase anzeigen, die nie zu sehen ist, und dafür die Bereinigung — jetzt der größte Posten — weiterhin ohne Zahl lassen.

**Dateien:**
- Ändern: `custom_components/dashboard_history/panel.js` (die `phases`-Tabelle in `_renderLock`)
- Test: `tests/test_panel_behaviour.py` (das Szenario `_LOCK_SCREEN`)
- **Nur wenn die Phase `versions` entfällt**, zusätzlich:
  - Ändern: `custom_components/dashboard_history/store.py` (die beiden `say("versions", …)` in `_rewrite_tags`)
  - Ändern: `tests/test_store.py` — `test_forgetting_reports_its_progress` verlangt `"versions" in phases` ausdrücklich und wird sonst rot

Der Panel-Testlauf allein findet das nicht: Die Phasennamen stehen auf beiden Seiten getrennt, und nur `tests/test_store.py` prüft, welche der Store überhaupt meldet. **Vor dem Commit deshalb `python3 -m pytest tests/ -q`, nicht nur `-k lock`.**

**Schnittstellen:**
- Nutzt: `this._forgetting.phase` aus `_onForgetting`, gespeist von `EVENT_FORGET_PROGRESS`.
- Liefert: nichts.

- [ ] **Schritt 1: Neu messen, bevor irgendein Text geändert wird**

Der Container muss laufen; die Phasenmessung von oben noch einmal fahren, gegen dieselbe Prüfbank:

```bash
docker compose -f docker/compose.yaml up -d
docker restart dashboard-history-test
```

Dann messen, welche Phase jetzt wie lange dauert. Ohne diese Zahl ist jede Textänderung geraten. Das Messen geht ohne Home Assistant, weil `store.py` frei davon ist — gegen eine **Kopie** des Repositorys der Testinstanz, nie gegen das Original:

```python
# Wegwerfskript, gehoert in das Scratchpad-Verzeichnis, nicht ins Repo.
import functools, pathlib, shutil, sys, time
sys.path.insert(0, "custom_components/dashboard_history")
import store as st
import dulwich.gc

SRC = pathlib.Path("../ha-dashboard-history-test/config/dashboard_history")
WORK = pathlib.Path("/tmp/forget-bench")
shutil.rmtree(WORK, ignore_errors=True)
shutil.copytree(SRC, WORK)

timings = {}

def clock(name, fn):
    @functools.wraps(fn)
    def wrapped(*a, **kw):
        t = time.perf_counter()
        try:
            return fn(*a, **kw)
        finally:
            timings[name] = timings.get(name, 0.0) + time.perf_counter() - t
    return wrapped

for name in ("_rewrite_tags", "_rewrite_notes", "_tree_without", "_drop_from_index"):
    raw = vars(st.HistoryStore)[name]
    fn = raw.__func__ if isinstance(raw, (staticmethod, classmethod)) else raw
    wrapped = clock(name, fn)
    setattr(st.HistoryStore, name,
            type(raw)(wrapped) if isinstance(raw, (staticmethod, classmethod)) else wrapped)
dulwich.gc.garbage_collect = clock("garbage_collect", dulwich.gc.garbage_collect)

s = st.HistoryStore(WORK)
key = sorted(s.list_all_dashboards())[0]      # irgendeines, es wird nur gemessen
t = time.perf_counter()
s.forget(key)
total = time.perf_counter() - t
print(f"GESAMT {total:.2f} s")
for name, secs in sorted(timings.items(), key=lambda kv: -kv[1]):
    print(f"  {name:20s} {secs:6.2f} s  {secs / total * 100:5.1f} %")
print(f"  {'Rest':20s} {total - sum(timings.values()):6.2f} s")
```

`type(raw)(wrapped)` wickelt `staticmethod` und `classmethod` wieder richtig ein — ohne das scheitert der Lauf an `_raw_tags`, einer `classmethod`.

Erwartet nach Aufgabe 2, als Vorhersage zum Prüfen: etwa 11 s insgesamt, davon rund 4,5 s Bereinigung (dann **40 %** statt 20) und rund 4,7 s Umschreiben.

- [ ] **Schritt 2: Entscheiden und festhalten, was das Panel sagt**

Zwei Fragen, die die Messung aus Schritt 1 beantwortet, und die hier bewusst offen stehen, statt geraten zu werden:

1. Ist »Rebuilding the version marks« noch eine eigene Phase wert, wenn sie 10 ms dauert? Wahrscheinlich nein — dann fällt sie aus der Tabelle und der Store meldet sie gar nicht erst.
2. Braucht die Bereinigung jetzt einen Zähler, wo sie der größte Posten ist? `garbage_collect` meldet von sich aus nichts; ein Zähler hieße, `dulwich`s Objektspeicher selbst zu durchlaufen — Aufwand, der in einem eigenen Vorhaben gehört, nicht hier.

Die Antwort in `docs/superpowers/status.md` festhalten, mit den Messwerten aus Schritt 1.

- [ ] **Schritt 3: Die Tabelle anpassen und den Test nachziehen**

Der Test `test_the_lock_screen_says_what_is_happening` prüft heute auf `"Rebuilding the version marks"`. Entfällt die Phase, muss dort die Phase stehen, die an ihre Stelle tritt — **nicht** die Zusicherung entfernen: Sie ist das einzige, was prüft, dass ein Phasenname überhaupt beim Leser ankommt.

- [ ] **Schritt 4: Tests laufen lassen**

Ausführen: `python3 -m pytest tests/test_panel_behaviour.py -k lock -v`

Erwartet: PASS.

- [ ] **Schritt 5: Committen**

```bash
# store.py und tests/test_store.py nur, wenn die Phase `versions` entfiel.
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py \
        custom_components/dashboard_history/store.py tests/test_store.py \
        docs/superpowers/status.md
git commit -m "Name the phases that are still worth naming

Rewriting the version marks went from 58 % of a forget to milliseconds,
so the lock screen announced a phase nobody ever saw while the
collection - now the largest part - went unnamed."
```

---

### Aufgabe 4: Im Container nachweisen und die Werte festschreiben

Der `pytest`-Lauf erreicht die Module, die Home Assistant kennen, strukturell nicht, und **jeder bisher in diesem Projekt gefundene Defekt lag genau dort**. Ein Laufzeitgewinn, der nur lokal gemessen wurde, ist kein Nachweis.

**Dateien:**
- Ändern: `docs/superpowers/status.md`
- Ändern: `.claude/lessons.md` (nur wenn Schritt 3 es rechtfertigt)

- [ ] **Schritt 1: Den vollständigen Prüflauf fahren**

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

Erwartet: kein neuer Fehlschlag gegenüber dem Lauf vor diesem Vorhaben. Besonders zu beachten ist der Abschnitt `run_forget`, und darin die Zusicherung, dass eine Beschreibung auf einem **anderen** Dashboard die Umschreibung überlebt — Notizen hängen an Commit-SHAs, Marken an Refs, und dieser Plan fasst nur die Refs an.

- [ ] **Schritt 2: Die Laufzeit eines echten `forget` messen**

Ein Dashboard mit eigenem, ausgeschriebenem Schlüssel anlegen, ein paar Stände speichern, löschen, die aufgezeichnete Löschung abwarten, vergessen, Zeit nehmen. **Niemals nach Präfix löschen** — nur der eine, genau benannte Schlüssel (Regel aus dem Nachtrag vom 2026-09-01).

Vergleichswert vor diesem Vorhaben: **24,0 s** ohne Nebenlast, 51,9 s mit Listenabfragen, 76,0 s mit Historienabfragen.

Erwartet: etwa 11 s ohne Nebenlast. Liegt der Wert deutlich darüber, ist die Umstellung nicht wirksam geworden — dann zuerst `packed-refs` im Repository der Testinstanz ansehen, bevor irgendetwas anderes vermutet wird.

- [ ] **Schritt 3: Festhalten**

In `docs/superpowers/status.md` die neue Verteilung notieren. In `.claude/lessons.md` gehört ein Abschnitt **nur dann**, wenn die Antwort auf »Würde ein anderes Teammitglied dieselbe Falle tappen?« ja lautet. Hier lautet sie ja, und der Satz dafür ist:

> **`dulwich` schreibt `packed-refs` bei jedem Entfernen einer
> gepackten Ref komplett neu.** `del repo.refs[x]` schreibt die ganze
> Datei und benennt sie um — gemessen 11,1 ms bei 58 KB und 782 Marken.
> `repo.refs[x] = y` dagegen schreibt eine **lose** Datei und ruft
> `fsync`, 5,5 ms, und lässt `packed-refs` unberührt; »jede
> Ref-Operation schreibt `packed-refs`« ist also falsch und war die
> erste, zu weit gefasste Fassung dieses Absatzes. Zusammen 12,46 s
> gegenüber 0,02 s mit `repo.refs.add_packed_refs(mapping)`, das alles
> in einem Zug erledigt und mit einem Ziel von `None` auch löscht.
> **Vor jeder Schleife über Refs in diesem oder einem Nachbarprojekt:**
> prüfen, ob die Batch-Form es auch tut.

- [ ] **Schritt 4: Committen**

```bash
git add docs/superpowers/status.md .claude/lessons.md
git commit -m "Write down what the marks cost, and what they cost now"
```

---

### Aufgabe 5: Issue #19 um den Befund ergänzen

Kein Code. Issue #19 beschreibt einen unterbrochenen `forget`, der `packed-refs.lock` hinterlässt und damit jeden weiteren `forget` dauerhaft verhindert.

**Was sich ändert, und nur das:** In dieser einen Phase schrieb ein `forget` die Datei einmal je Marke — bei 782 Marken also 782 Gelegenheiten, zwischen Schreiben und Umbenennen unterbrochen zu werden. Danach ist es eine.

**Was sich nicht ändert, und das gehört dazugesagt:** Ein vollständiger `forget` fasst `packed-refs` weiterhin mehrfach an, unter anderem in der abschließenden Bereinigung, die mit `pack_refs()` endet. Und `add_packed_refs` ist **keine** Transaktion über alle Marken: Die losen Ref-Dateien werden beim Durchlaufen des Mappings entfernt, und nur die gepackte Datei wird am Ende in einem Zug ersetzt. Ein Absturz mittendrin hinterlässt also weiterhin einen Zustand, den niemand angeordnet hat — nur seltener.

#19 ist damit nicht behoben. Wer es später angeht, soll die Zahl kennen, statt sie neu zu ermitteln.

- [ ] **Schritt 1: Kommentar anlegen**

Der Text enthält Backticks, und die sind in doppelten Anführungszeichen Kommandoersetzung — `--body "… `_rewrite_tags` …"` lässt die Shell ein Programm dieses Namens suchen. Über ein **quotiertes** Here-Document in eine Datei, dann `--body-file`:

```bash
cat > /tmp/issue-19-note.md <<'EOF'
Since <commit>, `_rewrite_tags` collects every mark into one
`add_packed_refs` call instead of removing and setting each ref on its own.

That does not fix this. It narrows one phase of it: removing a ref rewrites
`packed-refs` and renames it into place, so that phase offered one chance to be
interrupted per mark — 782 on the test bench — and now offers one. A full
`forget` still writes the file more than once (the collection ends with
`pack_refs()`), and `add_packed_refs` is not a transaction over all the marks:
loose refs are unlinked while the mapping is walked, and only the packed file is
swapped in one move at the end.

Measured 2026-09-18, 782 packed marks: 12.46 s for that phase, 0.02 s after.
EOF
gh issue comment 19 --body-file /tmp/issue-19-note.md
```

`<commit>` durch den SHA aus Aufgabe 2 ersetzen. Das quotierte `<<'EOF'` ist der Kern: unquotiert ersetzt die Shell auch dort.

---

## Was dieser Plan ausdrücklich nicht tut

* **Die Bereinigung beschleunigen.** `garbage_collect` ist danach mit rund 4,5 s der größte Posten. Ob `grace_period=0` und ein voller Objektspeicher-Durchlauf bei jedem `forget` nötig sind, ist eine eigene Frage — und sie berührt die Zusicherung »für immer vergessen«, also die Spec. Nicht nebenbei.
* **Issue #20 beheben.** Der `KeyError` beim Lesen der Stände hat eine andere Ursache, die noch nicht gefunden ist. Die `DIAG`-Zeilen in `capture.py` bleiben stehen, bis sie ihn gefangen haben.
* **Die Sperre oder ihre Texte ändern**, über die Phasennamen aus Aufgabe 3 hinaus.
* **`get_peeled` reparieren.** Nach `add_packed_refs` liefert es für annotierte Marken die SHA des Tag-Objekts statt des dereferenzierten Commits — was es heute nach `pack_refs()` genauso tut, weil `dulwich` in beiden Fällen keine `^{}`-Zeilen schreibt. Das Projekt ruft `get_peeled` nirgends auf; `_raw_tags` dereferenziert selbst über `tag.object[1]`. Geprüft am 2026-09-18, festgehalten, damit niemand es für eine Nebenwirkung dieses Umbaus hält.
