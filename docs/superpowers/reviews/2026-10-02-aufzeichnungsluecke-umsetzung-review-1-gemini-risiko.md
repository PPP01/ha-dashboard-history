# Review: Nebenläufigkeitsrisiken bei Aufzeichnungslücke (`unrecorded-live-state`)

**Aussage:** **Trifft zu**

Unter Nebenläufigkeit (paralleles Speichern in Home Assistant, Restore über eine zweite Panel-Instanz oder verzögerter `reconcile`-Lauf) können auf dem Branch `unrecorded-live-state` **beide** in der Frage beschriebenen Fehlerbilder eintreten:

1. Eine Version kann auf einem anderen Stand landen als dem Live-Stand, den die »Right now«-Box im Panel beschreibt.
2. `record_now` kann `{"recorded": true}` melden, obwohl der neueste Eintrag nicht der Stand ist, den die Person gesehen hat.

---

## 1. Begründung und Fundstellen

### Zu Frage 1: Version landet auf anderem Stand als dem von »Right now« beschriebenen Live-Stand
- **Fundstelle 1 (Split-Brain beim Laden):** `custom_components/dashboard_history/panel.js:1066–1069` und `custom_components/dashboard_history/panel.js:1452–1455`
  `_refresh()` und `_select()` rufen `history` und `versions` als zwei getrennte WebSocket-Befehle via `Promise.all` ab. Ändert sich der Live-Stand zwischen der Ausführung beider Befehle auf dem Server, stammen `this._changes[0]` (aus `history`) und `this._versionsMatchingNow()` (aus `versions`, siehe `panel.js:3978`) aus zwei verschiedenen Live-Ständen.
- **Fundstelle 2 (Starre Auflösung beim Klick):** `custom_components/dashboard_history/panel.js:4376–4377`
  Beim Klick auf den Save-Button der »Right now«-Box wird `"now"` clientseitig starr aufgelöst:
  `this._createVersion(which === "now" ? this._changes[0]?.revision : which);`
- **Fundstelle 3 (Unterdrückte Aktualisierung bei Dialog):** `custom_components/dashboard_history/panel.js:1008`
  `if (this.shadowRoot?.querySelector("dialog[open]")) return;` unterdrückt in `_onRecorded` alle Hintergrund-Aktualisierungen (`EVENT_RECORDED`), solange der Versions-Dialog offen ist.
- **Fundstelle 4 (Fehlende Server-Validierung):** `custom_components/dashboard_history/operations.py:1171–1237`
  `async_create_version` übernimmt die vom Panel übermittelte `revision` ungeprüft und validiert nicht, ob diese noch dem aktuellen Live-Stand entspricht.

### Zu Frage 2: `record_now` meldet `{"recorded": true}` für einen anderen Stand als den gesehenen
- **Fundstelle:** `custom_components/dashboard_history/operations.py:641–659` (`async_record_now`)
  `async_record_now` erwartet vom Panel keinerlei Zustands-Identifikator (keine Revision, keinen Hash des gesehenen Zustands). In Zeile 642 liest `live = await async_get_config(hass, key)` den Stand erst im Moment der Server-Ausführung. In Zeile 648 committet `capture.async_capture(key=key, reason=RECORDED_BY_HAND)` diesen (neuen) Stand. Zeile 656–659 vergleicht den neuesten Commit mit eben diesem neu gelesenen `live` und liefert `{"recorded": True}` zurück.

---

## 2. Genaue zeitliche Abfolgen

### Ablauf A: Version landet auf anderem Stand als von der »Right now«-Box beschrieben

#### Variante A1: Split-Brain beim Laden / Refreshen
1. Ausgangslage: Git-HEAD ist Commit 2 (Stand S2). In Home Assistant ist der Live-Stand S2. Version `v1.0.0` markiert einen älteren Commit 1 (Stand S1).
2. Das Panel fordert die Daten an (`panel.js:1066–1069`): `Promise.all([history, versions])`.
3. Der Server bearbeitet zuerst `history`:
   - `operations.py:568`: `live` ist Stand S2.
   - `rendered[0]` ist Commit 2 (S2). `rendered[0]["same_as_now"]` ist `True`.
   - `unrecorded` ist `False`.
   - `changes[0]` ist Commit 2 (S2).
4. **Nebenläufiges Ereignis:** Eine zweite Panel-Instanz führt `restore_state` auf Version `v1.0.0` (Commit 1, Stand S1) aus (oder Home Assistant stellt S1 wieder her). Der Live-Stand in Home Assistant ist nun S1.
5. Der Server bearbeitet nun `versions`:
   - `operations.py:async_versions` liest `live` aus Home Assistant: Stand S1.
   - `v1.0.0` (Commit 1) stimmt mit `live` überein -> erhält `same_as_now = True`.
6. Das Panel verarbeitet beide Antworten:
   - `this._changes[0]` ist Commit 2 (S2).
   - `this._unrecorded` ist `False`.
   - `this._versionsMatchingNow()` liefert `v1.0.0` (S1).
   - Die »Right now«-Box (`panel.js:3921–3925`) zeigt an:
     *»What the dashboard holds right now is the same state as v1.0.0.«*
   - Da `this._unrecorded` `false` ist, zeigt `_nowActs` (`panel.js:3948`) den Button:
     *»Save this as another version«* (`data-version="now"`).
