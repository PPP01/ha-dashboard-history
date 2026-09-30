# Objektzähler in `tests/test_store.py`: warum die CI sie reißt

Bezug: Issue #46 (»Object-count ceilings in test_store.py fail intermittently on CI«). Untersucht auf dem committeten Stand `origin/main` = `2aceaa6`, in einer Scratch-Kopie per `git archive`. Am Repository wurde nichts geändert; Instrumentierung lag nur als pytest-Plug-in bzw. Messskript neben der Kopie. Das eigens gezogene Image `python:3.13` ist wieder entfernt, Container liefen mit `--rm`.

Betroffen:

- `test_a_new_change_costs_the_change_and_not_the_history` (`tests/test_store.py:3888`, Grenze `:3917`)
- `test_a_new_change_does_not_make_the_survey_walk_again` (`tests/test_store.py:3954`, Grenze `:3978`)

## 1. Ursache

**Die Zahl hängt nicht vom Packen ab, sondern von der Uhr: davon, wie viele der 120 Rausch-Commits in derselben Sekunde entstanden sind wie der neue HEAD.** dulwichs Walker in `_extended_index` läuft über jeden dieser Commits, obwohl sie alle ausgeschlossen sind. Die CI-Runner committen etwa dreimal so schnell wie die Entwicklungsmaschine und bekommen deshalb bis zu alle 121 alten Commits in die letzte Sekunde.

### Bewiesen (im Code gelesen)

- `HistoryStore._extended_index` (`store.py:2778`) schreibt den Index fort mit `repo.get_walker(include=[head], exclude=[cached.head])`.
- Commits werden über `porcelain.commit` angelegt (`store.py:1285`), das über den Worktree geht; dort stempelt `dulwich/worktree.py:603` mit `commit_timestamp = time.time()`, gespeichert in ganzen Sekunden.
- dulwich 1.2.14, `_CommitTimeQueue._step` (`dulwich/walk.py:243–252`): Sind nur noch ausgeschlossene Commits in der Queue, wird der Zähler `_extra_commits_left` (Start `_MAX_EXTRA_COMMITS = 5`, `walk.py:57`) **nur dann** heruntergezählt, wenn der nächste Commit *älter* ist als der zuletzt ausgegebene (`n.commit_time >= self._last.commit_time` → zurücksetzen). `_last` ist hier der neue HEAD. Jeder ausgeschlossene Vorfahr mit **derselben** Sekunde setzt den Zähler also zurück, und der Walker liest weiter – bis zum ersten älteren Commit plus fünf. Pro so gelaufenem Commit fallen `_push` des Elternteils und `_exclude_parents` an, gemessen etwa 1,45 Reads.
- Automatisches Packen: `worktree.py:788` ruft nach jedem Commit `maybe_auto_gc` auf, die Schwelle ist `DEFAULT_GC_AUTO = 6700` Loose-Objekte (`dulwich/gc.py:60`). Der Test erzeugt 363–366. Es wird in diesen Tests **nie** gepackt.

### Bewiesen (nachgemessen)

Messskript über dieselben Schritte wie die Tests, `DiskObjectStore.__getitem__` nach Objekttyp gezählt, dazu die Zahl der Vorfahren mit `commit_time >= HEAD.commit_time`, Loose-Objekte und Packs:

| Umgebung | Uhr | Lesen | Survey | alte Commits in HEADs Sekunde | Packs |
|---|---|---|---|---|---|
| WSL2, py 3.12.3 / 3.13.15 / 3.14.7 | alle Commits in **einer** Sekunde | **194** (192 commit, 2 tree) | 192 | 121 / 120 | 0 |
| dieselben | jeder Commit eigene Sekunde | 22 | 21 | 0 | 0 |
| WSL2, py 3.13, echte Uhr (≈ 34 Commits/s) | echt | 43, 67 | 21, 24 | 15, 31 / 0, 2 | 0 |
| Docker `python:3.13`, `/tmp` Overlay (≈ 41 Commits/s) | echt | 22–52 | 21–54 | 0–23 | 0 |
| Docker `python:3.13`, `/tmp` tmpfs (≈ 105 Commits/s) | echt | 22–115 | 52–**154** | 0–90 | 0 |

Die Reads wachsen linear mit der Zahl der Commits in HEADs Sekunde (Lesen ≈ 20 + 1,45·n). Die Grenze 150 wird ab etwa n ≈ 90 gerissen – das braucht mindestens rund 90 Commits pro Sekunde. WSL2 schafft 34, kann also nie rot werden. tmpfs schafft 105 und hat den CI-Fehler in einem vollen Suite-Lauf **von selbst** reproduziert: `the survey cost 157 objects after one save`.

Mit dem **echten** Test (unverändert, Uhr nur per Plug-in auf `dulwich.worktree.time` gesetzt):

