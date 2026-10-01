# Review: Issue #48 – getippte Zeilenumbrüche (Zweitsicht)

Geprüft wurde Commit `7318c17` (»Keep line breaks typed into a description«) im committeten Stand. Der Arbeitsbaum war vor und nach der Prüfung sauber. Alle Laufzeit- und Mutationsprüfungen wurden isoliert in einem temporären Git-Worktree durchgeführt und anschließend vollständig bereinigt.

## Kritisch

Keine Befunde.

## Wichtig

- `tests/test_panel_behaviour.py:4384,4483-4491` – **Vergessene Python-Assertion für `describedKeepsLineBreaks`:**
  In `_ROWS` wurde zwar im JavaScript-Harness `describedKeepsLineBreaks: described.includes('class="why typed"')` korrekt vorbereitet und übergeben, in der zugehörigen Python-Testfunktion `test_a_versions_own_badge_and_note_show_in_the_advanced_head_too` fehlt jedoch die Assertion `assert row_parts["describedKeepsLineBreaks"] is True`.
  *Empirischer Nachweis:* Wird `typed` aus `custom_components/dashboard_history/panel/rows.js:172` entfernt, laufen weiterhin alle 289 Tests in `test_panel_behaviour.py` fehlerfrei durch (`289 passed`). Erst nach Ergänzung der Assertion wird der Test bei Fehlen von `typed` wie gewünscht rot (`AssertionError: assert False is True`).

- `custom_components/dashboard_history/panel/simple.js:195` und `panel.js:2739` – **Keine Testabdeckung für `typed` in einfacher Ansicht und Lösch-Dialog:**
  Für die einfache Ansicht (`simple.js`) existiert in der Testsuite kein Fixture-Fall, der einer Version eine Beschreibung zuweist. Im Lösch-Dialog (`panel.js:2739`) prüft `_REMOVE_VERSION` zwar auf den Text (`first.body.includes("a note")`) und das Label (`first.body.includes("<strong>Description:</strong>")`), jedoch nicht auf die Klasse `why typed` bzw. `typed`.
  *Empirischer Nachweis:* Wird `typed` selektiv aus `panel/simple.js:195` oder `panel.js:2739` entfernt, meldet die Testsuite (1080 Tests) in beiden Fällen `1080 passed, 0 failed`. Eine Regression an diesen beiden Stellen würde von den automatisierten Tests derzeit unbemerkt bleiben.

## Hinweis

- `custom_components/dashboard_history/panel/rows.js:300-302` und `panel/simple.js:66-67` – **Bestätigung des Arguments zu `.what` und `.step` (Leerzeilen):**
  Die Auslassung der `.what`- und `.step`-Elemente ist fachlich und technisch vollkommen korrekt:
  1. Änderungsbeschreibungen (`change.description`) werden im Dialog über ein `<input type="text" maxlength="200">` (`panel/dialogs.js:115`) als einzeilige Überschrift erfasst; mehrzeilige Eingaben sind dort gar nicht möglich.
  2. *Empirischer Nachweis der Leerzeilen:* In `panel/rows.js:300-302` ist das Template mehrzeilig formatiert:
     ```javascript
     <span class="what">${escape(change.description || change.message)}${chip}${named}
       ${change.description ? `<span class="auto">${escape(change.message)}</span>` : ""}
     </span>
     ```
     Ist `change.description` nicht gesetzt (Regelfall), evaluiert der Ternary zu `""`. Das erzeugte Markup lautet:
     `"<span class=\"what\">Card moved\n            \n          </span>"`
     Unter `white-space: pre-line` werden Zeilenumbrüche (`\n`) nicht kollabiert. Zwei aufeinanderfolgende Umbrüche mit Leerzeichen dazwischen erzeugen eine leere Zeile (Leerzeile) unterhalb des Textes jeder gewöhnlichen Änderungszeile. Bei gesetzter Beschreibung würde `<span class="auto">` auf eine neue Zeile umbrechen.
     In `panel/simple.js:66-67` würde der Quelltext-Umbruch vor `<span class="when">` den Zeitstempel ebenfalls auf eine neue Zeile zwingen.

- `custom_components/dashboard_history/panel/rows.js:172`, `panel/simple.js:195`, `panel.js:2739` – **Vollständigkeit der Ausgabestellen:**
  Eine systemweite Suche über alle JavaScript-Dateien nach `description`, `version.description`, `facts.description`, `change.description`, `why` und `textarea` bestätigt: Es gibt exakt diese drei Stellen, an denen eine durch Nutzer im `<textarea>` erfasste Versionsbeschreibung im HTML-DOM ausgegeben wird. Alle drei Stellen wurden auf `class="why typed"` umgestellt. Alle sonstigen Referenzen betreffen Eingabefelder, Vorbelegungen, Such-Tokens oder reine Zähler.

