# Review: Behebung der Aufzeichnungslücke (`unrecorded-live-state`)

**Datum:** 2026-10-02  
**Gegenstand:** Branch `unrecorded-live-state`, Commits `9dfdb34` und `83b6ab6` (15 Dateien, ~580 Zeilen Diff)  
**Rolle:** Unabhängiges Review ohne Vorkenntnis der Entstehungssitzung  

---

## 1. Zusammenfassung

Der Branch adressiert ein kritisches Konsistenzproblem: Wenn eine Aufzeichnung fehlschlägt (z. B. durch ein kurzzeitiges Lock der Git-Ablage), driftet der Live-Stand des Lovelace-Dashboards vom neuesten Eintrag im Verlauf ab. Bisher bot das Panel in diesem Zustand »Save this as (another) version« an, wodurch der neueste *aufgezeichnete* Eintrag statt des Live-Stands getaggt wurde.

Die Umsetzung gliedert sich in:
1. **Server (`operations.async_history`):** Neues Feld `unrecorded: bool`, das wahr ist, wenn der Live-Stand lesbar ist, die erste Seite geladen wird und der oberste Eintrag nicht dem Live-Stand gleicht.
2. **Server (`operations.async_record_now` & WebSocket `dashboard_history/record_now`):** Manueller Aufruf von `capture.async_capture(..., reason=RECORDED_BY_HAND)` ohne `confirm` (Nachtrag zu Entscheidung 7), mit Prüfung des Erfolgs über `_same_as_live`.
3. **Panel (beide Modi):** Anzeige des Chips »not recorded«, der Hinweises »This state is not in the history yet.« und des Knopfs »Record it now«, der den Save-Button verdrängt.
4. **Analyse (`analyze/explain.py`):** `RECORDED_BY_HAND` erzeugt dieselben Zählzeilen wie ein reguläres Speichern (`save`), damit `message_adds` weiterhin reine Zählzeilen liest.
5. **Tests & Doku:** Integration in `tests/integration/run_checks.py`, UI-Verhaltenstests in `tests/test_panel_behaviour.py`, Aktualisierung von `status.md`, `specs` und `user-guide.md`.

Die bestehende Testsuite (`1183 passed, 2 skipped`) sowie die Guards `complexity_ratchet.py` und `lint-imports` laufen fehlerfrei durch. Dennoch offenbart die genaue Prüfung der Randfälle und Nebenläufigkeiten mehrere substanzielle Schwachstellen.

---

## 2. Befunde

### Kritisch

#### Befund 1: Fehlendes `unrecorded` bei lebendem Dashboard ohne bisherigen Verlauf
- **Fundstelle:** `custom_components/dashboard_history/operations.py:604–610` (im Zusammenspiel mit `custom_components/dashboard_history/panel/simple.js:263–265`)
- **Status:** Reproduziert (Code-Analyse und Ausführung in Node.js).
- **Beschreibung:**  
  In `operations.py:async_history` lautet die Bedingung für das Serverfeld `unrecorded`:
  ```python
  "unrecorded": bool(
      before is None
      and live is not None
      and rendered
      and not rendered[0]["same_as_now"]
  ),
  ```
  Wenn ein Dashboard in Home Assistant existiert (`live is not None`), aber noch **keinen einzigen Eintrag im Verlauf** hat (z. B. ein neu erstelltes Dashboard, dessen initiale Aufzeichnung fehlschlug, oder ein Dashboard direkt nach einem `forget`), ist `rendered` leer (`[]`). Wegen `and rendered` evaluiert der gesamte Ausdruck zu `False`.
- **Konsequenz (konkretes Szenario):**
  1. Im **Simple-Modus** prüft `simple.js:264`:
     ```javascript
     ${unrecorded ? `<p>${UNRECORDED}</p>${recordButton()}` : saveButton()}
     ```
     Da `unrecorded === false` ist, wird der Button `saveButton()` (»Save this as a version«) gerendert. Klickt der Nutzer darauf, ruft `panel.js:4377` `this._createVersion(this._changes[0]?.revision)` auf. Da `this._changes` leer ist, ist das Argument `undefined`. `_createVersion` bricht in Zeile 2870 mit `if (!change) return;` stillschweigend ab: **Der Klick ist komplett wirkungslos (toter Button).**
     Der Nutzer erhält weder den Chip »not recorded«, noch den Text »This state is not in the history yet.«, noch den funktionierenden Knopf »Record it now«.
  2. Im **Advanced-Modus** zeigt `panel.js:3830–3833` lediglich `<p class="empty muted">No changes recorded for this dashboard.</p>`. Es existiert keinerlei Schaltfläche oder Hinweis, um den Zustand manuell aufzuzeichnen.