7. Der Nutzer liest, dass das Dashboard den Stand von `v1.0.0` hat, und klickt auf »Save this as another version«.
8. `panel.js:4377` übergibt `this._changes[0]?.revision` (Commit 2!).
9. `async_create_version` erzeugt die neue Version auf **Commit 2 (Stand S2)**.
**Ergebnis:** Die neue Version landet auf Stand S2, obwohl die »Right now«-Box dem Nutzer Stand S1 (`v1.0.0`) beschrieben hat.

#### Variante A2: Nebenläufige Änderung bei geöffnetem Versions-Dialog
1. Ausgangslage: Dashboard ist auf Stand S1 (`changes[0]` = Commit 1, `unrecorded` = `false`). Die »Right now«-Box beschreibt Stand S1.
2. Der Nutzer klickt auf »Save this as a version« (`data-version="now"`).
3. `panel.js:2868` öffnet den modalen Dialog `dialog.version` mit gebundenem `change.revision = Commit 1`.
4. Während der Nutzer den Titel eingibt, speichert ein anderer Benutzer (oder eine Automation) das Dashboard auf Stand S2.
5. Home Assistant feuert `EVENT_HISTORY_UPDATED`.
6. `_onRecorded` im Panel bricht wegen `panel.js:1008` (`dialog[open]`) ab; das Panel ignoriert die Änderung.
7. Der Nutzer klickt auf »Create«. `_createVersion` sendet `revision: Commit 1` (`panel.js:3077`).
8. `async_create_version` taggt Commit 1.
**Ergebnis:** Das Dashboard läuft auf Stand S2, die aus der »Right now«-Box erstellte Version taggt jedoch den veralteten Stand S1.

---

### Ablauf B: `record_now` meldet `{"recorded": true}` für fremden Stand
1. **Anzeige:**
   - In Home Assistant existiert Stand A (z. B. ungespeichert in Git nach fehlgeschlagenem automatischem Save).
   - Git-HEAD ist Stand 0.
   - `async_history` meldet `unrecorded: true`.
   - Das Panel zeigt den Chip `not recorded`, die Zeile `This state is not in the history yet.` und den Button `Record it now`.
   - Die Person sieht Stand A auf dem Dashboard und im Panel.
2. **Nebenläufige Änderung:**
   - Bevor die Person klickt (oder während der WebSocket-Aufruf läuft), speichert ein anderer Benutzer, eine Automation oder ein Restore Stand B in Home Assistant.
   - Der Live-Stand in Home Assistant ist nun Stand B. Stand A ist aus Home Assistant verdrängt.
3. **Klick & Ausführung:**
   - Die Person klickt auf »Record it now«, um den von ihr gesehenen Stand A aufzuzeichnen.
   - `operations.py:642` (`async_record_now`) wird aufgerufen:
     - Zeile 642: `live = await async_get_config(hass, key)` liest den neuen Stand B aus Home Assistant.
     - Zeile 648: `await capture.async_capture(key=key, reason=RECORDED_BY_HAND)` committet Stand B (Commit B).
     - Zeile 653: `newest = await hass.async_add_executor_job(store.list_changes, key, 1)` liefert Commit B.
     - Zeile 656–658: `_same_as_live` vergleicht Commit B mit `live` (Stand B) -> Übereinstimmung.
     - Zeile 659: `return {"recorded": newest[0].revision in same}` liefert `{"recorded": True}`.
4. **Antwort:**
   - Das Panel empfängt `recorded: true` und lädt neu.
   - In der Historie steht an oberster Stelle Commit B.
   - Der von der Person gesehene Stand A wurde **nie** in die Historie aufgenommen und ist verloren.
**Ergebnis:** `record_now` bestätigt den Erfolg (`{"recorded": true}`), obwohl der neueste Eintrag nicht der Stand ist, den die Person gesehen hat.

---

## 3. Der kleinste Fix

### Kleinstes Fix-Paket:

1. **Für `record_now` (`operations.py` & `panel.js`):**
   - In `panel.js:2840` übergibt `_recordNow` die oberste Revision, auf der die Lücke festgestellt wurde:
     `this._call("record_now", { dashboard: asked, expected_base: this._changes[0]?.revision })`
   - In `operations.py:621` prüft `async_record_now`, ob der HEAD vor dem Capture noch `expected_base` entspricht:
     Hat sich der HEAD zwischenzeitlich bewegt (durch nebenläufiges Speichern oder Restore), bricht `async_record_now` ab und meldet `{"recorded": False, "stale": True}`.

2. **Für die »Right now«-Box (`panel.js` & `operations.py`):**
   - In `panel.js:3978` und `panel/simple.js:333` darf `matching` nicht aus der separaten `versions`-Abfrage stammen, sondern muss zwingend das im selben Aufruf wie `_changes` berechnete `this._matching` (`history.matching_versions`) verwenden. Dadurch wird das Split-Brain zwischen Zeilen und Box eliminiert.
   - In `panel.js:4377` bei Klick auf `"now"` vor dem Öffnen des Dialogs prüfen, ob die Revision noch dem HEAD entspricht bzw. beim Schließen des Dialogs in `_createVersion` prüfen, ob das Panel zwischenzeitlich ein Update erhalten hat.
   - Im Backend in `async_create_version` (`operations.py:1171`): Wenn eine Version für den aktuellen Live-Stand angelegt werden soll (oder wenn kein expliziter Commit-Hash aus einer historischen Zeile übergeben wurde), serverseitig prüfen, ob die zu taggende Revision mit dem aktuellen `live`-Stand übereinstimmt (`_same_as_live`), und andernfalls mit Fehler ablehnen.

ENDE DES REVIEWS