- Uhr eingefroren: `reading after one save cost 194 objects` und `the survey cost 192 objects` – beide rot, in Python 3.13 und 3.14. **194 ist exakt der Wert aus Lauf 36709155135.** Das ist der Fall »alle 121 in einer Sekunde«.
- Uhr eine Sekunde pro Commit: beide grün, jedes Mal.

Der Index wird dabei **nicht** neu gebaut. Instrumentiert: `_built_index` läuft pro Test genau einmal (beim ersten Lesen), die gemessene Leseoperation geht durch `_extended_index`, das einen Index mit genau einem neuen Commit zurückgibt – und in diesem Aufruf stecken 186 der 194 Reads. Der Neubau zum Vergleich: **494** Reads bei 120 Rausch-Commits. Die Fehlermeldung beider Tests (»the index was thrown away and built again«, »it walked the whole history again«) behauptet also etwas, das nicht passiert ist.

### Bewiesen (CI-Logs)

Zeitstempel der `PASSED`/`FAILED`-Zeilen, Abstand zur vorigen Zeile = Dauer des Tests (122 Commits):

| Lauf | Job | `…costs_the_change…` | `…survey_walk_again…` |
|---|---|---|---|
| 36709155135 | 3.13 | **1,09 s, FAILED (194)** | 5,37 s, passed |
| 36709155135 | 3.12 | 3,35 s, passed | 2,92 s, passed |
| 36744716047 Versuch 1 | 3.13 | 1,14 s, passed | **1,34 s, FAILED (154)** |
| 36744716047 Versuch 1 | 3.12 | 1,34 s, passed | 1,33 s, passed |
| 36744716047 Versuch 2 | 3.13 | 1,41 s, passed | 1,39 s, passed |

Fundstellen: `AssertionError: reading after one save cost 194 objects behind 120 other commits` (Lauf 36709155135, Job 3.13, 11:32:57), `AssertionError: the survey cost 154 objects after one save` (Lauf 36744716047, Versuch 1, Job 3.13, 16:31:08). Die Runner schaffen also etwa 90–110 Commits pro Sekunde; der 194er-Lauf war der schnellste aller Läufe (≈ 112/s), die 121 alten Commits passten damit komplett in HEADs Sekunde. Der 3.12-Job in Lauf 36709155135 lief dreimal langsamer (3,35 s) und konnte gar nicht rot werden.

### Wahrscheinlich

- Die lokale Streuung (26 in der vollen Suite, 46 allein) ist dieselbe Uhrphase: Wie viele Commits in die letzte Sekunde fallen, hängt davon ab, wo innerhalb einer Sekunde die Rauschschleife endet. Mit fester Uhr verschwindet die Streuung vollständig (194/22, bei jeder Wiederholung).
- Die Zahlen im Docstring (»22 reads or in 61«, `tests/test_store.py:3897–3898`) waren schon damals diese Uhrphase, nicht das Packen – bei 60 bzw. 240 Commits und 30–40 Commits/s liegt das genau in der gemessenen Spanne. Nachgemessen ist das für den Stand von 2026-09-07 nicht.

### Offen

- Warum der Survey-Test in Lauf 36709155135 5,37 s brauchte statt ≈ 1,4 s. Für das Ergebnis unerheblich (grün, und ein langsamer Lauf senkt den Zähler nur), aber nicht erklärt.
- Welche Umgebung auf den GitHub-Runnern die Rate von ≈ 100/s liefert (Dateisystem, `fsync`-Kosten). Nachgestellt ist nur, dass tmpfs im Container dieselbe Rate und dieselben Werte liefert – nicht, dass der Runner tmpfs benutzt.

### Nebenbefund mit Produktbezug (Hinweis)

Dasselbe Verhalten gilt außerhalb der Tests. Nachgemessen: Springt die Systemuhr eine Stunde zurück (etwa durch NTP nach einem Neustart mit falscher RTC), ist jeder neue HEAD älter als sein Vorgänger, und **jedes** Fortschreiben läuft über die ganze Historie (194, 197, 199 Reads bei 120 Commits), bis die Uhr aufgeholt hat. Richtig bleibt das Ergebnis, nur teurer – immer noch unter dem Neubau, weil der Walker keine Bäume vergleicht. Wie groß das auf der Prüfbank mit 7407 Commits ist, ist nicht gemessen. Gehört nicht in #46, sondern gegebenenfalls in ein eigenes Issue.

## 2. Die fünf Vermutungen

