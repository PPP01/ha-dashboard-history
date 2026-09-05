# Die drei Restbefunde der Panel-Hälfte: Wächter statt Reparaturen

Gearbeitet im Worktree `ha-dashboard-history-h`, Branch `vorhaben-h`,
ausgehend von `a1d6d6a`. Grundlage: `final-panel-rereview.md` (N1, N2, N3)
und `final-panel-fixes.md`.

`python3 -m pytest tests/ -q` vorher **343 passed, 3 skipped**, nachher
**349 passed, 3 skipped** — sechs neue Fälle, ein umgeschriebener, und
jede einzelne Zusicherung durch einen wieder eingebauten Fehler gemessen.

`python3 -u tests/integration/run_checks.py`: **131 von 131**, kein FAIL.
(Der Lauf davor meldete »the panel module URL carries a fingerprint of
the file« — Home Assistant hatte den Fingerabdruck beim Start berechnet,
`panel.js` wurde danach geändert. Nach `docker restart` sauber.)

Drei Commits, jeder für sich lauffähig und gemessen:

| Commit | Inhalt | Suite |
|---|---|---|
| `f78b36a` | N3 — ein gescheitertes Nachladen sagt es | 345 passed |
| `a506062` | N2 — die sechs Wächter | 348 passed |
| `641b940` | N1 — der umgeschriebene Fall | 349 passed |

---

## N2 (Important) — sechs richtige Stellen, die nichts festhielt

Der Code war an allen sechs Stellen richtig; das hat das Nach-Review
geprüft. Was fehlte, war der Wächter: jede der sechs Rücknahmen ließ die
ganze Suite grün. `_createVersion` kam im Verhaltenstest überhaupt nicht
vor, obwohl es dieselbe C1-Reparatur trägt wie `_confirm` und `_forget`
und mit `create_version` schreibt.

**Was geändert wurde** (nur `tests/test_panel_behaviour.py`):

- Das Szenario `_WRONG_DASHBOARD` bekommt vier weitere Läufe. Der Aufbau
  stand schon; neu sind die Abläufe selbst:
  - Lauf 3 — ein anderes Dashboard wird gewählt, *während* der
    Versionsdialog seine drei Nummern holt. Er darf dann gar nicht
    aufgehen (Anspruchsschein).
  - Lauf 7 — dieselbe Verschiebung an `_select` vorbei, sodass der Schein
    gültig bleibt und allein die festgehaltene Variable entscheidet, auf
    welchem Dashboard der Tag landet.
  - Läufe 8 und 9 — `_restoreItem` und `_undoChange`, die zwei übrigen
    Closures derselben Form. Beide reichen ihre Promise nicht heraus, also
    werden sie über `settle()` getrieben statt abgewartet.
- Das Szenario `_WRITE_KEEPS_SEARCH` bekommt zwei weitere Abläufe:
  ein Zurückholen über `_confirm` und eine Version über `_createVersion`,
  beide von einem Treffer aus, den der Server gefunden hat. Bisher war
  nur `_describe` gemessen, obwohl alle drei aus demselben Grund von
  `_select` weggezogen wurden.
- Der gemeinsame DOM-Stand-in lernt drei Nichtstuer: `setAttribute`,
  `focus` und `select`. Ohne sie ist der Versionsdialog (er drückt seine
  Stufenknöpfe mit `setAttribute` zurecht und setzt den Cursor ins
  Titelfeld) schlicht nicht ausführbar — aus einem Grund, der mit dem
  nichts zu tun hat, was er tut.

Ein Detail, das ein falsches Grün verhindert hat und deshalb hier steht:
Lauf 3 sichert zusätzlich `asked: sent[0].type` zu. Ohne diese Zeile wäre
der Lauf auch dann grün gewesen, als er in Wahrheit an seiner ersten
Zeile stehen blieb — die beiden Läufe davor gehen durch das echte
`_select`, und das ersetzt `_changes` durch das, was die Antwort trug.
Gemessen, nicht vermutet: die Zusicherung war beim ersten Durchlauf rot.