- **Vorschlag:**  
  Die Bedingung in `operations.py` muss auch den Fall einer leeren Historie als `unrecorded` einstufen:
  ```python
  "unrecorded": bool(
      before is None
      and live is not None
      and (not rendered or not rendered[0]["same_as_now"])
  ),
  ```
  Zusätzlich sollte im Advanced-Modus bei `!shown.length && this._unrecorded` ebenfalls der Hinweis samt »Record it now«-Button angeboten werden.

---

### Wichtig

#### Befund 2: Nebenläufigkeits- und Timeout-Falle bei `_recordNow` im Panel
- **Fundstelle:** `custom_components/dashboard_history/panel.js:2837–2854` (im Zusammenspiel mit `panel.js:1000–1006` und `panel.js:1043–1053`)
- **Status:** Reproduziert (Simulation in Node.js).
- **Beschreibung:**  
  `_recordNow()` schärft vor dem Aufruf mit `const recorded = this._recorded();` den Listener `this._awaiting`. Danach treten zwei Fehlverhaltensweisen auf:
  1. **Verwaistes `this._awaiting` bei Fehlschlag:**  
     Antwortet der Server mit `result.recorded === false` (z. B. Git-Lock aktiv oder Speicher voll), wird `if (result?.recorded) await recorded;` übersprungen. `_recordNow` zeigt das Fehlerbanner und beendet sich. `this._awaiting` bleibt jedoch für die vollen 3 Sekunden des Timeouts im Panel scharf!  
     Trifft in diesem 3-Sekunden-Fenster ein echtes `dashboard_history_updated`-Ereignis ein (z. B. Speichern eines anderen Dashboards oder ein erfolgreicher Hintergrund-Abgleich), fängt `_onRecorded(event)` dieses Ereignis ab (`if (this._awaiting) { done(); return; }`). Das Ereignis wird stillschweigend verschluckt, und der reguläre Refresh des Panels unterbleibt.
  2. **3-Sekunden-Blockade bei Leerlauf-Erfolg (Idle Success):**  
     Wird »Record it now« gedrückt, während der Stand im Store bereits dem Live-Stand gleicht (z. B. weil ein automatischer Reconcile-Lauf wenige Millisekunden vor dem Klick erfolgreich war):  
     `capture.async_capture` stellt fest, dass das Dashboard unverändert ist (`revisions` ist leer). Daher wird `self._announce` **nicht** aufgerufen (`if revisions and announce:` in `capture.py:275`).  
     `operations.async_record_now` prüft `newest[0].revision in same`, stellt Übereinstimmung fest und antwortet `{"recorded": True}`.  
     Im Panel ist `result?.recorded === true`, weshalb `await recorded;` ausgeführt wird. Da der Server jedoch kein `dashboard_history_updated`-Event gefeuert hat, feuert das Promise erst nach Ablauf des harten 3-Sekunden-Fallbacks (`setTimeout(..., 3000)`).  
     **Konsequenz:** Die UI friert für volle 3 Sekunden im Busy-Status ein, bevor die Seite neu geladen wird.
- **Vorschlag:**  
  1. Schlägt `record_now` fehl oder wirft eine Exception, muss `this._awaiting` sofort abgeräumt werden (`this._awaiting = null`).
  2. `async_record_now` sollte im Ergebnis signalisieren, ob tatsächlich ein Commit geschrieben wurde (z. B. `{"recorded": True, "created": bool}`). Hat es nichts geschrieben, darf das Panel nicht auf das Event warten, sondern kann sofort `_reloadAfterWrite` ausführen.

---

#### Befund 3: Service `create_version` ohne Revision taggt bei Aufzeichnungslücke veralteten Stand
- **Fundstelle:** `custom_components/dashboard_history/operations.py:1212–1223` (und `custom_components/dashboard_history/services.py:142–151`)
- **Status:** Gelesen und verifiziert.
- **Beschreibung:**  
  Der Home-Assistant-Dienst `dashboard_history.create_version` erlaubt das Weglassen des Parameters `revision`, um den aktuellen Stand zu versionieren. In `operations.async_create_version` heißt es:
  ```python
  if not revision:
      newest = await hass.async_add_executor_job(store.list_changes, key, 1)
      if not newest:
          return {"created": None, "error": f"no recorded state for {key}"}
      revision = newest[0].revision
  ```
  `async_create_version` prüft weder, ob `unrecorded` vorliegt, noch ob `newest[0]` mit dem Live-Stand übereinstimmt!
