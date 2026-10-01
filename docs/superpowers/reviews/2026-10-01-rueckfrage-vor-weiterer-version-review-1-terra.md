# Review: Rückfrage vor einer weiteren Version

## Mittel

### M1 — Der universelle Pfad über die Volltextsuche ist nicht abgesichert

**Fundstelle:** Plan, Task 1 / Tests; `panel.js`, `_changeAt`, `_createVersion`.

`_changeAt` findet eine Revision nicht nur in `_changes`, sondern auch in
`_searchResults`. Damit ist »Version up to here« auch für einen Treffer aus
der Volltextsuche ein echter Aufrufer von `_createVersion`. Die neue Abfrage
funktioniert dort grundsätzlich, weil sie den gefundenen `change` verwendet.
Der Plan testet aber nur geladene Zeilen. Insbesondere fehlt ein Treffer, der
selbst eine Version trägt oder als `same_as_now` einer anderen Version gleicht.
Für Treffer außerhalb der geladenen Seite bleibt zudem `spanOf(change,
this._changes)` leer; das ist vorhandenes Verhalten, aber gerade deshalb
sollte die neue Rückfrage diesen Pfad nicht ungetestet lassen.

**Konsequenz:** Die Behauptung, alle Wege über `_createVersion` seien durch
Tests belegt, stimmt nicht. Eine künftige Änderung an Suchdaten oder am
Button kann die Rückfrage für diesen vorhandenen Bedienweg verlieren, ohne
dass die neun neuen Tests reagieren.

**Vorschlag:** Ein Szenario mit einem benannten Treffer ausschließlich in
`_searchResults` ergänzen und prüfen, dass zuerst der Bestätigungsdialog
erscheint, »Save anyway« anschließend den Versionsdialog öffnet und Cancel
keinen `next_versions`-Aufruf erzeugt. Den leeren Pending-Bereich entweder
als bestehende Grenze dokumentieren oder gesondert entscheiden.

## Niedrig

### N1 — Der behauptete Ja-Pfad wird im neuen Test vor der Umsetzung nicht belegt

**Fundstelle:** Plan, Task 1, Step 2, Abschnitt 3 und
`test_answering_yes_goes_on_to_the_create_dialog_as_before`.

Der Abschnitt startet `_createVersion`, schließt danach blind
`confirmBox()` mit `"apply"` und prüft nur den Request sowie den offenen
Versionsdialog. Im Ausgangscode ist die Confirm-Box nie offen; ihr
`close("apply")` ist im Node-Stand-in folgenlos, während der Versionsdialog
bereits durch den bisherigen Ablauf geöffnet wurde. Daher ist dieser Test
wie behauptet einer der drei PASS-Fälle und beweist gerade nicht, dass ein
bewusstes »Save anyway« die neue Frage passiert hat.

**Konsequenz:** Ein Fehler, der die Frage zwar öffnet, aber ihre positive
Antwort nicht korrekt zum bisherigen Ablauf weiterleitet, wird nur indirekt
durch andere Tests entdeckt oder kann unbemerkt bleiben.

**Vorschlag:** Vor dem Schließen explizit `confirmBox().open === true`
prüfen und danach zusätzlich belegen, dass sie geschlossen ist, bevor
`next_versions` und der Versionsdialog geprüft werden. Damit ist der
Ende-zu-Ende-Ja-Pfad unabhängig aussagekräftig.

## Bestätigte Punkte ohne Befund

- Die Anker existieren: `_createVersion`, `_alreadyNamed`, `_confirmOverride`,
  `_answerFrom` und `_changeAt`. Vor der Umsetzung gibt es genau drei
  `_confirmOverride`-Vorkommen: Definition sowie je einen Aufruf aus
  `_confirm` und `_openReplace`.
- Die Standardtexte der beiden vorhandenen Aufrufer bleiben mit den
  vorgeschlagenen Default-Parametern erhalten. `_confirm` und
  `_openReplace` schreiben die von `_confirmOverride` veränderten
  Dialogbereiche vor ihrem eigenen Öffnen selbst neu.
- Native Escape-Behandlung passt zum Plan: jede Öffnung setzt
  `returnValue = ""`; Escape schließt das native `dialog` ohne Wert,
  `_answerFrom` liefert diesen leeren Wert und die Abfrage wertet ihn als
  Nein. Die Buttons rufen `close(button.value)` auf.
- Ein während eines offenen Dialogs angefordertes Rendern wird durch
  `_renderOwed` zurückgestellt und in `_answerFrom` vor dem Fortsetzen
  ausgeführt. `_onRecorded` weicht offenen Dialogen ebenfalls aus; keine
  Kollision der vorgesehenen Rückfrage mit dem Versionsdialog oder diesem
  Ereignispfad gefunden.
- Vergleichsmodus, Moduswechsel und Dashboardwechsel eröffnen keinen
  zusätzlichen direkten `_createVersion`-Pfad. Ein nicht vorhandenes oder
  noch nicht geladenes Revisionsergebnis endet bereits an `if (!change)`.
  Mehrere Versionen werden von `_alreadyNamed` gemeinsam benannt. Der im
  Plan ausgesparte Banner-Fall ist korrekt beschrieben: der Button zielt
  auf die neueste getaggte Änderung und der Hinweis benennt deren Tag,
  nicht die passende ältere Version des Live-Stands.
- Spec Entscheidung 7 erlaubt `create_version` weiterhin ohne Service-
  `confirm`; die zusätzliche Panel-Rückfrage widerspricht dem nicht.
  Die vorgesehenen englischen FAQ-/Guide-Sätze und der Commit-Zuschnitt
  entsprechen den Regeln aus `CLAUDE.md`.

## Urteil

**Umsetzbar nach Korrekturen.** Die Implementierungsidee, Dialogmechanik,
Anker und Dokumentation sind stimmig. Vor Umsetzung sollten M1 und N1 in den
Testplan aufgenommen werden.

## Nachweislich ausprobiert

- Eine Scratch-Kopie aus `git archive HEAD` erstellt.
- Die vorgeschlagene Änderung an `_confirmOverride`, `_askAnother` und
  `_createVersion` sowie die vorgesehene Anpassung von `_PENDING_CHANGES`
  dort simuliert.
- `python3 -m pytest tests/test_panel_behaviour.py -q -p no:cacheprovider`:
  **308 passed**.
- `python3 -m pytest tests/ -q -p no:cacheprovider`:
  **1123 passed, 5 skipped**.

## Nur gelesen / geprüft

- Plan, `CLAUDE.md`, Status, bindende Spec Entscheidung 7, FAQ und
  User-Guide.
- `panel.js` einschließlich Dialog-, Render-, Such-, Auswahl-, Vergleichs-
  und Ereignispfade sowie `panel/dialogs.js`.
- Bestehende Node-Szenarien, insbesondere `_PENDING_CHANGES`; kein echter
  Browser und keine lokale Home-Assistant-Testinstanz gestartet.

ENDE DES REVIEWS