## N1 (Important) — ein Fall, der ohne seinen Gegenstand bestand

`test_the_held_render_runs_when_the_dialog_closes` blieb grün, wenn man
den Nachhol-Render in `_answerFrom` (`panel.js:939`) ausbaute: Der Fall
drückte *Apply*, und auf diesem Weg rendert `_confirm` hinterher ohnehin
noch einmal — der `_guard` des Schreibvorgangs setzt `_renderOwed` selbst
zurück, und `rows` schreibt `_loadOlder` unabhängig von jedem Render.

Die Zeile entscheidet auf dem **abgebrochenen** Weg: `_confirm`,
`_describe` und `_createVersion` kehren bei einer Antwort, die nicht die
gewünschte ist, zurück, ohne je wieder zu rendern. Eine Seite, die
während des Dialogs zurückgehalten wurde, bliebe für immer unsichtbar.

**Was geändert wurde:** Das Szenario `_DIALOG_SURVIVES` bekommt einen
zweiten Ablauf, in dem der Dialog **abgelehnt** wird. Der Stand-in-Root
merkt sich, was zuletzt in `innerHTML` geschrieben wurde (`_written`) —
das ist die Seite, die ein Mensch vor sich hätte, und ohne sie lässt sich
»ist der zurückgehaltene Render je auf dem Bildschirm angekommen?« gar
nicht fragen. Der neue Fall
`test_a_page_held_back_reaches_the_screen_when_the_dialog_is_refused`
sichert zu: die ältere Seite steht **nicht** auf dem Bildschirm, solange
der Dialog steht (`heldBack`), und steht dort in dem Moment, in dem er
schließt (`onScreen`), mit `_renderOwed` zurück auf `false`.

Der alte Fall bleibt unter seinem Namen stehen, aber nur noch mit dem,
was er wirklich misst (die Schuld wurde aufgenommen, der Ablauf kam zu
Ende); die Zusicherung über die Zeilen zieht in den neuen Fall um.

## N3 (Minor) — ein gescheitertes Nachladen sagte nichts mehr

Die drei schreibenden Abläufe endeten auf `_refreshQuietly()`, das seine
Fehler verschluckt, und die Folgezeile in `_confirm` setzte
`this._error = said || null` — löschte den Banner also ausdrücklich.
Ergebnis: Der Schreibvorgang gelingt, das Nachladen scheitert, die Seite
steht mit dem Stand von vor dem Schreiben da, und nichts sagt warum.
Dazu fehlte in diesem Fenster das »working…«, weil `_refresh` nicht durch
`_guard` läuft.

**Die ehrliche Antwort** ist nicht, `_refreshQuietly` lauter zu machen:
Dessen Stille ist für den Refresh gedacht, den *niemand* bestellt hat
(ein Speichern anderswo in Home Assistant kündigt sich an) — dort wäre
ein Banner aus dem Nichts schlimmer als eine kurz veraltete Seite. Für
das Nachladen nach einem Schreibvorgang gilt das Gegenteil.

**Was geändert wurde** (`panel.js`):

- Neu `_reloadAfterWrite(done)`: lädt über `_refresh` neu, hebt dabei den
  Betrieb-Zähler (also »working…«), und **antwortet** mit einem Satz, wo
  es scheiterte — `` `${done}, but the page could not be reloaded: …` `` —
  bzw. mit `null`, wo es durchkam. `done` benennt, was *gelungen* ist, damit
  der Satz beide Hälften trägt.
- `_confirm` setzt `this._error = [said, stale].filter(Boolean).join("; ")`
  — `said` zuerst, weil die Antwort des Schreibvorgangs die wichtigere
  Hälfte ist; der zweite Satz erklärt, warum die Seite darunter nicht
  nachgezogen hat.
- `_describe` und `_createVersion` setzen den Satz und rendern, wo es
  einen gibt.
