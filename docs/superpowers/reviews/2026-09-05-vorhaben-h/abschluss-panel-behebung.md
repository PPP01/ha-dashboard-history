# Abschluss-Review, Panel-Hälfte: die Reparaturen

Gearbeitet im Worktree `ha-dashboard-history-h`, Branch `vorhaben-h`, ausgehend
von `9be8aad`. Grundlage: `final-panel-review.md`.

`python3 -m pytest tests/ -q` vorher **324 passed, 3 skipped**, nachher
**343 passed, 3 skipped** — neunzehn neue Fälle, jeder einzeln daraufhin
gemessen, dass er rot werden *kann*.

Fünf Commits, jeder für sich lauffähig:

| Commit | Inhalt |
|---|---|
| `4fa0cbe` | C1 — die Vorschau gilt dem Dashboard, für das sie geholt wurde |
| `15502d0` | I4 — ein offener Dialog überlebt eine spät eintreffende Antwort |
| `d02fe04` | I1–I3 — »noch nicht gefragt« ist nicht »nichts gefunden« |
| `313aeed` | I5, I6, I8 — der einfache Modus sagt unter einer Suche die Wahrheit |
| `a1d6d6a` | I7 — ein Schreibvorgang wirft die Suche nicht mehr weg |

---

## C1 — Eine Vorschau gilt dem Dashboard, für das sie geholt wurde

**Was war.** Die Anfrage-Closures lasen `this._selected` zum *Aufrufzeitpunkt*,
und sie werden zweimal gerufen: einmal für die Vorschau, einmal für den
Schreibvorgang. Der Dialog erscheint erst, wenn die Vorschau zurück ist —
dazwischen ist die Seitenleiste voll bedienbar.

**Was geändert wurde.**

- `_confirm` hält `const asked = this._selected` **vor** dem ersten `await` fest
  und reicht es als drittes Argument in die Closure. `_restoreItem`,
  `_restoreState` und `_undoChange` nehmen es entgegen, statt selbst zu lesen.
- Dasselbe in `_forget` (beide Aufrufe, und der Dialogtext) und in
  `_createVersion` (`next_versions` und `create_version`).
- Neuer Slot `write` im vorhandenen `_claim`-Mechanismus. `_confirm`, `_forget`
  und `_createVersion` beanspruchen ihn vor der Vorschau; `_select` entwertet
  ihn. Wechselt die Auswahl, während die Vorschau unterwegs ist, öffnet der
  Dialog gar nicht erst. Ein eigener Slot, weil eine Suche oder eine ältere
  Seite eine Vorschau **nicht** entwerten darf und `_select` schon.
- Der `_guard` der Vorschau bekommt `mine` als `stillWanted` — damit legt auch
  ein *spätes Scheitern* seinen Banner nicht mehr über das inzwischen gewählte
  Dashboard.
- Bewusst **nur bis zum Dialog**: Ist er offen, kann die Auswahl nicht mehr
  wandern (ein modaler Dialog macht den Rest der Seite inert, und
  `_onRecorded` tritt bei offenem Dialog zurück). Nach *Apply* muss der
  Schreibvorgang durchgehen — ihn dort noch zu verwerfen hieße, jemanden einen
  Knopf drücken zu lassen, ohne dass etwas passiert und ohne dass etwas gesagt
  wird.

**Neue Fälle** (`_WRONG_DASHBOARD`):
`test_a_preview_is_written_to_the_dashboard_it_was_fetched_for`,
`test_a_dashboard_picked_while_the_preview_is_out_cancels_the_dialog`,
`test_forget_deletes_the_history_the_dialog_named`,
`test_an_undisturbed_restore_still_opens_and_writes` (Kontrolle).

