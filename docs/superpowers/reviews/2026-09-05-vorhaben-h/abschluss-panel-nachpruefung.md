# Nach-Review der Reparaturwelle (Panel-Hälfte)

Gelesen ausschließlich lesend im Worktree `ha-dashboard-history-h`, Branch
`vorhaben-h`, Stand `a1d6d6a`. Grundlage: `final-panel-review.md`,
`final-panel-fixes.md`, `final-panel-fixes.diff` sowie beide Dateistände
(`9be8aad` und HEAD).

Die Fehlereinbau-Messungen sind **nicht übernommen, sondern eigenständig
nachgemessen**: eine Arbeitskopie von `custom_components/` und `tests/` im
Scratchpad, 24 einzeln eingebaute Fehler, nach jedem
`python3 -m pytest tests/test_panel_behaviour.py -q`, danach zurückgesetzt.
Im Worktree wurde nichts verändert.

---

## Pflichtprüfungen

- `python3 -m pytest tests/ -q` → **343 passed, 3 skipped**. ✔
- Fünf Commit-Betreffe, Länge 39/48/40/41/45 Zeichen, alle im Imperativ und
  großgeschrieben; kein Body-Zeile über 72 Zeichen; alle fünf tragen
  `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. ✔
- Alles Lesbare ist Englisch: die einzige Nicht-ASCII-Ergänzung im ganzen
  Diff ist das Auslassungszeichen `…` in »Searching the whole history…«.
  Keine deutsche Zeile in JS oder Tests, kein Pfad, keine Adresse, kein
  Geheimnis (geprüft mit denselben Mustern wie im Erst-Review). ✔

---

## Die sechs Punkte

### 1. Critical — Vorschau und Schreibvorgang am selben Dashboard — **ADDRESSED**

Alle fünf Stellen der Form sind erreicht, nicht vier:

- `_confirm` (`panel.js:766`) hält `asked` vor dem ersten `await` fest und
  reicht es als drittes Argument in beide Aufrufe der Closure.
- `_restoreItem` (`1206`), `_restoreState` (`1218`) und `_undoChange`
  (`1240`) nehmen `dashboard` entgegen; keine der drei Closures liest
  `this._selected` noch. Gegengeprüft mit `grep` über *alle* Vorkommen von
  `_selected` — die verbleibenden liegen in `_refresh`, `_loadOlder`,
  `_search`, `_detailFor` und den Rendermethoden, also auf reinen
  Lesepfaden.
- `_forget` (`1160`, Schreibaufruf `1198`) — die teure Stelle — hält
  ebenfalls fest, und der Dialogtext wird aus demselben `asked` gebaut.
- `_createVersion` (`1052`, Schreibaufruf `1124`) ebenso.
- `_describe` braucht es nicht: es adressiert über `revision` allein und
  öffnet seinen Dialog ohne dazwischenliegendes `await`.

Der zweite Teil — der neue Slot `write` — ist sauber verdrahtet: beansprucht
von `_confirm`, `_forget` und `_createVersion` je genau einmal vor der
Vorschau, entwertet von `_select` (`471`), von niemandem sonst und nirgends
zweimal oder zu früh. Der Vorschau-`_guard` bekommt `mine` als
`stillWanted`; das späte Scheitern legt seinen Banner nicht mehr über das
inzwischen gewählte Dashboard.

Die Begrenzung »nur bis zum Dialog« trägt: `showModal()` macht den Rest der
Seite inert, und `_onRecorded` tritt bei offenem Dialog zurück.

*Nachgemessen:* Closure wieder auf `this._selected` → 1 rot;
`!mine() ||` aus `_confirm` bzw. `_forget` entfernt → je 1 rot;
`forget`-Bestätigung wieder live → 1 rot; `asked` in `_confirm` entwertet →
2 rot; `_claim("write")` aus `_select` entfernt → 2 rot. Die Messungen des
Berichts sind reproduzierbar.

*Restliche Lücke, ausdrücklich klein:* Nach *Apply* ist die Seitenleiste
während des Schreibens und der bis zu drei Sekunden `_recorded()` wieder
bedienbar. `_confirm` lädt danach über `this._selected` neu und setzt den
Banner (`901`/`908`) gegen das dann gewählte Dashboard. Das ist eine
Meldung am falschen Ort, kein Schreibvorgang am falschen Ort, und es war
vor der Welle genauso (`await this._select(this._selected)`). Siehe N3.

### 2. I4 — Ein Render zerreißt einen offenen Dialog — **ADDRESSED**

`_render` (`1707`) tritt zurück, solange `dialog[open]` antwortet, und merkt
sich `_renderOwed`; `_answerFrom` (`933`) begleicht die Schuld im
`close`-Handler, **vor** dem `resolve` und ohne `await` darin. Alle vier
`showModal()`-Stellen (`847`, `1014`, `1118`, `1194`) warten über
`_answerFrom` — keine eigene Wartestelle blieb stehen.

Die Nachfolge-Frage »was liest der Aufrufer nach dem Nachhol-Render?« ist
durchgezogen: `_describe` liest `field.value`, `_createVersion`
`title.value`/`description.value` und die Closure-Variable `level`,
`_confirm` `_keepChoice(keepBlock)` — alles Referenzen, die vor `showModal()`
genommen wurden und den Austausch des Shadow-DOM überleben. Die eine
Stelle, die früher neu suchte (`_keepChoice`), tut es nicht mehr.

Das Szenario `_DIALOG_SURVIVES` lässt den echten `_render` laufen; der
Stand-in-Root beantwortet `dialog[open]` ehrlich und wirft seine Kinder beim
Schreiben von `innerHTML` weg. Das ist die Eigenschaft, auf die es ankommt.

*Nachgemessen:* Zurückhaltung aus `_render` entfernt → 3 rot;
`_keepChoice` sucht wieder selbst → 1 rot. **Aber:** die *zweite* Hälfte —
der Nachhol-Render in `_answerFrom` — ist ungedeckt, siehe N1.

### 3. I1–I3 und der Ein-Zeichen-Fall — **ADDRESSED**

Die Wurzel ist repariert: `_shown()` (`649`) gibt `null` zurück, wo niemand
geantwortet hat, und `_renderMain` (`1601`) schreibt darüber keinen
Absolutsatz mehr. `_shown()` hat genau einen Verbraucher — geprüft —, also
gibt es keine Stelle, die das neue `null` nicht verträgt.

Dazu die zwei Ursachen: `_setMode` (`190`) stößt eine stehende Suche in den
Begriffen des neuen Modus neu an; die Suche hat einen eigenen Slot (`570`),
und `_refresh` (`366–372`) stellt eine stehende Frage selbst neu, wodurch
auch der Nebenbefund (überlebendes `_found` nach einem Refresh) erledigt
ist, weil `_search` zuerst `_found = null` setzt.

`_searchNote` (`1546`) sagt jetzt beim Ein-Zeichen-Fall, *warum* nichts
gefragt wurde. Der verbliebene stille Zweig (`_found === null` →
`""`) ist nicht mehr erreichbar: er setzt voraus, dass ein Lauf ohne
`_searching` und ohne Nachfrage endet, und genau das kann nur noch über
einen entwerteten Slot passieren, den nichts mehr entwertet.

*Nachgemessen:* `_shown()` wieder `this._found || []` → 2 rot; `_setMode`
fragt nicht neu → 3 rot; Kurz-Query-Satz entfernt → 1 rot; `_renderMain`
schreibt bei `null` wieder »Nothing matches.« → 2 rot.
Der Slot-Wechsel allein (`search` → `changes`) macht **nichts** rot, siehe
N2.

### 4. I5/I6 — Der einfache Modus unter einer Suche — **ADDRESSED**

`renderSimple` (`simple.js:34`) nimmt `versions` (vollständig) für den
»Right now«-Satz und `shown` (gefiltert) für die Zeilen; `_renderMain`
(`1590`) reicht beide. Der Satz stammt damit wieder aus `same_as_now` des
Servers über *alle* Versionen.

Die Beschriftung lautet »The newest N changes in this version« bzw. »The
newest change in this version«. Der Satz ist tatsächlich immer wahr:
`inside` beginnt an der eigenen Änderung der Version (der neuesten
Änderung, die sie umfasst) und läuft abwärts bis zur nächsten Version, wird
also ausschließlich am älteren Ende vom Fenster beschnitten.

Der bewusst gelassene Teil (`start < 0` → gar kein Zusammenklappen) ist im
Code begründet und laut Auftrag nicht zu melden.

*Nachgemessen:* `here` wieder aus `shown` → 1 rot; Beschriftung wieder
absolut → 1 rot.

### 5. I7 — Ein Schreibvorgang wirft die Suche weg — **ADDRESSED**

`_describe` (`1030`), `_createVersion` (`1144`) und `_confirm` (`901`) enden
auf `_refreshQuietly()`. `_refresh` fasst `_query` nicht an, hält die offene
Zeile über `_changeAt` (das beide Listen fragt) und stellt die Frage neu.
`_confirm` braucht deshalb kein eigenes `_loadDashboardsQuietly` mehr — die
Dashboard-Liste liest `_refresh` selbst, also findet ein neu angelegtes
Dashboard weiterhin in die Seitenleiste.

Die Banner-Zeile, die dabei anfiel (`threw`, `895`), ist richtig: der Reload
räumt den Banner beim Eintreten weg, die Meldung wird vorher genommen und
hinterher mit dem Rest gesetzt.

*Nachgemessen:* `_describe` wieder auf `_select` → 1 rot. `_confirm` und
`_createVersion` wieder auf `_select` → **0 rot**, siehe N2.

### 6. I8 — `simple.js` und `rows.js` ohne Verhaltenstest — **ADDRESSED**

Sieben neue Fälle. `rows.js` wird direkt importiert und über `sections`,
`versionHead`, `renderRow` und `someNames` geprüft; der einfache Modus läuft
über `el._renderMain()`, sodass auch die Verdrahtung in `panel.js`
mitgeprüft wird.

*Nachgemessen:* `someNames` schneidet erst ab vier → 1 rot; `sections`
eröffnet keinen neuen Abschnitt → 1 rot; dazu die beiden `simple.js`-Fehler
oben. Alle vier fallen.

---

## Was nachweislich nicht schwächer wurde

- **Kein erklärender Kommentar ist verlorengegangen.** Die entfernten
  Kommentarzeilen sind ausnahmslos durch längere an derselben Stelle ersetzt
  (`_shown`, `_confirm`s Banner-Absatz, `_armKeep`/`_keepChoice`,
  `renderSimple`s Kopf). Verglichen gegen
  `git show 9be8aad:…/panel.js`.
- **Keine Zusicherung wurde entfernt oder gelockert.** Der gesamte
  Test-Diff enthält genau eine gelöschte Zeile, und die ist die um
  `dataset: {}` erweiterte Eigenschaftsliste des Stand-ins.
- **Keine doppelt genommenen oder zu früh freigegebenen Tickets.** Die vier
  Slots werden von genau den Stellen beansprucht, die sie füllen; `_select`
  entwertet alle vier.
- **Kein Render, der nicht mehr stattfindet.** Der einzige neue
  Rückzugspfad in `_render` zahlt die Schuld in `_answerFrom` zurück; jeder
  Zweig von `_confirm`, `_describe`, `_createVersion` und `_forget`
  hinterher rendert oder wurde vom Nachhol-Render bedient.
- **Kein `await` in einem Dialog-Handler.** Der `close`-Handler in
  `_answerFrom` ruft `_render()` synchron und löst danach auf.
- **Kein Zustand, der auf einem Pfad geräumt wird, der ihn brauchte.**
  `_refresh` an Stelle von `_select` behält `_query`, `_found`, `_open`,
  `_verOpen` — und `_createVersion` verlässt sich auf `_verOpen`.

---

## Neue Befunde

### N1 (Important, Testabdeckung) — `test_the_held_render_runs_when_the_dialog_closes` besteht auch ohne die Sache, die es benennt

`tests/test_panel_behaviour.py:1549` gegen `panel.js:939`.

Baut man `if (this._renderOwed) this._render();` aus `_answerFrom` aus,
bleibt die Datei **grün** (nachgemessen: 0 rot). Die Zusicherung
`caughtUp is False` liest `_renderOwed` erst, nachdem `_confirm` den
`_guard` des Schreibvorgangs betreten hat — und dessen `_render()` läuft bei
inzwischen geschlossenem Dialog und setzt `_renderOwed` selbst auf `false`.
Die zweite Zusicherung (`rows == ["a","b"]`) liest `_changes`, das
`_loadOlder` unabhängig von jedem Render gesetzt hat.

Der Nachhol-Render ist nicht Zierde: Wird der Dialog **abgebrochen**,
kehrt `_confirm` bei `if (answer !== "apply") return;` zurück, ohne je
wieder zu rendern — dieselbe Lage in `_describe` und `_createVersion`. Ohne
`_answerFrom`s Zeile bliebe die zurückgehaltene Seite (die ältere Seite,
die Suchtreffer, der Fehlerbanner) für immer unsichtbar. Das ist eine
leisere Wiederkehr genau des Fehlers, den I4 beheben sollte.

Der Fix-Bericht behauptet das auch nicht: seine Messung baut die
*Zurückhaltung* aus, nicht die Rückzahlung. Die Zusicherung fehlt trotzdem.
Ein Fall, der nach einem *abgebrochenen* Dialog prüft, dass die inzwischen
geladene ältere Seite auf dem Bildschirm ankommt, schließt die Lücke.

### N2 (Important, Testabdeckung) — Drei der fünf C1-Stellen und zwei der drei I7-Stellen sind ungedeckt

Nachgemessen, jeweils **0 rot**:

| Fehler wieder eingebaut | Ergebnis |
|---|---|
| `_restoreItem`-Closure liest wieder `this._selected` (`panel.js:1206`) | grün |
| `_undoChange`-Closure liest wieder `this._selected` (`1240`) | grün |
| `_createVersion` schreibt wieder gegen `this._selected` (`1124`) | grün |
| `if (!mine() \|\| !offered)` in `_createVersion` wieder ohne `mine()` (`1058`) | grün |
| `_confirm` endet wieder auf `_select` (`901`) | grün |
| `_createVersion` endet wieder auf `_select` (`1144`) | grün |
| `_claim("search")` aus `_select` entfernt (`472`) | grün |
| Suche teilt sich wieder den `changes`-Slot (`570`), `_refresh` fragt aber neu | grün |

**Der Code ist an allen diesen Stellen richtig** — das ist geprüft und in
den Verdikten oben festgehalten. Was fehlt, ist der Wächter. `_createVersion`
kommt im ganzen Verhaltenstest **kein einziges Mal** vor (`grep` → 0
Treffer), obwohl es dieselbe Reparatur trägt wie `_confirm` und `_forget`
und mit `create_version` schreibt. Die Warnung des Erst-Reviews — »eine
Reparatur, die vier von fünf erreicht, ist schlimmer als keine, weil sie
fertig aussieht« — gilt hier eine Ebene höher: die Reparatur erreicht fünf
von fünf, die Messung zwei von fünf.

Billigster Schnitt: dem bestehenden `_WRONG_DASHBOARD`-Szenario zwei Läufe
für `_createVersion` und `_undoChange` anhängen (der Aufbau steht schon) und
`test_describing_a_found_row_leaves_the_search_standing` um einen zweiten
Lauf über `_confirm` erweitern.

Der letzte Zeile der Tabelle ist harmlos: mit der Neuanfrage in `_refresh`
holt sich das Verhalten von selbst zurück, und »Load older« ist während
einer laufenden Suche gar nicht auf dem Bildschirm. Der eigene Slot bleibt
richtig, ist aber unbelegt.

### N3 (Minor) — Ein gescheiterter Reload nach einem Schreibvorgang sagt jetzt nichts mehr

`panel.js:901`/`908` (und `1030`, `1144`) gegen `9be8aad`.

Vorher endete `_confirm` auf `await this._select(this._selected)`, und
`_select` läuft durch `_guard`: Scheiterte das Nachladen, stand der
Netzfehler im Banner, und `if (said) { … }` überschrieb ihn nur dann, wenn
es etwas zu sagen gab. Jetzt endet der Fluss auf `_refreshQuietly()`, das
seine Fehler verschluckt, und die Folgezeile setzt `this._error = said ||
null` — löscht den Banner also ausdrücklich.

Folge: Der Schreibvorgang gelingt, das Nachladen scheitert (ein Ereignis,
das durch `_recorded()` schon verbraucht ist, holt es auch nicht nach), und
die Seite steht mit dem Stand von vor dem Schreiben da, ohne ein Wort. Der
Neuladen-Knopf ist da, aber nichts sagt, dass man ihn drücken müsste.
Nebenbei fehlt in diesem Fenster auch das »working…«, weil `_refresh` nicht
durch `_guard` läuft.

Zwei Zeilen: `_refreshQuietly` einen Rückgabewert geben (oder `_confirm` das
`_refresh` selbst über `_guard` fahren) und `said` nur dort löschen, wo der
Reload wirklich durchkam.

---

## Was ich nicht als Befund führe

Geprüft und für in Ordnung befunden, damit klar ist, dass es angesehen
wurde:

- `_search`s früher Rückweg lässt `_searching` stehen, wenn ein zweiter
  Tastendruck lokal trifft, während der erste Lauf noch aussteht — der Hinweis
  sagt dann kurz »Searching…« statt »N of the M loaded entries«. Steht so
  schon auf `9be8aad`, von dieser Welle nur um den Slot-Namen berührt.
- Zwei Schreib-Vorschauen kurz hintereinander: die erste fällt jetzt still
  aus, statt wie vorher `showModal()` auf einem schon offenen Dialog werfen
  zu lassen. Besser als vorher.
- Der `_refresh` in `_confirm` wartet auf die Neuanfrage der Suche, bevor der
  Banner erscheint — bei einer gewachsenen Historie also um bis zu eine
  Sekunde verzögert. Kosmetik.

Die fünf Minors des Erst-Reviews, die doppelte Trefferregel, das
`/\d+ added/`-Schnüffeln und das fehlende Zusammenklappen bei `start < 0`
sind laut Auftrag ausgenommen und wurden nicht geprüft.

---

## Empfehlung

Alle sechs Punkte sind sachlich erledigt; kein Rückschritt, keine neue
Funktionslücke im ausgelieferten Verhalten. Die zwei Important-Befunde sind
Wächter, keine Fehler: N1 ist ein Fall, der seinen eigenen Gegenstand nicht
misst, N2 sind sechs Stellen, an denen die Reparatur stimmt und nichts sie
festhält. Beide zusammen sind eine überschaubare Ergänzung an
`tests/test_panel_behaviour.py` und an keiner Stelle eine Änderung am
Panel. N3 sind zwei Zeilen in `_confirm`.