- Der Kommentarabsatz von `_refreshQuietly` wurde nicht gelöscht, sondern
  aufgeteilt: die Begründung »nicht `_select`, weil das die Suche wegwirft«
  zieht mit an die neue Stelle, `_refreshQuietly` behält (und schärft) die
  eigene.

Die Panel-Regel bleibt gewahrt: hier wird nichts entschieden, was der
Server entscheiden könnte — es wird nur gesagt, was ohnehin passiert ist.

---

## Messungen

Jeder Fehler einzeln wieder eingebaut, danach `python3 -m pytest tests/ -q`
über die **ganze** Suite, danach zurückgesetzt. Ohne Fehler:
`349 passed, 3 skipped`.

### Die sechs Rücknahmen aus N2

| Wieder eingebaut | Ergebnis | Wer fängt es |
|---|---|---|
| `_restoreItem`-Closure liest wieder `this._selected` | 1 failed | `test_every_flow_that_writes_carries_its_own_dashboard` |
| `_undoChange`-Closure liest wieder `this._selected` | 1 failed | `test_every_flow_that_writes_carries_its_own_dashboard` |
| `_createVersion` schreibt wieder gegen `this._selected` | 1 failed | `test_every_flow_that_writes_carries_its_own_dashboard` |
| `if (!mine() \|\| !offered)` wieder ohne `mine()` | 1 failed | `test_a_dashboard_picked_while_the_numbers_are_out_cancels_the_version` |
| `_confirm` endet wieder auf `_select` | 3 failed | `test_a_restore_and_a_version_leave_the_search_standing`, dazu `…reload_that_failed…says_so` und `…says_it_is_working` |
| `_createVersion` endet wieder auf `_select` | 2 failed | `test_a_restore_and_a_version_leave_the_search_standing`, dazu `…reload_that_failed…says_so` |

Vorher waren alle sechs grün (im Nach-Review nachgemessen).

### Der umgeschriebene Fall aus N1

| Wieder eingebaut | Ergebnis | Wer fängt es |
|---|---|---|
| `if (this._renderOwed) this._render();` aus `_answerFrom` entfernt | 1 failed | `test_a_page_held_back_reaches_the_screen_when_the_dialog_is_refused` |

Der alte Fall (`test_the_held_render_runs_when_the_dialog_closes`) bleibt
dabei grün — genau das war der Befund, und genau deshalb steht die
Zusicherung jetzt woanders.

### Die neue Zeile aus N3

| Wieder eingebaut | Ergebnis | Wer fängt es |
|---|---|---|
| `_reloadAfterWrite` verschluckt den Fehler wieder (`return null`) | 1 failed | `test_a_reload_that_failed_after_a_write_says_so` |
| `_reloadAfterWrite` hebt den Betrieb-Zähler nicht | 1 failed | `test_the_reload_after_a_write_says_it_is_working` |

---

## Was ich stehen lasse

- **Die letzte Zeile der N2-Tabelle** (`_claim("search")` aus `_select`
  entfernt; Suche teilt sich wieder den `changes`-Slot) ist laut
  Nach-Review harmlos: `_refresh` stellt die Frage selbst neu, und
  »Load older« ist während einer laufenden Suche gar nicht sichtbar. Der
  eigene Slot bleibt richtig und bleibt unbelegt — ein Wächter dafür
  müsste ein Verhalten festhalten, das sich von selbst zurückholt.
- **Die Lücke nach *Apply*** (Seitenleiste ist während des Schreibens
  wieder bedienbar; der Banner kann am falschen Dashboard landen) bleibt
  wie im Nach-Review beschrieben: eine Meldung am falschen Ort, kein
  Schreibvorgang am falschen Ort, und vor der Welle war es genauso.
- **Die Reihenfolge im Banner** bei gleichzeitigem `said` und
  gescheitertem Reload ist eine Entscheidung, keine Messung: die Antwort
  des Servers steht vorn.
