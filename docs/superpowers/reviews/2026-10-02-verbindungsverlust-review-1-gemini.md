# Review: Verbindungsverlust beim Start abfangen (Commit 321f234)

**Datum:** 2026-10-02  
**Gegenstand:** Commit `321f2348a43bcdd371e23dd8b7c90e620829ddcd` auf Branch `main` (3 Dateien, +133 / -6 Zeilen)  
**Rolle:** Unabhängiges Review (rein lesend, keine Codeänderungen)  

---

## 1. Zusammenfassung

Der Commit `321f234` behebt ein unschönes Hängenbleiben des Panels, wenn es während eines Neustarts von Home Assistant geöffnet wird:
1. **Fehlerbeschreibung (`describeError`):** Anstelle einer nackten roten Ziffer »3« (`ERR_CONNECTION_LOST` aus `home-assistant-js-websocket`) wird ein verständlicher Satz (`CONNECTION_LOST_MESSAGE`) angezeigt.
2. **Optische Darstellung (`.banner.notice`):** Der Verbindungsfehler wird als schwebendes Banner (`position: fixed`, 96px oberhalb des unteren Bildschirmrandes) in den Farben des Home-Assistant-eigenen Toasts dargestellt, direkt über dem HA-Hinweis »Verbindung getrennt«.
3. **Automatisches Nachladen (`_retryOnReconnect`):** Sobald die WebSocket-Verbindung das Event »ready« meldet, lädt das Panel die Dashboard-Liste selbstständig nach, sofern noch keine Dashboards geladen sind (`_dashboards === null`) und kein Ladevorgang aktiv ist (`!_busy`). Polling während des Reboots wird vermieden.

Die Überprüfung anhand der Testsuite (`1201 passed, 2 skipped`), der Ratchet (`tools/complexity_ratchet.py: 20 known values, none grew`) und der Importverträge (`lint-imports`) verlief erfolgreich. Die empirische Prüfung am laufenden Container (Home Assistant 2026.8.3) sowie die Code-Analyse zeigen eine saubere, architekturkonforme Lösung mit zwei wichtigen Detailbefunden.

---

## 2. Befunde

### Kritisch

*Keine Befunde in dieser Kategorie.* Der Commit enthält keine Showstopper, führt keine Regressionen ein und blockiert weder den Start noch die Bedienung von Home Assistant.

---

### Wichtig

#### Befund 1: Textueller Fehlschluss und verwaistes Banner bei Verbindungsverlust nach dem Erstladen
- **Fundstelle:** `custom_components/dashboard_history/panel.js:140–141`, `panel.js:812–814`, `panel.js:1218–1220`
- **Status:** Verifiziert (Code-Analyse und logische Pfadanalyse).
- **Beschreibung:**  
  Die Konstante `CONNECTION_LOST_MESSAGE` formuliert ein Versprechen:
  > »Lost the connection to Home Assistant. The history loads again once it is back.«
  
  Dieser Satz wird über `describeError(err)` nun an sämtlichen fünf Fehlerstellen im Panel verwendet. Allerdings greift die automatische Nachlade-Logik in `_retryOnReconnect` ausschließlich beim initialen Erstladen:
  ```javascript
  const retry = () => {
    if (this._dashboards === null && !this._busy) this._loadDashboards();
  };
  ```
  Sobald das Panel die Dashboard-Liste einmal erfolgreich geladen hat, ist `this._dashboards` ein Array (`this._dashboards !== null`).
  
  Tritt nun *nach* dem Erstladen ein Verbindungsabbruch auf, entstehen zwei problematische Pfade:
  1. **Umschalten des Dashboards oder Detail-Abruf (`_select`, `_loadDetail`):**  
     Bricht die Verbindung während `_select()` oder `_loadDetail()` ab, fängt `_guard` bzw. `.catch()` den Fehler ab und setzt `this._error = CONNECTION_LOST_MESSAGE`. Das schwebende Notice-Banner erscheint und verspricht: »The history loads again once it is back.«  
     Kehrt die Verbindung zurück (`ready`), tut `retry()` jedoch **nichts**, da `this._dashboards !== null` ist! Der Verlauf wird **nicht** nachgeladen, und das schwebende Banner bleibt dauerhaft stehen, bis der Nutzer manuell interagiert.
  2. **Schreiboperationen (`_reloadAfterWrite`):**  
     Schlägt nach einer Aktion (z. B. Version erstellen, umbenennen oder Karte wiederherstellen) das anschließende Neuladen wegen eines Verbindungsabbruchs fehl, generiert Zeile 1219 den Text:  
     `"${done}, but the page could not be reloaded: Lost the connection to Home Assistant. The history loads again once it is back."`  
     Auch hier lädt nach dem Reconnect nichts von selbst nach. Zudem wird hier das Banner wegen der Text-Ungleichheit als normales rotes Banner oben gerendert (siehe Befund 3).
