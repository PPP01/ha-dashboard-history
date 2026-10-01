# Review: Issue #48 – getippte Zeilenumbrüche

Geprüft wurde Commit `7318c17` (»Keep line breaks typed into a
description«) im committeten Stand. Der Arbeitsbaum war sauber. Die
Tests und die Mutationen liefen ausschließlich in einer per `git archive`
angelegten Scratch-Kopie unter `/tmp`, die anschließend entfernt wurde.

## Kritisch

Keine Befunde.

## Wichtig

- `tests/test_panel_behaviour.py:4384,4490,7133,7236` – Die Tests beweisen
  nicht, dass die drei Ausgaben die Klasse `typed` tatsächlich tragen.
  `describedKeepsLineBreaks` wird im Node-Harness zwar ausgerechnet
  (`described.includes('class="why typed"')`), aber nirgends asserted.
  `undescribedShowsNothing` prüft nur den Fall ohne Beschreibung: Ohne
  Absatz bleibt der Ausdruck auch nach Entfernung von `typed` falsch.
  Dasselbe gilt für `wordlessHasNoDescriptionParagraph`: Bei einem
  wortlosen Tag gibt es unabhängig von der Klasse keinen Absatz.

  Empirische Mutation: Jeweils nur `typed` aus `panel/rows.js:172`,
  `panel/simple.js:195` oder `panel.js:2739` entfernt; danach lief
  `python3 -m pytest tests/test_panel_behaviour.py -q -p no:cacheprovider`
  in allen drei Varianten mit `289 passed`. Die neue CSS-Regel selbst ist
  dagegen abgedeckt: Ohne `style.js:688` schlägt
  `tests/test_panel_assets.py` erwartungsgemäß fehl (`1 failed, 7 passed`).
  Es fehlen positive Assertions für alle drei Markup-Pfade, insbesondere
  für den einfachen Modus und den Entfern-Dialog.

## Hinweis

- `custom_components/dashboard_history/panel/rows.js:300-302` und
  `panel/simple.js:66-67` – Die bewusste Nicht-Anwendung auf
  Änderungsbeschreibungen ist richtig, die Formulierung mit »Leerzeilen«
  aber nicht ganz präzise. Das gerenderte Template enthält jeweils einen
  Quelltext-Zeilenumbruch direkt nach dem Text: in `.what` vor dem
  optionalen Auto-Badge, in `.step` vor dem Zeitstempel. Mit `pre-line`
  würde daraus ein sichtbarer, erzwungener Zeilenumbruch; Badge bzw.
  Zeitstempel stünden in einer neuen Zeile. Eine vollständig leere
  zusätzliche Zeile entsteht dabei nicht. Die beiden Stellen sollen daher
  unverändert bleiben.

- `custom_components/dashboard_history/panel/rows.js:172`,
  `panel/simple.js:195`, `panel.js:2739-2740` – Vollständigkeit bestätigt.
  Eine Suche nach `version.description`, `facts.description`,
  `change.description` und allen `escape(...description...)`-Ausgaben in
  den Panel-JavaScript-Dateien ergibt genau diese drei sichtbaren
  Ausgaben von Versionsbeschreibungen. Die übrigen Treffer sind Suche,
  Vergleichslabel, Vorbelegung von Eingabefeldern oder die oben genannten
  Änderungszeilen. Alle drei vorgesehenen Pfade tragen `why typed`.

- `custom_components/dashboard_history/panel/rows.js:172`,
  `panel/simple.js:195`, `panel.js:2739-2740` – Kein sichtbarer
  Template-Whitespace in den neuen `typed`-Elementen. Die ersten beiden
  interpolieren den escapten Text unmittelbar nach `>`.
  Im Dialog folgt auf `</strong>` bewusst ein gewöhnliches Leerzeichen;
  der Quelltext-Zeilenumbruch nach `${` liegt innerhalb der
  JavaScript-Interpolation und gehört nicht zum Ergebnis. Die gerenderte
  Form ist somit `<span class="why typed"><strong>Description:</strong>
  TEXT</span>`, ohne zusätzliche Zeile.

- `custom_components/dashboard_history/panel/style.js:679-688,707,1034,1384,1388`
  – CSS-Prüfung bestanden. `.typed { white-space: pre-line; }` steht nach
  der Basisregel `.why`. Die weiterhin greifenden Selektoren
  `dialog .who .why`, `details.ver > summary .why`, `.vhead + .why` und
  `.vsum .why` verändern ausschließlich Abstände. Eine Vollsuche nach
  `white-space` fand keine spätere oder spezifischere Regel, die auf
  diese `typed`-Elemente trifft und `pre-line` überschreibt.

- `custom_components/dashboard_history/panel/style.js:1-1469` und Commit
  `7318c17` – Die Regeln aus `CLAUDE.md` sind eingehalten: `style.js`
  enthält genau zwei Backticks und kein `${`. Der englische Commit-Betreff
  hat 41 Zeichen; alle Body-Zeilen sind höchstens 68 Zeichen lang
  (Vorgabe: 72), der Betreff ist kapitalisiert und imperativ.

- Laufzeit im Scratch-Stand: `python3 -m pytest tests/ -q -p
  no:cacheprovider` ergab `1080 passed, 5 skipped`; `python3
  tools/complexity_ratchet.py` meldete `20 known values, none grew`.

## Urteil

**Umsetzbar nach Korrekturen:** Die Implementierung deckt die drei
Versionstext-Pfade ab und bewahrt deren Zeilenumbrüche ohne CSS- oder
Template-Whitespace-Nebeneffekt. Vor dem Merge sollten positive Tests für
`typed` an allen drei Ausgabestellen ergänzt werden; die bestehenden
Negativtests erkennen eine Entfernung der Klasse nicht.
