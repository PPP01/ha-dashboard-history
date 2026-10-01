# Review: »Save this as another version« nur im Advanced-Modus

## Kritisch

Keine Befunde.

## Hoch

Keine Befunde.

## Mittel

### Der Plan erklärt einen möglichen benannten Bannerzustand für unmöglich und testet ihn nicht

**Fundstelle:** Implementierungsplan, Aufgabe 2, Schritt 1(a)/(b), Review
Focus und Testszenario `_ADVANCED_SAVE_ANOTHER`; `panel.js`,
`_renderMain`, `_renderNowBanner`, `_nowFacts` und `_nowActs`.

**Beschreibung:** Der Plan beschreibt `_renderNowBanner` als den Fall
»drifted hinter einem Tag« mit leerem `matching`, also als unaufgeräumt.
Das folgt jedoch nicht aus dem Code. Der Banner wird erzeugt, wenn die
neueste Änderung eine Version trägt und `same_as_now` falsch ist.
`matching_versions` wird unabhängig davon aus *allen* Versionen berechnet:
der Live-Stand kann daher einer älteren Version entsprechen, obwohl die
neueste getaggte Änderung ihn nicht hält. Das ist etwa nach einer nicht
aufgezeichneten Rückkehr zu einem älteren Stand möglich. Dann ist der
Banner benannt und der in Aufgabe 2 geänderte `_nowActs(matching)`-Pfad
wird tatsächlich »Save this as another version« zeichnen.

**Konsequenz:** Die Umsetzung behandelt den Fall vermutlich richtig, aber
der Plan behauptet fälschlich, es gebe nur die zwei aufgeräumten Formen,
und seine neuen Tests belegen diesen dritten aufgeräumten Darstellungsfall
nicht. Damit ist die zugesicherte Zustandsabdeckung nicht erreicht; eine
künftige Umgestaltung von `_renderNowBanner` kann die Funktion unbemerkt
verlieren lassen.

**Vorschlag:** In Aufgabe 2 einen Test ergänzen: neueste Änderung mit
`versions`, `same_as_now: false`, aber `_matching` mit einer älteren
Version. Er muss genau einen »another«-Button und keinen Undo-Button im
`now-panel now-head named`-Banner erwarten. Die Aussage in Schritt 1(b)
und die Liste der aufgeräumten Formen entsprechend auf drei Formen
korrigieren.

### Die vorgeschriebene Sichtprüfung ist nicht aus dem committed Zustand reproduzierbar

**Fundstelle:** Implementierungsplan, Aufgabe 3, Schritte 1 und 4;
`CLAUDE.md`, Abschnitt »Planning«.

**Beschreibung:** Beide Schritte verlangen den Test-Container im Browser,
verweisen aber ausdrücklich auf eine außerhalb des Repositories liegende
Konfiguration und einen Token. Der Plan enthält weder eine committed
Fixture noch eine dokumentierte, ohne lokale Geheimnisse funktionierende
Alternative. Zudem bleibt offen, wo der verlangte Bericht »gesehen / nicht
gesehen« abgelegt werden soll.

**Konsequenz:** Ein anderer Ausführender kann die als Pflichtschritte
formulierte Prüfung nicht zuverlässig durchführen. Das widerspricht der
Projektregel, dass Implementierungspläne aus dem committed Zustand allein
reproduzierbar sein müssen, und kann den letzten Commit blockieren.

**Vorschlag:** Die Sichtprüfung als ausdrücklich optionale, lokale
Abnahme nach den automatisierten Tests kennzeichnen und ein klares
Fallback-Ergebnis festlegen (zum Beispiel »nicht ausgeführt: keine lokale
Testinstanz«). Falls sie verpflichtend bleiben soll, braucht der Plan eine
committete, geheimnisfreie Einrichtungs- und Prüfmöglichkeit sowie einen
benannten Ablageort für das Ergebnis.

## Niedrig

### Die Zahl der Commits ist widersprüchlich beschrieben

**Fundstelle:** Implementierungsplan, »Ausgangslage und Basis« sowie die
Commit-Schritte der Aufgaben 1 bis 3.