- **Konsequenz:**  
  Der Nutzer wird durch den Wortlaut getäuscht: Ihm wird versichert, die Historie lade bei Wiederkehr der Verbindung automatisch nach, was bei einem bereits initialisierten Panel jedoch nicht geschieht.
- **Vorschlag:**  
  Entweder wird das automatische Neuladen im Reconnect-Handler auf fehlgeschlagene Ansichten erweitert (z. B. wenn `this._error === CONNECTION_LOST_MESSAGE`, dann `this._refresh()`), oder `CONNECTION_LOST_MESSAGE` wird neutraler formuliert (z. B. »Lost the connection to Home Assistant.«), während das automatische Nachladen dem Erstladefall vorbehalten bleibt.

---

#### Befund 2: Fehlende Testabdeckung für Fehlerobjekt `{code: 3}` und Lifecycle-Hook
- **Fundstelle:** `tests/test_panel_behaviour.py:9845`, `tests/test_panel_behaviour.py:9866`
- **Status:** Verifiziert (Gegenprüfung gegen Test-Harness).
- **Beschreibung:**  
  1. In `panel.js:133–136` wird ausführlich dokumentiert, dass `home-assistant-js-websocket` zwei Fehlerformen wirft: eine primitive Zahl `3` bei Aufrufen in der Verbindungslücke und ein Objekt `{code: 3, message: "Connection lost"}` bei Anfragen, die während des Verbindungsabbruchs bereits unterwegs waren (in-flight).  
     Im Test `_HARNESS_RECONNECT` wirft `el._call` jedoch ausschließlich die nackte Zahl (`if (!up) throw 3;`). Die Objektform `{code: 3}` wird von keinem einzigen Test geprüft.
  2. Der Test `test_leaving_the_panel_removes_the_reconnect_listener` ruft im Harness direkt `el._unlisten()` auf. Er beweist damit zwar, dass `_unlisten()` den Listener entfernt, beweist aber nicht den eigentlichen Lifecycle-Vertrag des Custom Elements (`disconnectedCallback()`). Sollte jemand versehentlich den Aufruf von `this._unlisten()` in `disconnectedCallback()` entfernen, bliebe dieser Test weiterhin grün.
- **Konsequenz:**  
  Eine der beiden im Code explizit berücksichtigten Fehlerformen (`err?.code === ERR_CONNECTION_LOST`) ist ungetestet.
- **Vorschlag:**  
  Einen Testfall ergänzen, der `{code: 3, message: "Connection lost"}` wirft, und im Unlisten-Test `el.disconnectedCallback()` statt `el._unlisten()` aufrufen.

---

### Hinweis

