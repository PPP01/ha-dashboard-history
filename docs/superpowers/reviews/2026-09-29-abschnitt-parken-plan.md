# Review: Plan »Ganze entfernte Section parken« (#39)

Gegenstand: `docs/superpowers/plans/2026-09-29-abschnitt-parken.md` gegen die Spec `specs/2026-09-29-abschnitt-parken-design.md`, Branch `feature/park-removed-section`, Code-Stand `8795e0c`. Rein lesend; alle Simulationen in einer Scratch-Kopie aus `git archive HEAD` (inzwischen gelöscht, kein Docker beteiligt).

**Wichtig vorab:** Geprüft wurde der Plan aus dem **Arbeitsbaum**. Er ist uncommittet und weicht von `8795e0c` um +128/−12 Zeilen ab (u. a. die `how == "cards"`-Korrektur in `mixed`, drei Tests, Schritt 3a). Siehe W5.

## Was ich nachgestellt habe

- Die Codeblöcke des Plans (Aufgabe 1 und 2, ohne Integrationsprobe) wörtlich in die Kopie übertragen: Tests, `_rearranged`, `_park_removed_section`, `_park_instead`, geänderte `_plan_sections`/`_plan_section_steps`, `_section_parks`, `parks`, `park`.
- **Rot-Phase:** Mit den neuen Tests, aber ohne Umsetzung, scheitern genau die zwölf Undo-Tests, die der Plan nennt. In `test_restore.py` scheitern vier (`..._neighbours_changed_parks`, `..._one_block_in_order`, `..._creates_cards_when_null`, `..._appends_after_cards_already_there`), nicht mehr.
- **Grün-Phase:** Mit Umsetzung `325 passed, 3 skipped` (beide Dateien), gesamte Suite `999 passed, 5 skipped`.
- **Mutationen:** Ohne `any(p.how == "cards" …)` scheitert genau `test_a_card_change_is_refused_even_when_the_removed_cards_stand_again` (die Sperre trägt). Ohne die `type == "sections"`-Bedingung scheitert `test_a_section_never_parks_outside_a_sections_view`, ohne die Pfad-Bedingung `test_a_section_of_a_pathless_view_does_not_park`.
- **Sperrklinke:** `_plan_sections` fällt von C901 12 auf **11**. Die Baseline ist auf 11 zu senken, der Eintrag entfällt **nicht** (11 > Limit 10). Die drei neuen Funktionen liegen unter dem Limit. Nach dem Senken grün. `lint-imports`: 2 Verträge erfüllt.
- Aufrufer von `_plan_sections`: nur `_plan_section_steps` und der Testhelfer `_section_plan` (`tests/test_analyze.py:2274`, ohne `ctx`). `tests/test_analyze_interface.py` pinnt nur die Exportnamen; die neuen Helfer sind privat und nicht exportiert. Zeilenangaben des Plans stimmen.
- `operations.py` und Panel brauchen tatsächlich keine Änderung: `_reinsertion` (`operations.py:91–120`) ruft `parks`/`park` und meldet `[item.label]`, `async_restore_deleted` vergleicht `expected_parked` (Zeile 765), der Hinweistext im Panel (`panel.js:1999`) ist für Undo und Put back derselbe. Der WebSocket-Standard für `expected_parked` ist `[]` (`websocket_api.py:139, 188`); ein Put back ohne Angabe wird also wie bei #30 mit `_UNEXPECTED_PARKING` abgewiesen.

## Kritisch

Keine.

## Wichtig

### W1 – Die Undo-Probe erwartet ein falsches Etikett und wäre rot (hoch, empirisch)

Fundstelle: Aufgabe 3, Schritt 2, `run_section_parking`, Zeilen mit `"markdown: # A"` (Prüfung `asked.get("parked") == …` und `expected_parked=[…]`).

`_describe({"type": "markdown", "content": "# A"})` liefert `'markdown: A'` (die Markdown-Überschriftsmarke fällt weg; `run_parking` in derselben Datei erwartet entsprechend `"markdown: Licht"`). Folge: Die erste Prüfung ist rot; der bestätigende Aufruf mit `expected_parked=["markdown: # A"]` liefert `available: False` (`_UNEXPECTED_PARKING`, **keine** Ausnahme, die Probe prüft `applied` nicht), also wird nichts geschrieben und die zweite Prüfung ist ebenfalls rot. Schritt 3 verbietet ausdrücklich, die Probe anzupassen, und schickt den Umsetzer auf die Suche nach einem Code-Fehler, den es nicht gibt.
Vorschlag: Karteninhalt ohne `# ` (`"A"`) verwenden und das Etikett aus `asked["parked"]` lesen statt es zu raten; beim Bestätigen zusätzlich `applied is True` prüfen.

### W2 – Die Put-back-Probe erreicht den neuen Code nicht (hoch, empirisch)

Fundstelle: Aufgabe 3, `run_section_parking`, Abschnitt »put back« (`[a],[b]` → `[b]` → `[b],[c]`).