Die beiden Hälften der Reparatur werden **getrennt** gemessen: Lauf 4 verschiebt
`el._selected` an `_select` vorbei, sodass das Ticket gültig bleibt und allein
die festgehaltene Variable den Ausgang bestimmt; Läufe 1 und 2 gehen durch das
echte `_select`. Ob ein Ablauf überhaupt zu Ende kommt, wird mit einem
`finished()`-Helfer gemessen statt abgewartet — ein Aufrufer, der auf ein
`close` wartet, das nie kommt, soll eine Zusicherung reißen und nicht den Lauf
aufhängen.

**Messungen.**

| Fehler wieder eingebaut | Ergebnis |
|---|---|
| `restore_state`-Closure liest wieder `this._selected` | 1 failed (`…written_to_the_dashboard_it_was_fetched_for`) |
| `!mine() \|\|` aus `_confirm` und `_forget` entfernt | 2 failed (`…cancels_the_dialog`, `…the_dialog_named`) |
| `forget`-Bestätigung liest wieder `this._selected` | 1 failed (`…the_dialog_named`) |

---

## I4 — Ein offener Dialog überlebt eine spät eintreffende Antwort

**Was war.** `_render` ersetzt den kompletten Shadow-DOM samt offenem
`<dialog>`. Ein aus dem Dokument entferntes `<dialog>` feuert kein `close`, das
`await` in `_confirm` löst nie auf, der Dialog verschwindet wortlos.

**Was geändert wurde.**

- `_render` tritt zurück, solange ein Dialog offen ist, und merkt sich die
  Schuld in `_renderOwed`.
- Neues `_answerFrom(dialog)` — die eine Wartestelle für alle vier Dialoge —
  begleicht die Schuld in dem Moment, in dem der Dialog schließt.
- Der nachgeholte Render ersetzt auch das Häkchen-Feld. `_armKeep` gibt den
  Block deshalb zurück, und `_keepChoice(keep)` bekommt ihn übergeben, statt
  ihn erneut zu suchen: Eine erneute Suche fände ein frisches, leeres Feld und
  ließe die gewünschte Version stillschweigend fallen. Alle anderen Aufrufer
  lesen ohnehin über Element-Referenzen, die vor dem Öffnen genommen wurden,
  und die überleben den Austausch des Shadow-DOM.

**Sichtbar gemacht** — der Punkt, den das Review als »strukturell unerreichbar«
markiert hat, weil jedes Szenario `_render` stubbt. Das neue Szenario
`_DIALOG_SURVIVES` lässt den **echten** `_render` laufen, gegen einen
Wurzelknoten, der die eine Eigenschaft nachbildet, auf die es ankommt: Beim
Schreiben von `innerHTML` wirft er seine Kinder weg (`it._seen = {}`), und
`dialog[open]` wird ehrlich beantwortet statt mit dem üblichen
Immer-ein-Knoten. Geantwortet wird über das, was der Shadow-Root *gerade*
ausgibt — genau das, was ein Mensch anklicken kann; ein herausgerissener Dialog
ist das nicht. Nötig war dafür eine einzige Ergänzung am gemeinsamen
Stand-in: `dataset: {}` (der echte `_render` liest `element.dataset.key`).

**Neue Fälle:** `test_an_open_dialog_survives_a_page_arriving_underneath_it`,
`test_the_held_render_runs_when_the_dialog_closes`,
`test_the_kept_version_survives_the_render_that_was_held`.

**Messungen.**

| Fehler wieder eingebaut | Ergebnis |
|---|---|
| Die Zurückhaltung in `_render` entfernt | 3 failed (alle drei) |
| `_keepChoice` sucht den Block wieder selbst | 1 failed (`…the_kept_version_survives…`) |

---

## I1–I3 (und der Ein-Zeichen-Fall) — die Wurzel statt der drei Symptome

**Was geändert wurde.** `_shown()` liefert jetzt `null`, wo niemand geantwortet
hat, statt einer leeren Liste, und `_renderMain` schreibt darüber keinen
Absolutsatz mehr. Damit sind alle vier Symptome erledigt; dazu kommen die zwei
Ursachen, die überhaupt erst dafür sorgten, dass niemand gefragt wurde:

- **I1:** `_setMode` stößt eine stehende Suche in den Begriffen des neuen Modus
  neu an.
- **I2:** Die Suche bekommt einen **eigenen** Claim-Slot (`search`), den
  `_refresh` nicht mehr wegnimmt; und `_refresh` stellt eine stehende Frage
  selbst neu. Damit ist auch der Nebenbefund erledigt (`_found` überlebte einen
  Refresh und zeigte Treffer von vor der Änderung). Der Rückgabe-`return` im
  Detail-Zweig von `_refresh` wurde zu `if (detailMine())`, damit die
  Neuanfrage der Suche erreichbar bleibt.
- **I3:** Kein »Nothing matches.« mehr, während »Searching the whole history…«
  darüber steht.
- **Ein-Zeichen-Fall:** `_searchNote` sagt jetzt, *warum* nichts gefragt wurde
  (»Type a second character to search the whole history.«).

**Neue Fälle:** `test_switching_to_the_advanced_view_puts_the_standing_query`,
`test_a_running_search_does_not_also_say_nothing_matches`,
`test_a_query_too_short_to_send_says_so`,
`test_a_refresh_during_a_search_asks_the_question_again`.

**Messungen.**

| Fehler wieder eingebaut | Ergebnis |
|---|---|
| `_setMode` fragt nicht neu | 3 failed |
| `_shown()` gibt wieder `this._found \|\| []` | 2 failed |
| Suche teilt sich wieder den `changes`-Slot, `_refresh` fragt nicht neu | 1 failed |
| Der Kurz-Query-Satz aus `_searchNote` entfernt | 1 failed |

Das Szenario `_UNASKED` wurde nach der ersten Messung null-sicher gemacht
(`el._shown() && …`): Ohne die Reparatur starb es an einer Eigenschaft von
`null`, statt an seiner Zusicherung zu scheitern.

---

## I5, I6, I8 — der einfache Modus

**I5.** `renderSimple` bekommt jetzt **beide** Listen: `versions` (vollständig)
für den »Right now«-Satz, `shown` (gefiltert) für die Zeilen. Der Satz handelt
vom Dashboard, nicht von der Trefferliste — und war zugleich die einzige Stelle,
an der diese Hälfte eine vom Server beantwortete Tatsache über eine Anzeigeliste
nachrechnete.

**I6 — die ehrliche Beschriftung.** Der Server liefert für eine Version keine
Änderungszahl (`operations.async_versions` → `_version_dict`), es blieb also die
Formulierung. Gewählt: **»The newest N changes in this version«** (Einzahl: »The
newest change in this version«). Der Satz ist *immer* wahr, unabhängig davon,
was geladen ist: `inside` beginnt an der eigenen Änderung der Version und läuft
nach unten, wird also ausschließlich am *älteren* Ende abgeschnitten.

Den zweiten Teil des Befunds — bei `start < 0` fehlt das Zusammenklappen
kommentarlos — habe ich **bewusst so gelassen**, mit einem Kommentar im Code:
Auf einem Dashboard mit vielen Versionen trifft das die meisten Zeilen, und eine
Zeile Erklärung an jeder davon wäre Lärm. Ein fehlendes Zusammenklappen behauptet
nichts; eine falsche Zahl behauptet etwas Falsches.

Im **erweiterten** Modus bleibt `versionHead` unangetastet: Dort *kann* die Zahl
durch »Load older changes« richtig werden, und genau das ist der Unterschied,
den der einfache Modus nicht hat.