#### Befund 3: Verhalten bei Textungleichheit in `_reloadAfterWrite`
- **Fundstelle:** `custom_components/dashboard_history/panel.js:4301` i. V. m. `panel.js:1218–1220`
- **Status:** Geprüft und verifiziert.
- **Beschreibung:**  
  In Zeile 4301 entscheidet die strikte Gleichheit:
  ```javascript
  ${this._error ? `<div class="banner${this._error === CONNECTION_LOST_MESSAGE ? " notice" : ""}"><span class="grow">${escape(this._error)}</span></div>` : ""}
  ```
  In `_reloadAfterWrite` wird `describeError(err)` in einen längeren Satz eingebettet (`${done}, but the page could not be reloaded: ${why}`). Dadurch ist `this._error !== CONNECTION_LOST_MESSAGE`, und die Klasse `notice` wird nicht vergeben. Die Meldung erscheint im regulären roten Fehlerbanner oben im Panel.
- **Einschätzung:**  
  Dieses Verhalten ist **vollkommen akzeptabel und fachlich richtig**:  
  Wenn eine Schreiboperation ausgeführt wurde, der anschließende Reload aber scheitert, befindet sich die Oberfläche in einem unklaren Zustand. Dies ist ein potenziell kritischer Vorgang, der die prominente rote Fehleranzeige oben im Panel erfordert. Der dezente, schwebende Toast unten ist für unverschuldete, rein passive Verbindungsabbrüche gedacht.

---

#### Befund 4: Verhalten bei `unknown_command` vor Abschluss des Komponenten-Setups
- **Fundstelle:** `custom_components/dashboard_history/panel.js:150–154`, `panel.js:812–814`
- **Status:** Geprüft (Verhalten von Home Assistant WebSocket API).
- **Beschreibung:**  
  Startet Home Assistant neu, öffnet der Core die WebSocket-Schnittstelle sehr früh. Es kann vorkommen, dass `connection` bereits das Event »ready« signalisiert, während die Integration `dashboard_history` noch in `async_setup_entry` initialisiert wird und ihre WebSocket-Endpunkte noch nicht registriert hat.  
  Wird in diesem Zeitfenster `_call("dashboards")` abgesetzt, antwortet HA mit `{code: "unknown_command", message: "Unknown command"}`.
- **Einschätzung:**  
  1. `describeError` erkennt `unknown_command` nicht als Verbindungsverlust (`code !== 3`) und gibt den String `"Unknown command"` zurück.
  2. Das Panel zeigt ein rotes Standardbanner »Unknown command«, während die Seitenleiste auf »Reading the history…« stehen bleibt.
  3. Da die WebSocket-Verbindung bereits »ready« ist, feuert kein weiteres Reconnect-Event. Das Panel bleibt stehen, bis der Anwender manuell den Reload-Button `⟲` anklickt.  
  Dieses Verhalten ist nicht Teil des Commits und tritt in der Praxis nur bei stark verzögertem Setup auf, sollte aber für zukünftige Robustheits-Härtungen im Blick behalten werden.

---

#### Befund 5: CSS-Positionierung (`position: fixed`) und CSS-Variablen
- **Fundstelle:** `custom_components/dashboard_history/panel/style.js:501–514`
- **Status:** Empirisch verifiziert im Docker-Container `dashboard-history-test` (HA 2026.8.3).
- **Beschreibung & Prüfung:**  
  1. **Containing Block:**  
     Ein Element mit `position: fixed` im Shadow-Root orientiert sich am Viewport, es sei denn, ein Vorfahrelement besitzt `transform`, `perspective`, `filter` oder `contain: paint`.  
     Prüfung: `:host` setzt lediglich `container-type: inline-size`. Weder `:host` noch die HA-Container (`ha-panel-custom`, `partial-panel-resolver`) setzen im Standard `transform` oder Paint-Containment. Das Banner zentriert sich korrekt horizontal im Viewport (`left: 50%; transform: translateX(-50%)`) und schwebt 96px über dem unteren Fensterrand.
  2. **Bedienelemente überdecken:**  
     Bei `bottom: 96px` überdeckt das Banner die unteren Einträge der Liste oder des Inhaltsbereichs. Da bei getrennter Verbindung keine Interaktionen mit dem Backend möglich sind und wichtige Bedienelemente (Reload-Button in der Kopfleiste, modale Dialoge im Top-Layer) frei bleiben, ist dies unkritisch.
  3. **CSS-Variablen & Fallbacks:**  
     Eine Inspektion der Frontend-Quellen von Home Assistant 2026.8.3 (`hass_frontend/frontend_latest/39913.*.js`) ergab, dass Home Assistants eigene Toast-Komponente (`.toast`) exakt dieselben Variablen nutzt:
     ```css
     background-color: var(--ha-color-neutral-10);
     color: var(--ha-color-on-neutral-loud);
     ```
     Die im Commit hinterlegten Fallbacks (`var(--ha-color-neutral-10, #323232)` und `var(--ha-color-on-neutral-loud, #fff)`) sind exakt gewählt und gewährleisten in allen Themes (Light, Dark, Custom) einen einwandfreien Kontrast.

