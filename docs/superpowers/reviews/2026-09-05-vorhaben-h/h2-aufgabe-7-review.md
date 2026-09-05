# Review Aufgabe 7 — Zeilen adressieren sich über ihre Revision

Commit unter Prüfung: `c8fa472` (Vorgänger `8629c26`), Branch `vorhaben-h`.
Rein lesend geprüft, keine Änderungen vorgenommen.

## Vorgehen

- Brief (`task-7-brief.md`), Bericht (`task-7-report.md`) und
  Review-Diff gelesen.
- `panel.js` **nicht** über den Unified Diff verglichen, sondern
  `git show 8629c26:.../panel.js` gegen den aktuellen Stand direkt
  Funktion für Funktion gegengelesen (wie angewiesen), ebenso
  `panel/rows.js`.
- `python3 -m pytest tests/ -q` lokal ausgeführt.
- Test-Diff (`tests/test_panel_behaviour.py`) separat gegen
  `git diff 8629c26 c8fa472` geprüft.
- Codebasis nach verbliebenen `_before`-Aufrufen, `data-index` und
  `index + 1`-Mustern durchsucht (`grep -rn`), inklusive `simple.js` und
  `dialogs.js`.

## Ergebnis pytest

```
312 passed, 3 skipped in 15.71s
```

Stimmt exakt mit der im Brief (Schritt 4) und im Bericht genannten Zahl
überein.

## Funktion-für-Funktion-Vergleich (`panel.js`)

Jede geänderte Stelle wurde mit dem im Brief wörtlich vorgegebenen
Code-Block abgeglichen:

- `_refresh`: `findIndex`/`openAt < 0` → `_changeAt`/`!open`,
  `_detailFor(openAt)` → `_detailFor(open)`. Mechanisch identisch.
- `_before` ersatzlos entfernt; `_changeAt`, `_madeSince`, `_isNewest`
  wortgleich aus dem Brief übernommen (inklusive der defensiven
  `Boolean(change) &&` in `_isNewest`, die der Brief selbst so vorgibt).
- `_expand(revision)`, `_detailFor(change)`, `_describe(revision)`,
  `_createVersion(revision)`, `_restoreItem(change, item)`,
  `_undoChange(revision)`, `_alreadyNamed(change)`,
  `_matchingElsewhere(change)`, `_renderMakeVersion(change)`,
  `_renderSetBack(change)`, `_renderDetail(change)`, `_renderRow(change,
  spokenFor)`: jede Signatur, jeder Rumpf entspricht wortwörtlich dem
  Brief. Keine abweichende Bedingung, kein fehlender Guard, keine
  andere Reihenfolge gefunden.
- `_renderMain`/`_renderTopSection`: Auflösung `this._changes[index]`
  vor `this._renderRow(...)` exakt wie im Brief; `_renderVersionHead`
  unverändert (`top === 0`, `this._changes[top]?.same_as_now`) — wie
  gefordert, weil `sections()` weiterhin über globale Indizes arbeitet.
- Verdrahtung in `_render()`: `.change` liest `dataset.revision`,
  `[data-restore]` löst über `_changeAt(this._open)` auf und schützt
  jetzt mit `if (change && item)` (im alten Code gab es diesen Schutz
  nicht — `_restoreItem` wurde auch mit `index === -1` aufgerufen, was
  in der alten `_before(-1)`-Rechnung `this._changes[0]?.revision`
  ergeben hätte; unwahrscheinlich erreichbar, da der Button nur bei
  offener, existierender Zeile gerendert wird). `[data-undo]`,
  `[data-describe]`, `[data-version]` reichen die Revision direkt durch,
  keine `Number(...)`-Konvertierung mehr. Alles deckt sich mit dem
  Brief-Text.
- Semantische Äquivalenz geprüft: `index === 0` (alt, globaler Index in
  `this._changes`) ⇔ `_isNewest(change)` (neu, Vergleich gegen
  `this._changes[0]?.revision`) an jeder Stelle, an der es verwendet
  wurde (`_renderDetail`s "here"-Satz, `_renderRow`s `matching`).
  `index` (alt, für den "kept"-Halbsatz) ⇔ `_madeSince(change)` (neu):
  beide liefern `this._changes.findIndex(...)`, `0` bleibt falsy in
  beiden Fällen, `null` (neu, außerhalb des Fensters) ist zusätzlich
  falsy und lässt den Halbsatz entfallen — genau die im Brief
  beschriebene Erweiterung.

Keine Stelle gefunden, an der eine Bedingung, ein Default oder eine
Reihenfolge stillschweigend geändert wurde.

## `panel/rows.js`

Einzige Änderung: `index`-Parameter → `newest`-Boolean,
`data-index="${index}"` → `data-revision="${escape(change.revision)}"`,
Stift-Attribut ebenso. `sections()` und `versionHead()` unangetastet,
wie vom Brief verlangt (Abschnittslogik bleibt über globale Indizes).
Der komplette Erklärkommentar über `renderRow` (State-vs-Change,
`spokenFor`, `matching`) ist wortgleich erhalten.

## Kommentare (Punkt 5)