`find_removed(base, current)` vergleicht die Aufzeichnung mit dem **heutigen** Stand. Dort hat die Ansicht wieder zwei Sections; `_settle_sections` erkennt eine entfernte Section nur bei genau einer weniger (`old − new == 1`). Gemessen auf `HEAD` (ohne den Plan): Item ist `kind="card"`, Etikett `'markdown: a'`, und `restore.parks(...)` ist **schon heute** `True` (Vorhaben L, #30). Die Prüfung »a removed section is put back as parked cards« besteht also ohne das Vorhaben. Erreichbar ist der neue Pfad nur bei Nettoverlust von einer Section **und** anderweitig verändertem Umfeld, z. B. `[a],[b],[c]` → `[b],[c]` → `[c],[b]`: dort `kind="section"`, Etikett `'section 1'`, `parks` auf `HEAD` `False`, mit dem Plan `True`; nach dem Parken bietet `find_removed` nichts mehr an (Annahme der Spec, Abschnitt 4, hält).
Konsequenz für die Spec: Der Satz »beide Wege verweigern heute« stimmt für Put back im Ticketfall (hinzugekommene Section) nicht; dort parkt Put back die Karten bereits einzeln. Der Gewinn von Aufgabe 2 ist der schmalere Fall »Nettoverlust plus Umordnung/Bearbeitung der Nachbarn«. Das gehört in Spec und Journal ehrlich benannt.
Vorschlag: Probe auf `[a],[b],[c]` → `[b],[c]` → `[c],[b]` umstellen und prüfen, dass `deleted_since` `kind == "section"` meldet. Zusätzlich in `tests/test_restore.py` einen Test, der das Item über `find_removed(alt, heute)` gewinnt (Aufgabe 2 baut das Item bisher aus `old`/`new` und prüft gegen einen dritten Stand; das ist die Konvention der Datei, beweist hier aber die Erreichbarkeit nicht).

### W3 – Die Probe wartet auf die Aufzeichnung mit dem Helfer, den die Datei selbst als falsch dokumentiert (mittel, Lesen plus Belegstelle)

Fundstelle: Aufgabe 3, `save()` in `run_section_parking` nutzt `_wait_until_recorded`; drei Speicherungen hintereinander.

Die Docstring von `_wait_for_new_state` (`tests/integration/run_checks.py:985–994`) beschreibt genau den Fehler: `same_as_now` allein ist »für einen Moment nach jedem Speichern wahr«, das nächste Speichern landet im Debounce des Recorders, das Paar hebt sich auf, es entsteht kein Commit. `run_section_moves` – das Muster, das der Plan nennt – nutzt deshalb `_wait_for_new_state` mit der vorherigen Revision. Folge: flackernde oder falsch gelesene Revisionen (`removed[0]["revision"]`).
Weiter: Nach dem bestätigten Undo wartet die Probe nur `sleep(2)`, statt auf den eigenen Eintrag des Undo zu warten (`run_section_moves.undo()` zeigt das Muster), und löscht das Dashboard direkt danach.
Vorschlag: `save` und `undo` aus `run_section_moves` übernehmen.

### W4 – Einzelne Kartenänderungen außerhalb der Sections bleiben ein Teil-Undo (mittel, empirisch)

Fundstelle: `_park_instead`, Argument `mixed = bool(moved or reset or added or any(p.how == "cards" for p in mine))`; Spec §1 Punkt 4, Entscheidung 2 (Variante A).

Die Korrektur deckt nur Überlebende mit `how="cards"` ab. Eine lose Kartenänderung derselben Ansicht in `cards:` nicht. Gemessen: Änderung = Section `a` entfernt **und** Karte `z` in »Imported cards« hinzugefügt.
- `a` heute nicht zurück: Verweigerung durch `_sections_meet_cards` (Text »… moved sections … and also changed single cards«) – wie die Spec will.
- `a` heute schon zurück (leerer Parkplan): `plan.blocked is None`, Schritt `remove card z`; der Undo nimmt nur `z` heraus und meldet Erfolg.
Das ist derselbe Lochtyp, den der Plan für `how="cards"` schon geschlossen hat; die Spec verlangt »keine einzelne Kartenänderung (bearbeitet, verschoben, entfernt, hinzugefügt)« und »alles oder nichts«. Man kann es auch für richtig halten (die Entfernung ist ja »so oder so rückgängig«), dann aber als Entscheidung festhalten und mit einem Test pinnen; unentschieden bleibt die Antwort davon abhängig, ob die Karten schon zurück sind.
Vorschlag: `mixed` um »irgendein Kartenereignis dieser Ansicht in `ctx.matching`« erweitern (`edited`, `moved`, `loose_added`, `loose_removed` mit `slot.view_key == key`) – dann entfällt die Sonderbehandlung von `how="cards"` womöglich ganz –, oder die Entscheidung dokumentieren.

### W5 – Der Plan ist nicht aus dem committeten Stand reproduzierbar (mittel)

Der Arbeitsbaum enthält den überarbeiteten Plan und eine geänderte `CLAUDE.md`; beides ist uncommittet. Aufgabe 3, Schritt 6 legt den Plan erst in den **letzten** Commit. Wer von `8795e0c` startet, liest die alte Fassung ohne die `how == "cards"`-Korrektur – genau das Loch, das die Überarbeitung schließt. Projektregel (`CLAUDE.md`, Abschnitt »Planning«).
Vorschlag: Die Planüberarbeitung vor der Übergabe als eigenen Doku-Commit ablegen; in Schritt 6 dann nur noch `run_checks.py`, `status.md` und Spec.

## Hinweis

- **H1 – Kosmetik/Komplexität:** In `_park_instead` ist der Docstring nach der Überarbeitung nicht mehr auf 72 Zeichen umbrochen (Aufgabe 1, Schritt 3b), die `bool(...)`-Zeile im Aufruf ist sehr lang. Der `mixed`-Ausdruck ließe sich in einen Helfer auslagern; ob `_plan_sections` dann auf ≤ 10 fällt und der Baseline-Eintrag entfällt, habe ich nicht gemessen.
- **H2 – Rot-Phase Aufgabe 2:** Der Plan sagt, die `parks`/`park`-Tests scheiterten; tatsächlich sind `test_parking_a_section_leaves_the_input_alone` und `test_parking_a_section_into_a_cards_that_is_no_list_refuses` schon vor der Umsetzung grün (nur der Text anpassen). Der Zweig `raise LookupError("… holds no cards to park")` samt `isinstance(item.payload, dict)` in `park` ist unerreichbar (`_whole` liefert nur nicht leere Kartenlisten) und ungetestet: testen oder weglassen.
- **H3 – Pfadlose Ansichten:** Der Undo parkt dort (nachgestellt: Schritt mit `view_path=None`, `view_index=0`, Ergebnis stimmt), Put back nicht (`status.md:118` dokumentiert die Asymmetrie). Der Plan hat für den Undo-Fall keinen Test; einen ergänzen. Der neue Aufrufer stützt sich auf `ctx.now_index`, also auf den bekannten Befund W3 zu `Slot.view_index` (`status.md:121`) – dort mitnennen.
- **H4 – Spec-Nachzug unvollständig:** Aufgabe 3, Schritt 4 ergänzt nur §1 Punkt 4. Die Zeile »… Verweigerung durch `_sections_meet_cards`« in der Randfalltabelle und im Testplan stimmt für den `how="cards"`-Fall nicht mehr (verweigert wird in `_park_instead`, mit dem Text »rearranged since« – wie heute, keine Verschlechterung).
- **H5 – Reihenfolge von Ausnahmen:** `_park_removed_section` liest `ctx.card_now`/`card_then` früher als `_COMPUTED_BEFORE["cards"]` es vorsieht. Nur bei entarteten Eingaben (eine später sortierte Ansicht, deren Karten-Gruppierung wirft, während vorher eine Verweigerung erreicht worden wäre) ändert sich, wo geworfen wird. Kein Test in der Suite pinnt das; der Plan begründet es im Docstring.
- **H6 – Testlücken ohne Schaden:** Kein Test für zwei Ansichten mit je einer entfernten Section in einer Änderung, für `expected_parked`-Abweichung (liegt in `operations.py`, nicht importierbar; Integrationsprobe prüft nur den Gutfall) und für »gewöhnliche Einsetzung bleibt vor der geparkten« (Spec-Testplan; über den Planer nicht erreichbar, `apply_undo` unverändert, durch die #30-Tests gedeckt). Die bewusst weggelassene reale Bank ist im Plan begründet.
- **H7 – Formulierung im Panel:** »These cards … you still have to place them: section 1« nennt bei Put back die Section, nicht die Karten; von Spec §5 so entschieden.
- Nachgestellt und in Ordnung: zweites Undo hängt nichts an, gleiche Karte mehrfach (`deleted` = 2) und gleiche Karte in anderer Ansicht, `cards: null`/fehlend/Nicht-Liste, zwei Ansichten mit demselben Pfad (Tor `_paths_collide_anywhere` beim Undo, `_paths_share` bei Put back), Einstellungsänderung derselben Ansicht in derselben Änderung (parkt und setzt, Spec lässt das zu), Reihenfolge in `apply_undo` (Geparktes zuletzt, in alter Reihenfolge).

## Urteil

**Umsetzbar nach Korrekturen.** Aufgabe 1 und 2 sind konsistent und laufen mit den Codeblöcken des Plans so, wie behauptet (rot/grün, Sperrklinke, Import-Verträge, Aufrufer geprüft); die Tests sind nicht hohl, die tragende Sperre ist durch Mutation belegt. Aufgabe 3 hat mit W1–W3 drei Fehler in der Probe, von denen zwei (falsches Etikett, Put-back-Fall ohne Wirkung auf den neuen Code) die Abnahme entweder rot oder wertlos machen. W4 ist eine Entscheidung, die vor der Umsetzung fallen sollte, W5 eine Formalie vor der Übergabe.