---

#### Befund 6: Listener-Management und Nebenläufigkeit in `_retryOnReconnect`
- **Fundstelle:** `custom_components/dashboard_history/panel.js:768`, `panel.js:810–817`, `panel.js:820–828`
- **Status:** Geprüft und verifiziert.
- **Beschreibung:**  
  1. **Doppelte Listener:**  
     `set hass` wird bei jedem Zustandswechsel in HA aufgerufen und stößt `_listen()` an. In `_retryOnReconnect` verhindert der Guard `if (this._readyOff) return;` zuverlässig, dass mehrfache Event-Listener auf `connection` registriert werden.
  2. **Objektidentität:**  
     In `home-assistant-js-websocket` bleibt das `connection`-Objekt über Reconnects hinweg identisch. Es wird nicht ersetzt, sondern feuert auf derselben Instanz das Event `"ready"`.
  3. **Rennen zwischen »ready« und `_busy`:**  
     `retry` prüft `if (this._dashboards === null && !this._busy)`. Da `home-assistant-js-websocket` ausstehende Anfragen beim Verbindungsabbruch sofort verwirft und vor dem erfolgreichen Handshake keine neuen annimmt, ist `_busy` bei Eintreffen von `"ready"` praktisch immer `0`.

---

#### Befund 7: Einhaltung der Projektregeln
- **Fundstelle:** `@CLAUDE.md`, Spec
- **Status:** Vollständig eingehalten.
- **Prüfung:**  
  - *Nichts blockiert den HA-Start / kein Polling:* Es gibt keine `setInterval`-Schleifen; das Panel reagiert rein passiv auf das `"ready"`-Event der WebSocket-Verbindung.
  - *Keine Eingriffe in HA-Interna / kein Monkey-Patching:* Es wird ausschließlich die offizielle öffentliche Schnittstelle `connection.addEventListener("ready", ...)` verwendet.
  - *Keine HA-Webkomponenten:* Das Banner ist als reines HTML/CSS (`<div class="banner notice">`) im Shadow-Root realisiert.
  - *Sprach- und Codekonventionen:* Englische Bezeichner, Kommentare und Commit-Messages im Code; Dokumentation der Gründe (das *Warum*) in den Kommentaren vorbildlich gepflegt.

---

## 3. Urteil

**Umsetzbar nach Korrekturen (Minor)**

Der Commit löst das Kernproblem (die nackte »3« beim Öffnen während eines Home-Assistant-Neustarts) elegant und regelkonform. Die optische Abstimmung auf den HA-eigenen Toast ist hervorragend gelungen.

Vor dem endgültigen Abschluss sollten jedoch:
1. Der Benachrichtigungstext `CONNECTION_LOST_MESSAGE` so angepasst werden, dass er bei bereits geladenen Ansichten (z. B. nach Schreibfehlern oder beim Dashboard-Wechsel) kein automatisches Nachladen verspricht, das nicht stattfindet (Befund 1).
2. Die Testsuite um den Fehlerfall `{code: 3}` ergänzt und der Unlisten-Test über `disconnectedCallback()` abgesichert werden (Befund 2).

ENDE DES REVIEWS