- **Konsequenz (konkretes Szenario):**  
  Ruft ein Nutzer oder eine Automation bei bestehender Aufzeichnungslücke den Dienst `dashboard_history.create_version` auf, taggt das Backend blind den veralteten Commit `newest[0].revision`. Genau das Fehlverhalten, das im Frontend verhindert werden soll, ist über den Home-Assistant-Dienst weiterhin ungebremst möglich.
- **Vorschlag:**  
  Wenn `revision is None`: Prüfen, ob der Live-Stand lesbar ist und ob `newest[0]` diesem Stand gleicht. Falls nicht, entweder analog zu `restore_state` den Live-Stand vorab sichern oder den Aufruf mit einer eindeutigen Fehlermeldung verweigern (z. B. »live state is not recorded yet«).

---

#### Befund 4: Maskierender Mock im Test `_UNRECORDED_NOTE`
- **Fundstelle:** `tests/test_panel_behaviour.py:5276`
- **Status:** Gelesen.
- **Beschreibung:**  
  Im Test `_UNRECORDED_NOTE` wurde `el._recorded` explizit durch einen Dummy ersetzt:
  ```javascript
  // No recorder here to announce anything; its 3 s fallback would only
  // slow the test down.
  el._recorded = () => Promise.resolve();
  ```
- **Konsequenz:**  
  Der Testautor hat das 3-Sekunden-Problem zwar erkannt, es aber im Test wegoptimiert, anstatt das Zusammenspiel im Produktivcode zu lösen. Dadurch testen die Verhaltenstests in `test_panel_behaviour.py` weder das Verhalten von `this._awaiting` bei einem Misserfolg (Befund 2.1) noch die Timeout-Falle bei Idle-Aufrufen (Befund 2.2). Der Test `test_a_successful_recording_says_nothing_and_reloads` suggeriert eine Testabdeckung, die an der realen Implementierung vorbeigeht.
- **Vorschlag:**  
  Nach Behebung von Befund 2 sollte der Test das Zusammenspiel mit echten Events und Timeouts ohne künstliches Wegmocken von `_recorded` abbilden.

---

### Hinweis

#### Befund 5: Race Condition bei gleichzeitigem Speichern während `async_record_now`
- **Fundstelle:** `custom_components/dashboard_history/operations.py:641–657`
- **Status:** Gelesen.
- **Beschreibung:**  
  `async_record_now` liest `live = await async_get_config(hass, key)` ganz zu Beginn. Während `capture.async_capture` läuft, kann ein paralleles Speichern in Home Assistant stattfinden (Stand L2). `async_capture` erfasst Stand L2. Am Ende prüft `async_record_now`:
  ```python
  same = await hass.async_add_executor_job(
      _same_as_live, store, key, [newest[0].revision], live
  )
  return {"recorded": newest[0].revision in same}
  ```
  Hier wird `newest[0]` (Stand L2) mit der alten Variablen `live` (Stand L1) verglichen. Das Ergebnis ist `False`.
- **Konsequenz:**  
  `record_now` meldet einen Fehler (`{"recorded": False}`), und das Panel zeigt das Fehlerbanner, obwohl der neue Stand L2 in Wahrheit erfolgreich aufgezeichnet wurde.
- **Vorschlag:**  
  Vor dem Aufruf von `_same_as_live` sollte `live` erneut via `async_get_config` abgefragt werden.

---

#### Befund 6: Dashboard-Wechsel während laufendem `_recordNow`
- **Fundstelle:** `custom_components/dashboard_history/panel.js:2833–2856`
- **Status:** Gelesen.
- **Beschreibung:**  
  Wechselt der Nutzer während `_call("record_now")` auf ein anderes Dashboard B, liefert `_guard` das Ergebnis zurück. War die Aufzeichnung für Dashboard A erfolgreich, ruft `_recordNow` Zeile 2855 auf:
  ```javascript
  const stale = await this._reloadAfterWrite("the state was recorded");
  ```
  `_reloadAfterWrite` führt ein `_refresh()` aus, welches nun Dashboard B neu lädt.
- **Konsequenz:**  
  Unerwünschter, überraschender Reload von Dashboard B.
