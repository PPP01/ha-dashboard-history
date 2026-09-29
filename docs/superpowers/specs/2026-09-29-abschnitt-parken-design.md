# Ganze entfernte Section parken statt verweigern (GitHub #39)

Stand: 2026-09-29, überarbeitet nach dem Terra- und dem Gemini-Review desselben Tages. Baut auf Entscheidung 26 (Parken, #30, Vorhaben L) und auf »Sections als Einheit« (#31, Vorhaben O, `specs/2026-09-25-sections-als-einheit-design.md`) auf.

## Ausgangslage

In einer `sections`-Ansicht wird eine ganz gelöschte Section als ein Stück erkannt (`_settle_sections`, #31). Sie exakt zurückzunehmen verlangt den atomaren `sections_list`-Beweis in `_plan_sections` (`analyze/undo.py`): Keine der *anderen* Sections der Ansicht darf seither gekommen, gegangen oder verschoben sein (`since, gone, came = _pair_view_sections(...)`, `gone or came or _moved(since)`), und höchstens eine darf seither bearbeitet worden sein. Sonst verweigert die ganze Rücknahme: *»the other sections of the view … were rearranged since, so there is no telling where these go back«*.

Gemessen am 2026-09-26 an `test-2`, Ansicht `a3`: Section entfernt, danach eine andere Section in derselben Ansicht hinzugefügt – die Rücknahme der Entfernung verweigert, obwohl jede Karte der entfernten Section bekannt ist.

Für einzelne Karten löst Entscheidung 26 dasselbe Problem längst: Lässt sich ihre Section nicht mehr beweisen, wird die Karte ans Ende der `cards:`-Liste der Ansicht geparkt (HAs »Imported cards«), und der Knopf trägt ein Sternchen. Für eine ganze Section gibt es diesen Ausweg nicht.

Zwei Wege sind betroffen, und beide verweigern heute:

- **Undo** (`plan_undo` → `_plan_sections` → `apply_undo`): plant einen `UndoStep` mit `kind="sections_list"`.
- **»Put back«** (`operations.async_restore_deleted` → `_reinsertion` → `restore.parks`/`park`/`reinsert`): `parks()` verneint `kind="section"`, `reinsert` verweigert über `_section_gap_holds`.

## Ziel

Ist die Section bekannt, aber ihr Platz in der Reihe seither nicht mehr beweisbar, kommen ihre Karten in »Imported cards« zurück, statt dass die Rücknahme verweigert. Dasselbe Verhalten für beide Wege, dasselbe Sternchen, dieselbe Form der Auskunft `parked` (eine Liste von Texten; was darin steht, unterscheidet sich, siehe Abschnitt 5).

## Nicht-Ziele

- **Die Richtung »Section hinzugekommen« bleibt hart verweigert.** Sie zurückzunehmen hieße Karten *entfernen*; wenn die Reihe sich geändert hat, lässt sich nicht beweisen, welche heutigen Karten genau die der Änderung sind (Entscheidung 4, »verweigert, nie geraten«). Ein Parken gibt es dort nicht. Praktisch abgedeckt: Eine Section, die niemand mehr will, löscht man in der Oberfläche direkt. *(Festgelegt im Kommentar zu #39 nach Diskussion.)*
- **Keine gemischten Änderungen.** Hat dieselbe Änderung in derselben Ansicht *auch* eine Section verschoben, bearbeitet oder hinzugefügt, *oder* eine einzelne Karte geändert, bleibt es bei der Verweigerung. Mehrere Wirkungen in einem Schritt sind über die Oberfläche kaum herstellbar (nur per Raw-Editor oder externem Edit), und wer sie sauber ausführt, erzeugt einzelne Schritte. *(Entschieden am 2026-09-29, Variante A: kein Teil-Undo, »alles oder nichts« bleibt.)*
- **Genau eine entfernte Section je Ansicht.** `_settle_sections` erkennt eine entfernte Section nur dort, wo die Ansicht genau eine Section verloren hat (`old_counts - new_counts == 1`) und genau eine Kandidatin passt. Wurden mehrere entfernt, bleiben alle in `rest_old` und werden von der frühen Rest-Verweigerung abgewiesen. Das bleibt so; das Erweitern des Matchings ist ein eigenes Vorhaben.
- **Kein Zielwechsel.** Ein frei wählbares Dashboard oder eine Ansicht ist #40; dieses Vorhaben liefert dafür das Bauteil (eine Section als Kartenblock parken).
- **Die Einstellungen der Section (`column_span` u. Ä.) werden nicht mitgeführt.** Geparkt werden Karten in eine Liste, in der es keine Section mehr gibt.
- **Kein Umbau von `apply_undo`.** Siehe unten: nicht nötig.
- **Kein Umbau von `analyze/removed.py`, `matching.py` und dem Panel.** Etiketten und Paneltexte bleiben, wie sie sind (Abschnitt 5).

## Entwurf

### 1. Wann der Parkweg greift

Der Parkweg greift im Undo genau dann, wenn alle Bedingungen zutreffen:

1. Die Ansicht hat in dieser Änderung **ausschließlich eine entfernte Section**: `removed` enthält genau eine, `moved`, `reset` und `added` sind leer.
2. Der exakte Weg würde an der Umordnung scheitern: `gone or came or _moved(since)` (Verweigerung 1) oder mehr als eine Section seither bearbeitet (Verweigerung 2). Bei reiner Entfernung sind das die einzigen beiden Verweigerungen *nach* den frühen Prüfungen von `_plan_sections`, denn die Schleife über die Indizes (»changed again after this«) läuft nur über `added`, `moved` und `reset` und ist hier leer.
3. Die frühen Prüfungen von `_plan_sections` sind bestanden und bleiben unverändert: keine Section in `rest_old`/`rest_new` dieser Ansicht (`undo.py:144`), die Ansicht ist noch auf dem Dashboard (Zeile 151), und `sections` ist in `before` und heute eine Liste (Zeile 153). Der Parkweg sitzt **hinter** diesen Prüfungen, an der Stelle der beiden Umordnungs-Verweigerungen (Zeile 167 ff.), und erbt sie damit. Dass die Ansicht heute noch `type: sections` hat, sichert die Prüfung auf `_VIEW_TYPE_REFUSAL` in `plan_undo` davor.
4. Die Änderung hat in dieser Ansicht **keine einzelne Kartenänderung** (bearbeitet, verschoben, entfernt, hinzugefügt). Die geparkten Schritte werden in den Behälter `planned["sections"]` gelegt; damit greift das vorhandene Tor `_sections_meet_cards` (`undo.py:734`) unverändert und verweigert mit `_SECTIONS_AND_CARDS_REFUSAL`, sobald derselbe Plan in derselben Ansicht auch Kartenschritte enthält. Kein neuer Code dafür; die Meldung spricht von »sections moved«, was hier nur ungefähr stimmt und bewusst so bleibt.

Hält der exakte Beweis, ändert sich nichts: derselbe `sections_list`-Schritt wie heute, ohne Sternchen. **Der Parkweg ersetzt nie eine andere Verweigerung** – er springt nur an die Stelle der beiden Umordnungs-Verweigerungen.

### 2. Was weiter verweigert wird, und was nicht

| Fall | Antwort |
|---|---|
| Die Ansicht ist nicht mehr auf dem Dashboard, `sections` keine Liste, oder die Ansicht ist keine `sections`-Ansicht mehr | wie heute (frühe Prüfungen bzw. `_VIEW_TYPE_REFUSAL`) |
| Die entfernte Section war leer | wird gar nicht als entfernte Section erkannt (`_whole(…, empty_counts=False)`), bleibt in `rest_old` und wird von der frühen Rest-Verweigerung abgewiesen; kein eigener Fall, kein eigener Test |
| Die Änderung hat in derselben Ansicht auch verschobene, bearbeitete oder hinzugekommene Sections oder Kartenänderungen | Verweigerung, wie heute |
| Karten der Section stehen heute schon in der Ansicht (von Hand neu angelegt, oder ein früheres Undo derselben Änderung) | **keine Verweigerung, sondern Überspringen** (Abschnitt 3) |

### 3. Undo: ein geparkter Schritt je fehlender Karte, `apply_undo` bleibt

Der Planer erzeugt **keinen** `sections_list`-Schritt für diese Ansicht, sondern je Karte der entfernten Section, die heute nicht schon dort steht, einen Schritt: `action="insert"`, `kind="card"`, `parked=True`, `location=("cards",)`, `payload` die Karte, `label` die Beschreibung der Karte (`_describe(card)`, wie `_put_back` es bei einzelnen Karten tut). Reihenfolge: Section-Index der alten Reihe, dann Kartenindex. Genau diese Form kennt `apply_undo` seit Vorhaben L (`for step in (s for s in inserts if s.parked)` → `_park_for(...).append(...)`): Es legt `cards:` an, wenn sie fehlt oder `null` ist, und hängt an. **`apply_undo` ändert sich nicht.**

**Überspringen statt verweigern (Entscheidung vom 2026-09-29).** Der Kartenweg ist idempotent: Eine Karte, die schon zurück ist, wird ausgelassen (`_card_came_back`, `undo.py:519-537`, *»this part of the change is undone either way«*). Der Parkweg hält dieselbe Eigenschaft, sonst würde ein zweites Undo derselben Änderung dieselben Karten erneut anhängen. Je Fingerabdruck der Karte, gezählt **in dieser Ansicht**:

- `deleted` – wie viele gleiche Karten die entfernte Section enthielt,
- `back` – wie viele gleiche Karten heute mehr in der Ansicht stehen als im Stand nach der Änderung (`_card_came_back`, dieselbe Zählung, dieselbe Ansicht – eine gleiche Karte in einer anderen Ansicht zählt nicht, #35),
- geparkt werden `max(0, deleted - back)` Kopien; sind alle zurück, wird nichts geparkt.

Es gibt hier **keine** Verweigerung, auch nicht bei teilweiser Rückkehr: Die Kopien sind gleich, welche davon fehlt, ist unerheblich, und die Karten zusätzlich vorhanden zu haben ist das kleinere Übel. Das ist bewusst milder als der Kartenweg, der bei teilweiser Rückkehr verweigert (`undo.py:538`), weil hier ohnehin nur hinzugefügt und nie etwas geändert wird. Sind alle Karten schon zurück, ist der Plan für diese Ansicht leer – wie beim Kartenweg, wenn die eine Karte schon zurück ist.

Die Karten stammen sonst vollständig aus dem Stand *vor* der Änderung (`before_view`). Ein Beweis über den heutigen Stand darüber hinaus ist nicht nötig, weil nur hinzugefügt wird; deshalb entfällt die Prüfung »geändert seither«, die den exakten Weg trägt.

Komplexität: `_plan_sections` steht in der Baseline (`tools/complexity-baseline.json`, C901 12). Die Umordnungs-Prüfung wird in eine Hilfsfunktion herausgezogen und der Parkweg in eine zweite. Dadurch **sinkt** die Komplexität von `_plan_sections`, und die Sperrklinke verlangt, die Baseline **im selben Commit** zu senken (oder den Eintrag zu entfernen, fällt der Wert unter das Limit); neue Hilfsfunktionen über dem Limit brauchen einen eigenen Eintrag. Die Baseline wird nach der Messung gesetzt, nicht vorhergesagt; `python3 tools/complexity_ratchet.py` ist Teil der Abnahme.

### 4. »Put back«: `parks()`/`park()` nehmen `kind="section"`

- `restore.parks(config, item)` liefert für `kind="section"` `True`, wenn die Ansicht per Pfad gefunden wird, `type: sections` hat und `_section_gap_holds` nicht hält. Andernfalls antwortet weiter `reinsert`, einschließlich seiner Verweigerungen.
- `restore.park(config, item)` hängt für eine Section alle Karten aus `item.payload["cards"]` **als ein Block** an `cards:` der Ansicht an (Reihenfolge erhalten), statt Karte für Karte über den Aufrufer.
- `operations._reinsertion` meldet `parked: [item.label]` (das Etikett der Section, wie `find_removed` es erzeugt) in Vorschau und Antwort; `async_restore_deleted` vergleicht wie bei #30 `expected_parked` vor dem Schreiben. Das Protokoll ist unverändert.
- **Kein Zählen bereits vorhandener Karten in `restore.py`.** Dort gilt: `find_removed` bietet die Section nur an, wenn ihre Karten heute *fehlen* (`_whole` zählt die vom Kartenabgleich aufgegebenen Karten); stehen sie schon, wird sie nicht als entfernt angeboten. Der Plan prüft das mit einem Test (Abschnitt Test-Plan); erweist sich die Annahme als falsch, wird sie hier nachgezogen, nicht durch einen Import von `analyze` in `restore.py` (dessen Kern-Regel bleibt).

### 5. Wörter

Die Etiketten bleiben, wie sie heute erzeugt werden:

- **Undo:** `plan.parked` listet die Etiketten der geparkten Schritte (`UndoPlan.parked`, `model.py:404`), also die Beschreibung **jeder einzelnen Karte**, wie beim Parken einzelner Karten. Es gibt beim Undo kein Section-Etikett.
- **Put back:** `parked` enthält das eine Etikett der Section (`_section_title`).

Die bestehenden Paneltexte (»These cards cannot go back into their exact section … you still have to place them: …«, Hinweiszeile mit Sternchen) bleiben unverändert und stimmen für beide Wege: Beim Undo stehen die Karten, bei Put back der Name der Section, deren Karten zu platzieren sind. Das Panel liest keine Bedeutung aus dem Etikett (`operations.py:238`) und braucht kein neues Feld. Der Knopf trägt das Sternchen wie bei #30; `equals_state_before` ist bei einem parkenden Undo von selbst `False`.

## Fehler- und Randfälle

| Fall | Verhalten |
|---|---|
| Section entfernt, danach andere Section in derselben Ansicht hinzugefügt (Fall aus dem Ticket) | Karten der entfernten in `cards:` geparkt, Sternchen |
| Section entfernt, danach zwei Sections getauscht | geparkt |
| Section entfernt, sonst nichts geändert | exakt, ohne Sternchen (wie heute) |
| Section entfernt **und** eine andere in derselben Änderung verschoben oder bearbeitet | Verweigerung |
| Section entfernt **und** eine Karte in einer anderen Section derselben Ansicht geändert | Verweigerung durch `_sections_meet_cards` |
| Karten der entfernten Section stehen heute schon (von Hand neu angelegt, oder zweites Undo) | diese Karten werden übersprungen; sind alle da, bleibt der Plan für die Ansicht leer |
| Ansicht hat `cards: null` oder keine `cards:` | wird angelegt |
| `cards:` ist etwas anderes als eine Liste | Verweigerung mit dem Text von `_park_for` |
| Zwischen Vorschau und Bestätigen speichert jemand | neu gerechnet; weicht `parked` von `expected_parked` ab, wird nichts geschrieben (wie bei #30) |
| HA stellt die Anzeige »Imported cards« eines Tages ein | nichts geht verloren, die Karten stehen in der Konfiguration; dafür steht das Sternchen |

## Test-Plan

**pytest** (`tests/test_analyze.py`, `tests/test_restore.py`; `operations.py` ist nicht importierbar):

- Planer: eine entfernte Section + Umordnung (hinzugefügt / vertauscht) → geparkte Schritte in alter Reihenfolge, Etiketten sind Kartenbeschreibungen, `plan.parked` hat je Karte einen Eintrag; reine Entfernung ohne Umordnung → weiter `sections_list`; Entfernung + Verschiebung/Bearbeitung/Hinzufügung → Verweigerung; Entfernung + Kartenänderung in einer anderen Section derselben Ansicht → `_SECTIONS_AND_CARDS_REFUSAL`; Ansicht nicht mehr `sections` → Verweigerung; zwei entfernte Sections → Verweigerung (`rest_old`); die Verweigerung für `added` bleibt Wort für Wort.
- Überspringen: alle Karten schon in der Ansicht → leerer Plan; ein Teil vorhanden → nur die fehlenden geparkt; gleiche Karten mehrfach in der Section (`deleted` = 2) und eine heute vorhanden → eine geparkt; eine gleiche Karte in einer *anderen* Ansicht zählt nicht; wiederholtes Undo derselben Änderung hängt nichts ein zweites Mal an.
- Regression der bewusst verschluckten Karten (`loose_removed`): `find_removed`, `loose_removed`, `summarize`, `_explain` und `change_message` liefern mit einer entfernten Section weiter *eine* Section, nicht mehrere Kartenereignisse; nur der neue Undo-Plan erzeugt Karten einzeln.
- `apply_undo` mit einem solchen Plan: legt `cards:` an (fehlt / `null`), hängt in Reihenfolge an, eine gewöhnliche Einsetzung in dieselbe Liste bleibt davor.
- `parks`/`park` mit `kind="section"`: `True`/`False` je Bedingung aus Abschnitt 4, Block-Anhängen, Eingabe bleibt unverändert (deepcopy); Section, deren Karten heute schon stehen, wird von `find_removed` nicht angeboten (überprüft die Annahme in Abschnitt 4).
- Bestehende Tests zu `reinsert` und `_section_gap_holds` bleiben unverändert grün; sie prüfen das Werkzeug, nicht die Politik.
- Ein Fall gegen die **reale** Bank (überspringt sichtbar ohne `DASHBOARD_HISTORY_REAL_STORAGE`), sofern sich dort eine Ansicht mit mehreren Sections findet.

**Panel** (`tests/test_panel_behaviour.py`): Sternchen und Hinweis bei einem Plan mit geparkten Schritten, deren Etiketten Karten sind (der Text selbst bleibt).

**Laufende Instanz** (`tests/integration/run_checks.py`, Wegwerf-Instanz): Ansicht mit mehreren Sections, eine entfernen, eine andere hinzufügen, Undo und »Put back« je einmal; nach dem Bestätigen liegen die Karten in `cards:`, ein erneutes Laden über die API liefert sie unverändert; ein zweites Undo derselben Änderung hängt nichts an. Hinweis aus dem Journal: das Skript erodiert seine Prüfbank und braucht ein Ziel-Dashboard mit zwei Karten – vorher prüfen, ob der Abschnitt davor rot ist, bevor er als Ergebnis dieser Änderung gelesen wird.

**Abnahme:** `python3 -m pytest tests/ -v`, `python3 tools/complexity_ratchet.py` (Baseline im selben Commit angepasst), `lint-imports`.

## Entscheidungen (am 2026-09-29 vom Nutzer bestätigt)

1. **Nur »Section entfernt«**, nicht »hinzugekommen« (Kommentar zu #39).
2. **Variante A:** Parken nur, wenn die Ansicht in dieser Änderung ausschließlich die eine entfernte Section hat. Gemischte Änderungen – auch mit Kartenänderungen – bleiben verweigert.
3. **Beide Wege** – Undo und »Put back« – verhalten sich gleich.
4. **Der Parkweg springt nur an die Stelle der Umordnungs-Verweigerung** und erbt alle frühen Prüfungen; hält der exakte Beweis, bleibt der exakte Schritt.
5. **`apply_undo` bleibt unverändert**; die Neuerung liegt im Planer und in `parks`/`park`. Die früher erwogene Vorarbeit aus #43 (`apply_undo` zerlegen) entfällt damit.
6. **Überspringen, nie verweigern (Variante B):** Karten, die schon in der Ansicht stehen, werden nicht erneut geparkt – weder bei vollständiger noch bei teilweiser Rückkehr. Die früher erwogene Verweigerung bei einer bytegleichen Section entfällt; wer Karten von Hand neu angelegt hat, bekommt sie nicht doppelt. Gleiche Eigenschaft wie der Kartenweg (idempotent), ohne dessen Verweigerung bei Teil-Rückkehr.
7. **Etiketten und Paneltexte bleiben** (Karten beim Undo, Section-Titel bei Put back); kein Eingriff in `removed.py` und im Panel.