- `custom_components/dashboard_history/panel.js:2738-2741` – **Kein störender Whitespace in Template-Strings:**
  Weder in `panel/rows.js:172` noch in `panel/simple.js:195` gibt es Whitespace zwischen Tag und Text.
  In `panel.js:2739` (`<span class="why typed"><strong>Description:</strong> ${escape(facts.description)}</span>`):
  Der sichtbare Quelltext-Zeilenumbruch liegt hinter `${` innerhalb der JavaScript-Interpolation. Er ist syntaktischer Code-Umbruch und landet nicht im gerenderten String. Der String vor `${` endet auf ein einzelnes Leerzeichen nach `</strong>`, der String nach `}` schließt direkt mit `</span>`.
  Empirischer Testausdruck:
  `"<span class=\"why typed\"><strong>Description:</strong> Erste Zeile\nZweite Zeile</span>"`.
  Da Beschreibungen beim Speichern getrimmt werden (`.trim()` in JS, `.strip()` in Python), existieren auch keine führenden/nachlaufenden Zeilenumbrüche im Nutzertext.

- `custom_components/dashboard_history/panel/style.js:688` – **CSS-Spezifität und Selektor-Stabilität:**
  `.typed { white-space: pre-line; }` greift mit Spezifität `(0, 1, 0)`.
  Die bestehenden Layout-Selektoren `details.ver > summary .why`, `.vsum .why`, `dialog .who .why` und `.vhead + .why` matchen weiterhin fehlerfrei auf `<p class="why typed">` bzw. `<span class="why typed">`, da eine zusätzliche Klasse das Matching von `.why` nicht beeinträchtigt.
  Keiner dieser Selektoren und keine spätere Regel in `style.js` definiert `white-space`. `pre-line` wird daher an keiner Stelle überschrieben.

- `tests/test_panel_behaviour.py:4381,7133` – **Schwäche der Negativ-Tests:**
  `undescribedShowsNothing` prüft `undescribed.includes('class="why typed"')` auf `False`.
  `wordlessHasNoDescriptionParagraph` prüft `!wordless.body.includes('class="why typed"')` auf `True`.
  Da das Element bei fehlender Beschreibung komplett weggelassen wird, sind beide Prüfungen zwar wahr, sie würden jedoch nicht anschlagen, wenn versehentlich ein Absatz mit `class="why"` (ohne `typed`) ausgegeben würde. Ein Matcher auf `class="why` (ohne schließendes Anführungszeichen) wäre robuster. Immerhin sichert `wordlessHasNoDescriptionLabel` das Fehlen von `Description:`.

- **Regeln aus CLAUDE.md & Laufzeit:**
  - `custom_components/dashboard_history/panel/style.js` enthält exakt zwei Backticks (`test_the_style_is_one_unbroken_template_literal` passed) und keine unvollständigen `${`-Interpolationen (`test_no_substitution_hides_in_the_stylesheet` passed).
  - Commit-Format: Betreff »Keep line breaks typed into a description« ist englisch, imperativ, 41 Zeichen lang (≤ 50). Body sauber auf max. 68 Zeichen umbrochen (≤ 72).
  - Testsuite: `python3 -m pytest tests/ -q -p no:cacheprovider` liefert `1080 passed, 5 skipped` (0 failed).
  - Komplexitäts-Ratchet: `python3 tools/complexity_ratchet.py` meldet `20 known values, none grew`.
  - Imports: `lint-imports` meldet `Contracts: 2 kept, 0 broken`.

## Urteil

**Umsetzbar nach Korrekturen:**
Die CSS- und Markup-Änderung in Commit `7318c17` löst das Problem getippter Zeilenumbrüche sauber und ohne Nebeneffekte. Die Ausgabestellen sind vollständig und die Abgrenzung zu Änderungsbeschreibungen ist technisch begründet.
Vor dem finalen Abschluss sollte jedoch die Testabdeckung nachgebessert werden:
1. In `tests/test_panel_behaviour.py` bei `test_a_versions_own_badge_and_note_show_in_the_advanced_head_too` die bereits im JS vorbereitete Prüfung `assert row_parts["describedKeepsLineBreaks"] is True` nachtragen.
2. Positive Prüfungen auf `typed` für den einfachen Modus (`panel/simple.js`) und den Entfern-Dialog (`panel.js:2739`) ergänzen, damit Mutationen an diesen Stellen nicht unbemerkt bleiben.
