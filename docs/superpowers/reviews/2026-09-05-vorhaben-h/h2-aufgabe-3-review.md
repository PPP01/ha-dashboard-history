# Review Aufgabe 3: Das Panel wird nach Zuständigkeiten geteilt

Commit-Bereich: `d9b1cec..bbc31b1` (ein Commit: `bbc31b1`).

## Vorgehen

Für jede laut Brief bewegte Funktion wurde die Fassung in
`d9b1cec:custom_components/dashboard_history/panel.js` gegen ihre neue
Heimat in `bbc31b1` verglichen (`sections`, `someNames`, `versionHead`,
`renderRow`, die vier `<dialog>`-Blöcke, den Lade-Block, die Umbenennung
`sections` → `cut`, alle vier `someNames`-Aufrufstellen). Zusätzlich
wurde geprüft, ob `panel/rows.js` und `panel/dialogs.js` exakt dem im
Brief vorgegebenen wörtlichen Code entsprechen (Diff gegen die
Code-Blöcke aus `task-3-brief.md`), um zu trennen, ob eine Abweichung
vom Implementierer oder bereits vom Brief stammt. `git diff --stat` über
den gesamten Bereich wurde gegen die im Brief genannte Dateiliste
geprüft, `pytest tests/ -q` und `node --check` auf allen drei
JS-Dateien liefen zur Bestätigung.

## Verdikt A — Spec-Konformität

Der Schnitt entspricht dem Brief vollständig: Dateien, Exportnamen,
Signaturen, Ladeblock-Reihenfolge (`style.js`, `render.js`, `rows.js`,
`dialogs.js`), Umbenennung `sections` → `cut`, alle vier
`someNames`-Aufrufstellen, die dünnen Klassen-Umhüllungen `_renderRow`/
`_renderVersionHead`, sowie die Testliste in `test_panel_assets.py` —
alles wortgleich mit dem, was der Brief verlangt.

## Verdikt B — Codequalität / Reinheit des Umzugs

Die Bewegung ist bis auf zwei stillschweigend verlorene
Kommentar-Absätze verhaltensgleich; beide Verluste stammen jedoch bereits
aus dem Brief-Code selbst (byte-genau gegengeprüft), nicht aus einer
eigenmächtigen Kürzung des Implementierers, der beide Stellen exakt wie
im Brief vorgegeben übernommen hat. `pytest tests/ -q` → `286 passed, 3
skipped`, unverändert; `test_panel_behaviour.py` blieb unangetastet; nur
`test_panel_assets.py` unter den Testdateien geändert; Commit-Message
erfüllt alle Formvorgaben (Subject 45 Zeichen, Body-Zeilen ≤ 72,
korrekter Trailer).

## Findings

- **Minor — Konflikt mit dem Plan, nicht dem Implementierer anzulasten:**
  `versionHead` in `custom_components/dashboard_history/panel/rows.js`
  (Zeilen 74–97) hat gegenüber der Original-Methode `_renderVersionHead`
  in `d9b1cec:custom_components/dashboard_history/panel.js` (Zeile 1073)
  einen Kommentar-Absatz verloren: *„'same state as now' and not a
  wording of its own: three places say this one fact, and they said it
  in two vocabularies until somebody read all three together and asked
  whether they meant the same thing. They do.“* Dieser Absatz stand im
  Original direkt vor `const top = section.rows[0];` und erklärt, warum
  der Wortlaut „same state as now“ an drei Stellen wiederverwendet wird —
  exakt die Art Begründung, die der Brief mit „Jeden vorhandenen
  Kommentar mitnehmen“ ausdrücklich für erhaltenswert erklärt. Der
  Verlust steht bereits im Brief-Codeblock selbst (byte-genau gegen
  `task-3-brief.md` geprüft) und wurde vom Implementierer unverändert
  übernommen — anders als beim bereits adjudizierten `someNames`-Fall
  hat der Implementierer hier nicht bemerkt, dass der Brief-Schnipsel
  selbst unvollständig ist, und den Absatz nicht wiederhergestellt.

- **Minor — Konflikt mit dem Plan, nicht dem Implementierer anzulasten:**
  `renderRow` in `custom_components/dashboard_history/panel/rows.js`
  (Zeilen 116–147) hat gegenüber `_renderRow` in
  `d9b1cec:custom_components/dashboard_history/panel.js` (ab Zeile 1184)
  drei Kommentarpassagen verloren, alle drei „Warum“-Begründungen:
  (1) *„The other difference the chips carry: the top entry is where
  you are. A lower entry can hold byte-identical content without being
  where you are - move a card up and down and there is a whole run of
  them, all worded alike.“*; (2) den Halbsatz *„…and it was measurable:
  the head read 'same content as now' while the row under it read 'same
  state as now', one fact wearing two coats.“* an das `spokenFor`-Docstring
  angehängt; (3) vor `const named = …`: *„Beside 'current state' rather
  than in a sentence under the card. Both said the same thing; only one
  of them sits inside the frame the eye stops at, and the sentence below
  was read past. Kept short for the same reason - a chip is a label, not
  a statement - with the part that cannot fit moved into the tooltip,
  where 'a different entry' is spelled out.“* Wie bei `versionHead`
  steht diese Kürzung bereits im Brief-Codeblock (byte-genau geprüft)
  und wurde wortgleich übernommen.

Beide Funde sind reine Dokumentationsverluste ohne Verhaltensänderung —
kein Test kann sie fangen, aber sie widersprechen dem eigenen
Prinzip des Briefs, dass Begründungskommentare beim Umzug mitgenommen
werden müssen. Da der fehlerhafte Text bereits im Brief steht, liegt die
Behebung beim nächsten Plan-Update (Brief korrigieren), nicht bei einer
Nacharbeit an dieser Aufgabe.

Keine weiteren Abweichungen gefunden: alle übrigen Kommentare,
Bedingungen, Defaults und die Reihenfolge der Operationen sind
unverändert übertragen. Keine Datei-Grenzverletzung (jede Funktion liegt
in der laut Brief vorgesehenen Datei), kein zirkulärer Import, keine
Ladereihenfolge-Verletzung (rows.js importiert render.js selbständig,
das ist bereits das bestehende Muster aus render.js/style.js und wird
durch `test_panel_behaviour.py` mitgeprüft).
