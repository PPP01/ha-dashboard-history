**Trifft zu.** Beide Abweichungen sind auf `unrecorded-live-state` möglich.
Die Sperre über `unrecorded` gilt für die gelesene History-Antwort; sie bindet
weder den Klick an die tatsächlich gerenderte Revision noch `record_now` an
den zuvor angezeigten Live-Stand.

### Eine Version kann einen anderen Stand als die sichtbare Box erhalten

Genaue Abfolge:

1. Die Box zeigt Stand A, die erste geladene Revision ist `rA`,
   `unrecorded` ist falsch. Eine historische Zeile ist aufgeklappt.
2. Eine zweite Instanz speichert B. Capture zeichnet B als `rB` auf und
   das Ereignis startet `_refresh()`.
3. `_refresh()` ersetzt bereits `this._changes` durch die neue Liste mit
   `rB` und aktualisiert `_unrecorded`
   (`custom_components/dashboard_history/panel.js:1078`, `:1086`).
4. Die aufgeklappte Zeile existiert weiter. Der Refresh wartet deshalb auf
   `_detailFor(open)` (`panel.js:1093`, `:1100`). Das neue Rendern folgt
   erst bei `panel.js:1118`. Während dieses Wartens zeigt der DOM weiterhin A.
5. Die Person klickt den sichtbaren »Save this as a version«-Knopf für A.
   Dessen Attribut enthält nur `"now"`. Der Handler liest aus dem inzwischen
   geänderten Modell `this._changes[0].revision`, also `rB`
   (`panel.js:4376–4377`).
6. `_createVersion()` hält diesen Eintrag fest (`panel.js:2868–2870`) und
   sendet beim Bestätigen `revision: change.revision` (`panel.js:3077`).
   `async_create_version()` übergibt genau diese Revision an den Store;
   eine Bindung an den angezeigten Live-Stand fehlt
   (`custom_components/dashboard_history/operations.py:1228–1236`). Die
   Version landet auf B, obwohl der auslösende Knopf in der Box für A stand.

**Reproduziert:** Die unveränderte `_refresh()`-Methode wurde in Node mit
kontrolliert verzögerter Detailantwort ausgeführt. Während des Wartens:
`{"displayed":"rA","nowClickRevision":"rB"}`. Anschließende Übergabe an
den Versionsbefehl: am tatsächlichen Code nachvollzogen.

**Kleinster Fix für diese Abweichung:** Den »now«-Button beim Rendern mit der
konkreten Revision dieser Darstellung versehen und beim Klick diese Revision
verwenden. Die Übersetzung aus `"now"` über das veränderliche Modell entfällt.
Das gilt für beide Modi und alle Varianten des Save-Buttons. Eine bereits
festgehaltene Revision wird durch spätere Saves nicht von selbst umgebogen;
das Problem liegt hier vor dem Festhalten im Klick-Handler.

### `record_now` kann Erfolg für einen anderen als den gesehenen Stand melden

Genaue Abfolge:

1. Die Person sieht die Box für den unaufgezeichneten Stand A.
2. Eine zweite Instanz speichert oder restauriert B. Das erste Panel hat
   noch keine neue Anzeige erhalten; die Person klickt »Record it now«.
3. `_recordNow()` sendet ausschließlich den Dashboard-Schlüssel, keine
   Identität von A (`custom_components/dashboard_history/panel.js:2840`).
4. `async_record_now()` liest jetzt B (`operations.py:642`). Capture liest
   ebenfalls B und zeichnet B auf (`operations.py:648`,
   `custom_components/dashboard_history/capture.py:168–173`, `:183`).
5. Die Prüfung vergleicht `rB` mit B und liefert `{"recorded": true}`
   (`operations.py:653–659`). A war nie Teil dieses Requests.

**Ein zusätzliches Rennen liegt innerhalb der Prüfung:** Der Aufruf liest A,
Capture zeichnet A auf, `list_changes` liefert `rA`. Zwischen diesem
Executor-Aufruf und `_same_as_live` zeichnet ein paralleler Save B als `rB`
auf. Geprüft wird weiterhin die festgehaltene Revision `rA` gegen A; das
Ergebnis ist `true`, obwohl der neueste Eintrag bereits B enthält
(`operations.py:653–659`). Die getrennten Capture-Locks umfassen diese
Abschlussprüfung nicht (`capture.py:168–173`).

**Reproduziert:** Die unveränderte Funktion `async_record_now` wurde aus dem
Python-AST ausgeführt, mit kontrollierten Fakes für HA, Capture und Store.
Sowohl beim Wechsel vor dem Request als auch nach `list_changes` war das
Ergebnis: gesehen A, live B, neuester Eintrag B, `recorded: true`.
Es wurde keine HA-Instanz verwendet.

**Kleinster Fix für die Zusage »den gesehenen Stand aufzeichnen«:** `history`
muss eine serverseitig erzeugte Inhaltskennung des gelesenen Live-Stands
liefern. Das Panel bindet sie an den gerenderten Record-Knopf und sendet sie
als Erwartungswert mit. Der Server verweigert einen inzwischen abweichenden
Stand und zeichnet nur den gegen diese Kennung geprüften Snapshot auf;
Capture darf dafür nicht unabhängig einen anderen Snapshot neu lesen.
Der Erfolg sollte die tatsächlich aufgezeichnete Revision zurückgeben.
Soll zusätzlich »ist der neueste Eintrag« zugesagt werden, müssen dessen
Ermittlung und Inhaltsprüfung gemeinsam gegen konkurrierende
History-Schreiber abgesichert werden. Diese Aussage gilt am Prüfzeitpunkt;
ein anschließender Save darf die Historie selbstverständlich weiterführen.
Ein bloßes erneutes Lesen von Live nach Capture bindet den Vorgang weiterhin
nicht an das zuvor gesehene A.

ENDE DES REVIEWS