- **Vorschlag:**  
  Vor `_reloadAfterWrite` mit `if (this._selected === asked)` sicherstellen, dass der Nutzer sich noch auf dem betroffenen Dashboard befindet.

---

#### Befund 7: Fehlender isolierter Unit-Test für WebSocket `record_now`
- **Fundstelle:** `custom_components/dashboard_history/websocket_api.py:84–89`
- **Status:** Gelesen.
- **Beschreibung:**  
  Der neue Befehl `dashboard_history/record_now` wird ausschließlich im Integrationstest `tests/integration/run_checks.py` getestet. Ein pytest-kompatibler Test auf Modulebene existiert nicht.
- **Konsequenz:**  
  Geringere Testabdeckung in der schnellen lokalen Testsuite.

---

## 3. Systematische Prüfung der Randfälle

| Randfall | Status | Bewertung |
|---|---|---|
| **Gelöschtes Dashboard** | Korrekt | `async_history` liefert `unrecorded: False`, da `live is None`. `async_record_now` liefert sofort `{"recorded": False}`. |
| **Dashboard ohne Verlauf** | **Fehlerhaft** | Betroffen von **Befund 1**. Server meldet fälschlicherweise `unrecorded: False`; Simple Mode zeigt toten Save-Button. |
| **Standard-Dashboard (`lovelace`)** | Korrekt | Wird regulär über `keys.py` / `snapshot.py` aufgelöst und verhält sich identisch zu benannten Dashboards. |
| **Blättern & `restarted`-Antwort** | Korrekt | `async_history` setzt `unrecorded: False` bei `before is not None`. Bei einem `forget`-Restart wird eine neue erste Seite mit aktuellem `unrecorded` erzeugt und im Panel sauber übernommen. |
| **Suche** | Korrekt | `async_search` liefert kein `unrecorded`. Das Panel behält den Zustand der ersten Seite; im Simple-Modus bleibt der »Record it now«-Button sichtbar. |
| **Wechsel während `_recordNow`** | Unschön | Siehe **Befund 6**; führt zu unschönem Refresh des neu gewählten Dashboards. |
| **Paralleles Speichern / Reconcile** | Kritische Pfade | Siehe **Befund 2.2** (3s UI-Freeze) und **Befund 5** (falsche Fehleranzeige). |
| **Doppelter Refresh via `updated`-Event** | Gefährdet | Siehe **Befund 2.1**; bei Fehlschlag wird das nächste Event verschluckt. |

---

## 4. Einhaltung der harten Regeln (`CLAUDE.md`)

- **Admin-Pflicht:** Eingehalten. Der neue WebSocket-Befehl ist mit `@websocket_api.require_admin` über `_command` geschützt.
- **Startup nicht blockieren:** Eingehalten. `record_now` läuft ausschließlich auf Nutzeranforderung; `capture.py` fängt Fehler ab.
- **Executor-Nutzung:** Eingehalten. Git-Zugriffe (`store.list_changes`, `_same_as_live`, `_write_one`) laufen ausnahmslos in `hass.async_add_executor_job`.
- **HA-freie Module:** Eingehalten. `analyze/explain.py` und `analyze/__init__.py` bleiben vollständig frei von Home-Assistant-Imports. `lint-imports` bestätigt dies (`Contracts: 2 kept, 0 broken`).
- **Keine Logik im Panel:** Eingehalten. Die Panel-eigene Heuristik aus Commit 1 (`liveIsRecorded`) wurde in Commit 2 konsequent durch das Serverfeld `unrecorded` ersetzt.
- **Entscheidung 7:** Eingehalten. `record_now` schreibt einen Verlaufseintrag und modifiziert kein Dashboard. Daher ist kein `confirm` erforderlich (Nachtrag zu Entscheidung 7 ist konsistent dokumentiert).

---

## 5. Fazit und Urteil

Die Idee, die Aufzeichnungslücke über das Serverfeld `unrecorded` und die Aktion `record_now` explizit zu behandeln, ist architektonisch sauber und löst das Problem des Fehl-Taggens im Frontend im Normalfall zuverlässig.

Allerdings verhindern **Befund 1** (Versagen bei Dashboards ohne Verlauf) und **Befund 2** (3-Sekunden-Blockade und Event-Verschlucken durch verwaiste Listener in `_recordNow`) einen sofortigen Merge.

**Urteil:** **Mergebar nach Korrekturen** (Behebung von Befund 1 und Befund 2; Befund 3 empfohlen).

ENDE DES REVIEWS