**I8 — die fehlende Abdeckung.** Neue Fälle für `simple.js`
(`test_the_simple_mode_says_where_the_dashboard_stands`,
`test_a_search_does_not_change_what_is_said_about_the_dashboard`,
`test_the_fold_counts_only_what_it_can_show`) und für `rows.js`
(`test_the_history_is_cut_into_sections_at_the_versions`,
`test_a_section_head_offers_the_way_back_only_where_it_leads_somewhere`,
`test_a_chip_says_which_kind_of_sameness_it_means`,
`test_a_long_list_of_names_is_cut_and_says_so`). `rows.js` wird dafür direkt
importiert; der einfache Modus läuft über `el._renderMain()`, sodass auch die
Verdrahtung in `panel.js` mitgeprüft wird.

**Messungen.**

| Fehler wieder eingebaut | Ergebnis |
|---|---|
| »Right now« wieder aus der gefilterten Liste | 1 failed (`…what_is_said_about_the_dashboard`) |
| Beschriftung wieder absolut (`N changes in this version`) | 1 failed (`…counts_only_what_it_can_show`) |
| `someNames` schneidet erst ab vier Namen | 1 failed (`…is_cut_and_says_so`) |
| `sections` eröffnet keinen neuen Abschnitt an einer Version | 1 failed (`…cut_into_sections_at_the_versions`) |

---

## I7 — Ein Schreibvorgang wirft die Suche nicht mehr weg

`_describe`, `_createVersion` und `_confirm` enden jetzt auf
`_refreshQuietly()` statt auf `_select(this._selected)`. Der Reload liest die
Dashboard-Liste, die Historie und die Versionen, behält die offene Zeile (und
holt ihre Antworten frisch) und stellt eine stehende Frage neu — `_confirm`
braucht deshalb auch kein eigenes `_loadDashboardsQuietly` mehr.

Eine Zeile fiel dabei an, die das Review als Altlast gar nicht aufführt: Der
Reload räumt den Banner beim Eintreten weg, genau wie `_select` es tat — ein
Schreibvorgang, der *geworfen* hat, verlor seine Meldung damit an eben den
Refresh, der ihm folgte. Sie wird jetzt vorher genommen (`threw`) und hinterher
mit dem Rest gesetzt.

**Neuer Fall:** `test_describing_a_found_row_leaves_the_search_standing`.

**Messung.** `_describe` wieder auf `_select` umgestellt → 1 failed.

---

## Was nicht gemacht wurde

**Ausdrücklich ausgenommen** (Plan- bzw. Spec-Vorgabe, im Review so benannt):
die doppelte Trefferregel zwischen `_wordsOf` und `store.search_changes` (P1)
und das Meldungs-Schnüffeln `/\d+ added/` (P2). Beide unangetastet.

**Minors, alle fünf gelassen:**

- **M1** — der Fokus springt bei jedem Render ins Suchfeld. Keine
  Zwei-Zeilen-Sache: Es braucht die Unterscheidung, ob der Render von einem
  Tastendruck kommt.
- **M2** — ein Netzfehler beim Detail liest sich als Verweigerung.
- **M3** — `test_the_same_failure_is_not_reported_twice` prüft die
  `||`-Reihenfolge, nicht die Bedingung im Namen. Der Code sagt das selbst;
  ich habe weder Test noch Kommentar angefasst.
- **M4** — der Entprell-Timer überlebt das Verlassen des Panels. Wäre zwei
  Zeilen in `disconnectedCallback`, fällt aber aus keiner der Reparaturen
  heraus; nach der Vorgabe gelassen.
- **M5** — `candidates[level].split()` wirft, wenn der Server eine Stufe
  ausließe.

## Prüfungen

- `python3 -m pytest tests/ -q` → **343 passed, 3 skipped**.
- `python3 -u tests/integration/run_checks.py` → **131 von 131**. Der erste
  Lauf meldete einen Fehlschlag (»the panel module URL carries a fingerprint of
  the file«): `panel.py` bildet den Fingerabdruck beim Setup, und der Container
  lief seit vor den Änderungen. Nach `docker restart dashboard-history-test`
  grün.
