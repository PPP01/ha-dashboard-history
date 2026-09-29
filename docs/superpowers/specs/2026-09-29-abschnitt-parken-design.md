# Ganze entfernte Section parken statt verweigern (GitHub #39)

Stand: 2026-09-29, überarbeitet nach dem Terra- und dem Gemini-Review desselben Tages, umgesetzt am 2026-09-29. Baut auf Entscheidung 26 (Parken, #30, Vorhaben L) und auf »Sections als Einheit« (#31, Vorhaben O, `specs/2026-09-25-sections-als-einheit-design.md`) auf.

## Ausgangslage

In einer `sections`-Ansicht wird eine ganz gelöschte Section als ein Stück erkannt (`_settle_sections`, #31). Sie exakt zurückzunehmen verlangt den atomaren `sections_list`-Beweis in `_plan_sections` (`analyze/undo.py`): Keine der *anderen* Sections der Ansicht darf seither gekommen, gegangen oder verschoben sein (`since, gone, came = _pair_view_sections(...)`, `gone or came or _moved(since)`), und höchstens eine darf seither bearbeitet worden sein. Sonst verweigert die ganze Rücknahme: *»the other sections of the view … were rearranged since, so there is no telling where these go back«*.

Gemessen am 2026-09-26 an `test-2`, Ansicht `a3`: Section entfernt, danach eine andere Section in derselben Ansicht hinzugefügt – die Rücknahme der Entfernung verweigert, obwohl jede Karte der entfernten Section bekannt ist.

Für einzelne Karten löst Entscheidung 26 dasselbe Problem längst: Lässt sich ihre Section nicht mehr beweisen, wird die Karte ans Ende der `cards:`-Liste der Ansicht geparkt (HAs »Imported cards«), und der Knopf trägt ein Sternchen. Für eine ganze Section gibt es diesen Ausweg nicht.

Zwei Wege sind betroffen, wenn auch in unterschiedlicher Breite (für Put back gilt die Verweigerung nur bei Nettoverlust von einer Section und umgeordneten oder bearbeiteten Nachbarn, etwa `[a],[b],[c]` → `[c],[b]`; kam nach der Entfernung eine Section hinzu, hatte die Ansicht wieder gleich viele Sections, `_settle_sections` erkannte keine entfernte Section und `find_removed` bot die Karten einzeln an, die Put back schon seit Vorhaben L parkt):

- **Undo** (`plan_undo` → `_plan_sections` → `apply_undo`): plant einen `UndoStep` mit `kind="sections_list"`.
- **»Put back«** (`operations.async_restore_deleted` → `_reinsertion` → `restore.parks`/`park`/`reinsert`): `parks()` verneinte `kind="section"`, `reinsert` verweigerte über `_section_gap_holds`.

## Ziel

Ist die Section bekannt, aber ihr Platz in der Reihe seither nicht mehr beweisbar, kommt sie **als Ganzes** in »Imported cards« zurück, statt dass die Rücknahme verweigert: als *eine* Karte in `cards:` der Ansicht, denn `{type: grid, cards: [...]}` ist eine Section und zugleich eine gültige Grid-Karte. Dasselbe Verhalten für beide Wege, dasselbe Sternchen, dieselbe Form der Auskunft `parked` (eine Liste von Texten: der Titel der Section, siehe Abschnitt 5). *(Geändert am 2026-09-29 nach dem Ausprobieren: Die erste Umsetzung parkte Karte für Karte; bei einer Section mit vielen Karten wären alle einzeln in eine neue Section zu ziehen gewesen – Entscheidung 8.)*

## Nicht-Ziele

- **Die Richtung »Section hinzugekommen« bleibt hart verweigert.** Sie zurückzunehmen hieße Karten *entfernen*; wenn die Reihe sich geändert hat, lässt sich nicht beweisen, welche heutigen Karten genau die der Änderung sind (Entscheidung 4, »verweigert, nie geraten«). Ein Parken gibt es dort nicht. Praktisch abgedeckt: Eine Section, die niemand mehr will, löscht man in der Oberfläche direkt. *(Festgelegt im Kommentar zu #39 nach Diskussion.)*
- **Keine gemischten Änderungen.** Hat dieselbe Änderung in derselben Ansicht *auch* eine Section verschoben, bearbeitet oder hinzugefügt, *oder* eine einzelne Karte geändert, bleibt es bei der Verweigerung. Mehrere Wirkungen in einem Schritt sind über die Oberfläche kaum herstellbar (nur per Raw-Editor oder externem Edit), und wer sie sauber ausführt, erzeugt einzelne Schritte. *(Entschieden am 2026-09-29, Variante A: kein Teil-Undo, »alles oder nichts« bleibt.)*
- **Genau eine entfernte Section je Ansicht.** `_settle_sections` erkennt eine entfernte Section nur dort, wo die Ansicht genau eine Section verloren hat (`old_counts - new_counts == 1`) und genau eine Kandidatin passt. Wurden mehrere entfernt, bleiben alle in `rest_old` und werden von der frühen Rest-Verweigerung abgewiesen. Das bleibt so; das Erweitern des Matchings ist ein eigenes Vorhaben.
- **Kein Zielwechsel.** Ein frei wählbares Dashboard oder eine Ansicht ist #40; dieses Vorhaben liefert dafür das Bauteil (eine Section als eine Grid-Karte parken).
- **Aus der geparkten Karte wird keine echte Section.** Wer sie in eine neue Section zieht, hat eine Grid-Karte in einer Section (mit eigenem Spaltenraster); ein exakter Weg bleibt allein der `sections_list`-Schritt, wo der Platz beweisbar ist. Die Einstellungen der Section (`column_span` u. Ä.) bleiben in der geparkten Karte erhalten, HA wertet sie dort aber nicht aus.
- **Kein Umbau von `apply_undo`.** Siehe unten: nicht nötig.
- **Kein Umbau von `analyze/removed.py`, `matching.py` und dem Panel.** Etiketten und Paneltexte bleiben, wie sie sind (Abschnitt 5).

## Entwurf

### 1. Wann der Parkweg greift

Der Parkweg greift im Undo genau dann, wenn alle Bedingungen zutreffen:

1. Die Ansicht hat in dieser Änderung **ausschließlich eine entfernte Section**: `removed` enthält genau eine, `moved`, `reset` und `added` sind leer.
2. Der exakte Weg würde an der Umordnung scheitern: `gone or came or _moved(since)` (Verweigerung 1) oder mehr als eine Section seither bearbeitet (Verweigerung 2). Bei reiner Entfernung sind das die einzigen beiden Verweigerungen *nach* den frühen Prüfungen von `_plan_sections`, denn die Schleife über die Indizes (»changed again after this«) läuft nur über `added`, `moved` und `reset` und ist hier leer.
3. Die frühen Prüfungen von `_plan_sections` sind bestanden und bleiben unverändert: keine Section in `rest_old`/`rest_new` dieser Ansicht (`undo.py:144`), die Ansicht ist noch auf dem Dashboard (Zeile 151), und `sections` ist in `before` und heute eine Liste (Zeile 153). Der Parkweg sitzt **hinter** diesen Prüfungen, an der Stelle der beiden Umordnungs-Verweigerungen (Zeile 167 ff.), und erbt sie damit. Dass die Ansicht heute noch `type: sections` hat, sichert die Prüfung auf `_VIEW_TYPE_REFUSAL` in `plan_undo` davor.
4. Die Änderung hat in dieser Ansicht **keine einzelne Kartenänderung** (bearbeitet, verschoben, entfernt, hinzugefügt). Die geparkten Schritte werden in den Behälter `planned["sections"]` gelegt; damit greift das vorhandene Tor `_sections_meet_cards` (`undo.py:734`) unverändert und verweigert mit `_SECTIONS_AND_CARDS_REFUSAL`, sobald derselbe Plan in derselben Ansicht auch Kartenschritte enthält. Kein neuer Code dafür; die Meldung spricht von »sections moved«, was hier nur ungefähr stimmt und bewusst so bleibt. Zusätzlich verweigert `_park_instead` selbst, wenn die Änderung in derselben Ansicht irgendeine einzelne Karte berührt hat (bearbeitet, verschoben, hinzugefügt, entfernt – auch in `cards:`); sonst bliebe das Tor `_sections_meet_cards` blind, sobald alle Karten der entfernten Section schon zurück sind und kein Section-Schritt entsteht (Plan-Review 2026-09-29).

Hält der exakte Beweis, ändert sich nichts: derselbe `sections_list`-Schritt wie heute, ohne Sternchen. **Der Parkweg ersetzt nie eine andere Verweigerung** – er springt nur an die Stelle der beiden Umordnungs-Verweigerungen.

### 2. Was weiter verweigert wird, und was nicht

| Fall | Antwort |
|---|---|
| Die Ansicht ist nicht mehr auf dem Dashboard, `sections` keine Liste, oder die Ansicht ist keine `sections`-Ansicht mehr | wie heute (frühe Prüfungen bzw. `_VIEW_TYPE_REFUSAL`) |
| Die entfernte Section war leer | wird gar nicht als entfernte Section erkannt (`_whole(…, empty_counts=False)`), bleibt in `rest_old` und wird von der frühen Rest-Verweigerung abgewiesen; kein eigener Fall, kein eigener Test |
| Die Änderung hat in derselben Ansicht auch verschobene, bearbeitete oder hinzugekommene Sections oder Kartenänderungen | Verweigerung, wie heute |
| Karten der Section stehen heute schon in der Ansicht (von Hand neu angelegt, oder ein früheres Undo derselben Änderung) | **keine Verweigerung, sondern Überspringen** (Abschnitt 3) |

### 3. Undo: ein geparkter Schritt für die ganze Section, `apply_undo` bleibt

Der Planer erzeugt **keinen** `sections_list`-Schritt für diese Ansicht, sondern **einen** Schritt für die entfernte Section: `action="insert"`, `kind="card"`, `parked=True`, `location=("cards",)`, `payload` die Section als Karte (`{"type": "grid", **section}`; hat die Section kein `type`, wird `grid` ergänzt), `label` der Section-Titel (`_section_title`, wie bei Put back). Genau diese Form kennt `apply_undo` seit Vorhaben L (`for step in (s for s in inserts if s.parked)` → `_park_for(...).append(...)`): Es legt `cards:` an, wenn sie fehlt oder `null` ist, und hängt an. **`apply_undo` ändert sich nicht.**

**Überspringen statt verweigern (Entscheidung vom 2026-09-29).** Der Kartenweg ist idempotent; der Parkweg hält dieselbe Eigenschaft, sonst würde ein zweites Undo derselben Änderung die Section erneut anhängen. Steht in der Ansicht heute schon eine bytegleiche Karte wie die zu parkende (Fingerabdruck gleich, gezählt **in dieser Ansicht**, `_card_came_back` heute mehr als im Stand nach der Änderung), ist dieser Teil der Änderung so oder so rückgängig: Der Plan für die Ansicht bleibt leer, es wird nichts verweigert. Einzeln nachgebaute Karten der Section zählen **nicht** als Rückkehr der Section. Eine gleiche Karte in einer anderen Ansicht zählt nicht (#35).

Die Section stammt vollständig aus dem Stand *vor* der Änderung (`before_view`). Ein Beweis über den heutigen Stand darüber hinaus ist nicht nötig, weil nur hinzugefügt wird; deshalb entfällt die Prüfung »geändert seither«, die den exakten Weg trägt.

Komplexität: `_plan_sections` steht in der Baseline (`tools/complexity-baseline.json`, C901 12). Die Umordnungs-Prüfung wird in eine Hilfsfunktion herausgezogen und der Parkweg in eine zweite. Dadurch **sinkt** die Komplexität von `_plan_sections`, und die Sperrklinke verlangt, die Baseline **im selben Commit** zu senken (oder den Eintrag zu entfernen, fällt der Wert unter das Limit); neue Hilfsfunktionen über dem Limit brauchen einen eigenen Eintrag. Die Baseline wird nach der Messung gesetzt, nicht vorhergesagt; `python3 tools/complexity_ratchet.py` ist Teil der Abnahme.

### 4. »Put back«: `parks()`/`park()` nehmen `kind="section"`

- `restore.parks(config, item)` liefert für `kind="section"` `True`, wenn die Ansicht per Pfad gefunden wird, `type: sections` hat und `_section_gap_holds` nicht hält. Andernfalls antwortet weiter `reinsert`, einschließlich seiner Verweigerungen.
- `restore.park(config, item)` hängt für eine Section **die ganze Section als eine Grid-Karte** an `cards:` der Ansicht an (`{"type": "grid", **payload}`, dieselbe Form wie beim Undo).
- `operations._reinsertion` meldet `parked: [item.label]` (das Etikett der Section, wie `find_removed` es erzeugt) in Vorschau und Antwort; `async_restore_deleted` vergleicht wie bei #30 `expected_parked` vor dem Schreiben. Das Protokoll ist unverändert.
- **Kein Zählen in `restore.py`, aber Doppel-Schutz.** Da die Karten der Section danach in der geparkten Grid-Karte *verschachtelt* stehen, sieht `find_removed` sie nicht mehr als Karten der Ansicht und bietet die Section weiter an. `park()` verweigert deshalb mit einem `LookupError` (»already sits in this view's Imported cards«), wenn eine bytegleiche Karte schon in `cards:` steht; `_reinsertion` gibt das als `error` zurück. Ein Vergleich mit `==` auf den Daten, kein Import von `analyze`.

### 5. Wörter

Die Etiketten bleiben, wie sie heute erzeugt werden:

- **Undo:** `plan.parked` listet das Etikett des geparkten Schritts (`UndoPlan.parked`, `model.py:404`), also den Titel der Section (`_section_title`), wie bei Put back.
- **Put back:** `parked` enthält das eine Etikett der Section (`_section_title`).

Die bestehenden Paneltexte (»These cards cannot go back into their exact section … you still have to place them: …«, Hinweiszeile mit Sternchen) bleiben unverändert; sie nennen bei beiden Wegen den Namen der Section. Das Panel liest keine Bedeutung aus dem Etikett (`operations.py:238`) und braucht kein neues Feld. Der Knopf trägt das Sternchen wie bei #30; `equals_state_before` ist bei einem parkenden Undo von selbst `False`.

## Fehler- und Randfälle

| Fall | Verhalten |
|---|---|
| Section entfernt, danach andere Section in derselben Ansicht hinzugefügt (Fall aus dem Ticket) | die Section als eine Grid-Karte in `cards:` geparkt, Sternchen |
| Section entfernt, danach zwei Sections getauscht | geparkt |
| Section entfernt, sonst nichts geändert | exakt, ohne Sternchen (wie heute) |
| Section entfernt **und** eine andere in derselben Änderung verschoben oder bearbeitet | Verweigerung |
| Section entfernt **und** eine Karte in einer anderen Section derselben Ansicht geändert | Verweigerung durch `_park_instead` (`_card_events_in`, Text »rearranged since«; `_sections_meet_cards` als zweite Sicherung) |
| Dieselbe Section steht heute schon als bytegleiche Karte in der Ansicht (zweites Undo, oder von Hand) | Undo: übersprungen, der Plan für die Ansicht bleibt leer; Put back: Verweigerung mit Text (»already sits …«) |
| Ansicht hat `cards: null` oder keine `cards:` | wird angelegt |
| `cards:` ist etwas anderes als eine Liste | Verweigerung mit dem Text von `_park_for` |
| Zwischen Vorschau und Bestätigen speichert jemand | neu gerechnet; weicht `parked` von `expected_parked` ab, wird nichts geschrieben (wie bei #30) |
| HA stellt die Anzeige »Imported cards« eines Tages ein | nichts geht verloren, die Section steht in der Konfiguration; dafür steht das Sternchen |

## Test-Plan

**pytest** (`tests/test_analyze.py`, `tests/test_restore.py`; `operations.py` ist nicht importierbar):

- Planer: eine entfernte Section + Umordnung (hinzugefügt / vertauscht) → **ein** geparkter Schritt mit der ganzen Section als Grid-Karte (auch mit `column_span`, auch ohne `type`), `plan.parked` hat den Section-Titel; reine Entfernung ohne Umordnung → weiter `sections_list`; Entfernung + Verschiebung/Bearbeitung/Hinzufügung → Verweigerung; Entfernung + Kartenänderung in einer anderen Section derselben Ansicht → Verweigerung (durch `_park_instead`, `_sections_meet_cards` als Sicherung); Ansicht nicht mehr `sections` → Verweigerung; zwei entfernte Sections → Verweigerung (`rest_old`); die Verweigerung für `added` bleibt Wort für Wort.
- Überspringen: dieselbe Section schon als Karte in der Ansicht → leerer Plan; nur einzelne Karten der Section stehen in der Ansicht → trotzdem geparkt; eine gleiche Karte in einer *anderen* Ansicht zählt nicht; wiederholtes Undo derselben Änderung hängt nichts ein zweites Mal an.
- Regression der bewusst verschluckten Karten (`loose_removed`): `find_removed`, `loose_removed`, `summarize`, `_explain` und `change_message` liefern mit einer entfernten Section weiter *eine* Section, nicht mehrere Kartenereignisse.
- `apply_undo` mit einem solchen Plan: legt `cards:` an (fehlt / `null`), hängt in Reihenfolge an, eine gewöhnliche Einsetzung in dieselbe Liste bleibt davor.
- `parks`/`park` mit `kind="section"`: `True`/`False` je Bedingung aus Abschnitt 4, die Section als eine Grid-Karte (Einstellungen bleiben), Eingabe bleibt unverändert (deepcopy), zweites Parken derselben Section wird verweigert.
- Bestehende Tests zu `reinsert` und `_section_gap_holds` bleiben unverändert grün; sie prüfen das Werkzeug, nicht die Politik.
- Ein Fall gegen die **reale** Bank (überspringt sichtbar ohne `DASHBOARD_HISTORY_REAL_STORAGE`), sofern sich dort eine Ansicht mit mehreren Sections findet.

**Panel** (`tests/test_panel_behaviour.py`): Sternchen und Hinweis bei einem Plan mit geparkten Schritten (der Text selbst bleibt).

**Laufende Instanz** (`tests/integration/run_checks.py`, Wegwerf-Instanz): Ansicht mit mehreren Sections, eine entfernen, eine andere hinzufügen, Undo und »Put back« je einmal; nach dem Bestätigen liegt die Section als eine Grid-Karte in `cards:`, ein erneutes Laden über die API liefert sie unverändert; ein zweites Undo derselben Änderung hängt nichts an. Hinweis aus dem Journal: das Skript erodiert seine Prüfbank und braucht ein Ziel-Dashboard mit zwei Karten – vorher prüfen, ob der Abschnitt davor rot ist, bevor er als Ergebnis dieser Änderung gelesen wird.

**Abnahme:** `python3 -m pytest tests/ -v`, `python3 tools/complexity_ratchet.py` (Baseline im selben Commit angepasst), `lint-imports`.

## Entscheidungen (am 2026-09-29 vom Nutzer bestätigt)

1. **Nur »Section entfernt«**, nicht »hinzugekommen« (Kommentar zu #39).
2. **Variante A:** Parken nur, wenn die Ansicht in dieser Änderung ausschließlich die eine entfernte Section hat. Gemischte Änderungen – auch mit Kartenänderungen – bleiben verweigert.
3. **Beide Wege** – Undo und »Put back« – verhalten sich gleich.
4. **Der Parkweg springt nur an die Stelle der Umordnungs-Verweigerung** und erbt alle frühen Prüfungen; hält der exakte Beweis, bleibt der exakte Schritt.
5. **`apply_undo` bleibt unverändert**; die Neuerung liegt im Planer und in `parks`/`park`. Die früher erwogene Vorarbeit aus #43 (`apply_undo` zerlegen) entfällt damit.
6. **Überspringen, nie verweigern (Variante B):** Steht die Section schon als bytegleiche Karte in der Ansicht, wird sie beim Undo nicht erneut geparkt. Die früher erwogene Verweigerung bei einer bytegleichen Section entfällt. Gleiche Eigenschaft wie der Kartenweg (idempotent). Bei Put back verweigert `park()`, weil dort die Section weiter angeboten wird.
7. **Etiketten und Paneltexte bleiben** (Section-Titel bei beiden Wegen); kein Eingriff in `removed.py` und im Panel.
8. **Die ganze Section als eine Grid-Karte parken, nicht Karte für Karte (2026-09-29, nach dem Ausprobieren auf `test-sections`):** Karte für Karte hieß bei einer großen Section, alle Karten einzeln in eine neue Section zu ziehen. Eine Section ist bereits eine gültige Grid-Karte; als eine Karte geparkt, ist es ein Zug oder ein Raw-Edit. Das ersetzt die erste Umsetzung (je Karte ein Schritt, `max(0, deleted − back)`); die Zählung entfällt.