1. **Automatisches Packen – trifft nicht zu.** `gc.auto`-Schwelle 6700, der Test erreicht 366 Loose-Objekte; `packs=0` in jeder einzelnen Messung, auch bei 194. Der Satz »moves with packing« im Docstring ist falsch.
2. **Pack- oder Loose-Verteilung – trifft nicht zu.** Es gibt in diesen Tests keine Packs. Die Mehrreads sind Commit-Objekte, gelesen vom Walker, nicht ein anderer Lesepfad.
3. **Dateisystem oder Zeit – trifft zu, aber anders als vermutet.** Nicht `mtime` oder Schreibreihenfolge, sondern die Commit-Zeit in ganzen Sekunden. Das Dateisystem wirkt nur mittelbar, über die Commit-Rate: Overlay im Container ≈ 41/s und nie rot, tmpfs ≈ 105/s und rot (157).
4. **Modulweiter Zustand, Testreihenfolge – trifft nicht zu.** Beide Tests legen eigene `HistoryStore`-Instanzen in eigenen `tmp_path`s an; mit fester Uhr ist das Ergebnis deterministisch und gleich dem CI-Wert, ganz ohne vorherige Tests. Dass Zustand aus Vortests einen kleinen Beitrag leistet, ist nicht bis ins Letzte ausgeschlossen, zur Erklärung aber nicht nötig.
5. **Unterschied Python 3.12/3.13 – trifft nicht zu.** Mit fester Uhr liefern 3.12.3, 3.13.15 und 3.14.7 dieselben Zahlen (194/192 bzw. 22/21). Dass nur der 3.13-Job rot war, ist Zufall der Runner-Geschwindigkeit und der Uhrphase (siehe Tabelle der Logs).

Die unterschiedliche Zahl übersprungener Tests (CI 5, lokal 2) hat mit dem Befund nichts zu tun: Übersprungen werden die Fälle gegen echte Dashboards in `test_analyze.py` und `test_yaml_io.py`, die ohne `.real-storage` nicht laufen; keiner davon berührt ein Repository.

## 3. Vorschlag (nicht umgesetzt)

Die gemessene Spanne: Fortschreiben kostet bei 120 Rausch-Commits **22 bis 194** Reads, je nach Uhr; der Neubau, gegen den die Tests schützen sollen, kostet **494**. 194 ist die obere Schranke, weil der Walker nie mehr als die ganze Historie lesen kann. Die Grenze 150 liegt mitten in der Streuung des *richtigen* Pfads.

**Kleinste Änderung, die das Problem löst:**

- Die Grenze in beiden Tests auf **300** setzen: über dem schlechtesten Fall des Fortschreibens (194), klar unter dem Neubau (494), unabhängig von Uhr und Maschine.
- Die Docstrings korrigieren: nicht »packing«, sondern »how many of the commits fell into the same second as HEAD – dulwich's walker steps over those even when excluded«, mit den Zahlen 22/194/494.
- Die beiden Fehlermeldungen ehrlicher formulieren, damit ein Reißen nicht wieder als »neu gebaut« gelesen wird.

**Bewusst nicht getan:**

- Die Uhr im Test festnageln (etwa `dulwich.worktree.time` patchen). Das gäbe stabile 22 und eine enge Grenze, hängt aber an einem internen Modulattribut von dulwich – die erste Fassung meiner Instrumentierung hat genau daran vorbeigepatcht, weil der Zeitstempel inzwischen in `worktree.py` statt `repo.py` gesetzt wird. Das bricht beim nächsten dulwich-Update leise.
- `store.py` ändern. Das Testproblem ist mit der Grenze gelöst.
- Die Zahl der Rausch-Commits erhöhen, um den Abstand zu vergrößern: macht den Test langsamer und verschiebt nur die Schwelle.

**Option (»Was würde ein Senior-Entwickler tun?«), getrennt von #46:** `_extended_index` braucht den zeitgeordneten Walker nicht. Die Historie dieses Stores ist linear, das Fortschreiben könnte vom neuen HEAD über den ersten Elternteil zurückgehen, bis es `cached.head` trifft (und `None` liefern, wenn es einen bereits indizierten Commit oder die Wurzel trifft). Dann kostet es genau die neuen Commits, unabhängig von der Uhr – das behebt auch den Nebenbefund mit der zurückspringenden Uhr, und der Test könnte eine enge Grenze tragen. Das ist eine Produktänderung an einer Stelle mit zwei bewusst gehaltenen Sicherungen (Docstring von `_extended_index`) und braucht deshalb einen eigenen Plan und eigene Tests, etwa gegen Merge-Commits, die der Store heute nie schreibt.

## 4. Urteil

Ursache gefunden und deterministisch reproduziert: Der CI-Wert 194 entsteht exakt, wenn alle Commits in einer Sekunde liegen, und der tmpfs-Container reißt die Grenze ohne Eingriff. Kein Produktfehler im getesteten Verhalten – der Index wird korrekt fortgeschrieben, die Grenze ist zu eng für die Uhrabhängigkeit des dulwich-Walkers. **Behebbar mit der kleinsten Änderung aus Abschnitt 3**; der Nebenbefund zur zurückspringenden Uhr ist ein *Hinweis* für ein eigenes Issue.