**Beschreibung:** Der Plan verlangt einen ersten Commit für die Plan-Datei
und danach je einen Commit in den drei Aufgaben. Das sind vier Commits,
nicht der im Review-Auftrag genannte Zuschnitt von drei Commits.

**Konsequenz:** Die Ausführung ist zwar technisch eindeutig, die
Anforderung an den Commit-Zuschnitt aber nicht.

**Vorschlag:** Explizit festhalten, ob »drei Commits« nur die Umsetzung
meint und der Plan-Commit zusätzlich ist, oder den Plan-Commit in einen
der drei vorgesehenen Commits integrieren.

## Geprüfte Behauptungen und Tests

Gelesen wurden `CLAUDE.md`, Status und bindende Spec, der vollständige
Plan, `panel.js`, `panel/rows.js`, `panel/simple.js`, `panel/style.js`,
`operations.py`, die genannten Panel-Tests sowie FAQ und User Guide.

Nachweislich ausgeführt:

- Die Suche nach `data-version="now"` ergab genau drei Vorkommen: zwei in
  `panel/simple.js`, eines in `panel.js`.
- Der gezielte bestehende Panel-Testlauf zu den berührten Right-now- und
  Simple-Fällen bestand: 21 passed.
- `tests/test_panel_assets.py` bestand: 12 passed. Die vorgeschlagene
  CSS-Regel enthält weder Backticks noch `${` und verletzt diese Prüfungen
  daher nicht.
- `python3 tools/complexity_ratchet.py` und `lint-imports` bestanden.

Nur gelesen bzw. aus dem Code hergeleitet:

- `_nowActs`, `_nowFacts`, `_renderVersionHead`, `versionHead`,
  `crowned`, `standingOn`, `merged`, die Imports und der bestehende
  `onClick("[data-version]")` sind an den genannten Ankern vorhanden.
  Die Importreihenfolge ist schlüssig: beide Module laden `rows.js` über
  dieselbe dynamische Modul-URL, und `panel.js` destrukturiert dessen
  Exporte erst nach `Promise.all`.
- Die Datenformen der vorgeschlagenen Szenarien passen zu `sections()` und
  `_renderMain`; die Zählung `">Save this as a version<"` unterscheidet
  zuverlässig den exakten alten Buttontext von »another version«.
  Vor der Änderung würden die zwei settled-Simple-Assertions sowie
  crowned, stacked, reverted und named-match im Advanced-Szenario
  fehlschlagen; unaufgeräumt, keine Version und noch nicht geladene
  Versionen bestehen bereits. Außer `boxSave` und `noSaveButton` wurde
  keine weitere bestehende Assertion gefunden, die zwingend kippt.
- `async_history` und `async_versions` setzen `same_as_now` nur bei
  vorhandener Live-Konfiguration. Ein gelöschtes Dashboard kann daher
  nicht gekrönt sein. Suche lässt im Simple-Modus die globale
  `standingOn`-Entscheidung bestehen; im Advanced-Modus gibt sie keine
  Right-now-Box aus. Beim Moduswechsel bleibt die jeweilige Aktion über
  den anderen Modus erreichbar, abgesehen von der beabsichtigten
  settled-Simple-Ausnahme. Nicht geladene Versionen lassen weiterhin alle
  entsprechenden Buttons weg.
- Der neue Button liegt innerhalb eines `summary`; der zentrale Handler
  verhindert dort bereits das native Auf-/Zuklappen. Die vorgeschlagene
  `.acts`-Regel ist strukturell passend. FAQ und User-Guide-Texte
  beschreiben die normalen settled-, unaufgeräumten- und leeren Fälle
  zutreffend, aber nicht den oben genannten benannten Banner-Randfall.

## Urteil

**Umsetzbar nach Korrekturen.** Die Kernänderung, Datenflüsse,
Importreihenfolge und vorgesehenen Assertion-Anpassungen sind schlüssig.
Vor der Umsetzung sollten der benannte Bannerzustand getestet und die
nicht reproduzierbare Browser-Abnahme im Plan bereinigt werden.

ENDE DES REVIEWS