Direkter Vorher/Nachher-Vergleich der vollständigen Datei: kein
vorhandener Erklärkommentar wurde entfernt. Zusätzliche Kommentare
kamen hinzu (bei `_changeAt`, `_madeSince`, `_renderSetBack`,
`_renderDetail`s "kept"-Zeile) — alle wortgleich aus dem Brief
übernommen, keine Erfindung des Umsetzers.

## Punkt 2 — `_before` wirklich verschwunden

`grep -rn "_before\b|data-index|index + 1|index+1" custom_components/`
findet nur noch den erklärenden Kommentar in `_renderSetBack`, der die
alte Rechnung zur Begründung zitiert, sowie unabhängige Treffer
(`equals_state_before` in Python, kein Bezug). Kein Aufrufer verwendet
noch einen Index als Vorgänger-Adresse.

## Punkt 3 — fehlende Zeile im Fenster

`_expand`, `_describe`, `_createVersion` brechen jetzt mit `if
(!change) return;` sauber ab, statt auf `undefined.revision`
zuzugreifen. Die `[data-restore]`-Verdrahtung schützt zusätzlich mit
`if (change && item)`. Alle drei Guards sind wörtlich im Brief
vorgegeben.

## Punkt 4 — offene Zeile über einen Refresh

`_refresh` sucht jetzt über `_changeAt(this._open)` statt
`findIndex`; Verhalten mechanisch identisch übernommen. Anzumerken:
Dieser Zweig (offene Zeile überlebt/überlebt nicht den Refresh) war
schon vor dieser Aufgabe nicht durch einen eigenen Testfall abgedeckt
(`test_a_refresh_asks_for_both_and_starts_at_the_top` setzt `_open`
nie) — das ist keine Regression dieser Aufgabe, sondern eine
vorbestehende Lücke, die der Brief hier nicht zu schließen verlangt.

## Punkt 6 — Testfälle

Beide neuen Fälle wurden wie vom Bericht dargestellt geprüft:
- Ohne die Behebung (`change.previous` statt der positionalen
  `_before`-Rechnung) hätte die zweielementige Liste `["a","b"]` bei
  `_expand("b")` keinen `deleted_since`-Aufruf ausgelöst — der erste
  Test bricht dann exakt an den geprüften Assertions.
- Der zweite Fall sichert die Bedingung „kein Vorgänger → kein
  `deleted_since`" ab; er bricht, sobald diese Bedingung fällt (z. B.
  ein unbedingter `deleted_since`-Aufruf).
Beide sind reale, keine vakuum-wahren Fälle.

## Verdikt A — Spec-Konformität

Erfüllt. Jede im Brief benannte Signatur, jeder benannte Name
(`_changeAt`, `_madeSince`, `_isNewest`, `data-revision`, `newest`) ist
exakt wie spezifiziert umgesetzt; `_before` ist entfernt; die drei
betroffenen Dateien stimmen mit dem Diff überein; Commit-Message
erfüllt Format (47 Zeichen Subject, Body ≤ 72 Zeichen, korrekter
Co-Authored-By-Trailer).

## Verdikt B — Reinheit des Refactorings

Erfüllt. Jede der 168 geänderten Zeilen in `panel.js` plus die
Änderungen in `panel/rows.js` bilden dieselbe Verhaltenslogik unter
neuer Adressierung ab; die einzige tatsächliche Verhaltensänderung ist
die im Brief benannte Behebung (unterste Zeile einer Seite fragt jetzt
gegen ihren echten, ggf. ungeladenen Vorgänger statt `null`
zurückzugeben), und diese ist durch den neuen Testfall belegt.

## Befunde

Keine Critical- oder Important-Befunde.

- **Minor** — `panel.js`, Zeile 1416/1420 (`[data-restore]`-Handler):
  Der neue `if (change && item)`-Schutz ändert das beobachtbare
  Verhalten in einem Randfall, den die alte Implementierung nicht
  abfing (`_restoreItem` wurde zuvor auch mit `index === -1`
  aufgerufen). Praktisch unerreichbar, weil der Button nur bei
  offener, existierender Zeile im Markup steht, und der Guard ist
  wörtlich im Brief vorgegeben — kein Fehler des Umsetzers, aber damit
  ist diese eine Stelle im strengen Sinn keine reine
  Bedeutungsverschiebung, sondern eine (im Brief selbst angelegte)
  zusätzliche Absicherung. Erwähnenswert, nicht handlungsbedürftig.
- **Minor** — Der Refresh-Zweig, der die offene Zeile über einen
  `_changeAt`-Lookup sucht (`panel.js`, `_refresh`, Zeile 325 ff.), hat
  weiterhin keinen eigenen Testfall (weder vorher noch nachher). Keine
  Regression dieser Aufgabe, aber eine vorbestehende Lücke, die bei der
  in Schritt 4 des Briefs vorgesehenen Sichtprüfung besonders den
  Punkt „unterste Zeile der ersten Seite nach ‚Ältere laden‘" trifft.

## Konflikt mit dem Plan

Keiner. Nichts im Brief wirkt hier wie ein Defekt.
