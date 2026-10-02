# Review: Startdauer als Diagnose-Sensor (Implementierungsplan)

**Datum:** 2026-10-02  
**Gegenstand:** Implementierungsplan `docs/superpowers/plans/2026-10-02-startdauer-sensor.md`  
**Bezugsstand:** Commit `5004421` auf Branch `startup-duration-sensor`  
**Reviewer:** Unabhängiges Review (Gemini)  

---

## Befunde

### Hoch

#### Befund 1: Bei fehlgeschlagenem `store.ensure` oder Schreibfehlern zeigt der Sensor eine Startdauer statt `unknown`
- **Fundstelle:** Plan Zeile 32 (Review Focus Punkt 4), Zeilen 331–352 (`__init__.py:131-135`) im Vergleich zu `custom_components/dashboard_history/capture.py:240-246` und `custom_components/dashboard_history/__init__.py:66-74`.
- **Beschreibung:** Review Focus Punkt 4 behauptet:
  > »Ein Opening pass, der mit einer Ausnahme endet, setzt keine Zahl – der Sensor bleibt unknown, statt die Dauer eines Starts zu nennen, der nicht fertig wurde (try/except/else, Task 2).«
  
  Tatsächlich fängt `capture.py` (`_async_write`) Fehler beim Schreiben einzelner Dashboards mit `try: ... except Exception: _LOGGER.exception(...); continue` ab. Wenn `store.ensure()` in `async_setup_entry` fehlschlägt (z. B. fehlende Dateisystemberechtigungen für den Konfigurationsordner oder volle Festplatte), wird der Fehler geloggt, aber der Hintergrund-Task `_async_open` trotzdem gestartet. In `_async_open` ruft `capture.async_opening_pass()` dann `_async_write()` auf, wo alle Schreibversuche scheitern und geschluckt werden. `capture.async_opening_pass()` endet somit **ohne Exception** erfolgreich.
  
  Dadurch wird in `_async_open` der `else:`-Block ausgeführt:
  ```python
  coordinator.startup_seconds = time.monotonic() - started
  coordinator.startup_index_seconds = store.last_index_build()
  ```
- **Konsequenz:** Bei einer unbenutzbaren Integration (kein Repository, keine Schreibmöglichkeit) zeigt der Sensor `Startup time` eine scheinbar erfolgreiche Startdauer von wenigen Millisekunden (z. B. `0.0 s` oder `0.1 s`) und den Zustand `available: true`. Der Sensor spiegelt damit vor, die Historie sei nutzbar, obwohl sie funktionsunfähig ist.
- **Vorschlag:** In `_async_open` vor dem Setzen der Startdauer prüfen, ob das Repository überhaupt existiert und einsatzbereit ist:
  ```python
  else:
      if store._repo() is not None:
          coordinator.startup_seconds = time.monotonic() - started
          coordinator.startup_index_seconds = store.last_index_build()
  ```
  Oder in `async_setup_entry` bei einem Fehlschlag von `store.ensure` ein Flag setzen bzw. den Hintergrund-Task gar nicht erst starten.

---

#### Befund 2: Randfall Neuinstallation mit genau einem Dashboard setzt `index_build` fälschlich dauerhaft auf `null`
- **Fundstelle:** Plan Zeile 15 (Abschnitt »Warum dieser Messpunkt«), Zeilen 33–34 (Review Focus Punkt 5) im Vergleich zu `custom_components/dashboard_history/store.py:2718-2720` und `custom_components/dashboard_history/capture.py:358-371`.
- **Beschreibung:** Die Kernbegründung des Plans lautet:
  > »Der Opening pass baut den Index selbst: `_write_one` ruft für jedes Dashboard `_has_history` auf, das geht über `list_changes(name, limit=1)` in `_revision_index`. Der erste Aufruf baut voll...«
  
  Dies gilt für bestehende Repositories und Neuinstallationen mit mehreren Dashboards, jedoch **nicht** für eine Neuinstallation mit genau einem Dashboard (der Standardzustand bei frischem Home Assistant mit nur dem Default-Lovelace-Dashboard):
  1. Beim Start ist das Repository noch leer. HEAD existiert nicht (`_resolve(repo, "HEAD")` ist `None`).
  2. Vor dem ersten Schreiben ruft `_write_one` für das einzige Dashboard `_has_history` auf. In `store.py:2718-2720` gibt `_revision_index` sofort `None` zurück, da `head is None` ist. `_timed_build` wird **nicht** aufgerufen!
  3. `_write_one` schreibt den ersten Snapshot. HEAD wird erzeugt.
  4. Da es kein zweites Dashboard gibt, endet der Opening pass hier. `_timed_build` lief kein einziges Mal.
  5. `_async_open` liest `store.last_index_build()` aus, was `None` ist, und speichert dies im Coordinator.
  6. Erst bei der nachfolgenden ersten Messung (`store.measure()`) oder beim ersten Öffnen des Panels wird der Index gebaut. Zu diesem Zeitpunkt ist `coordinator.startup_index_seconds` jedoch bereits unveränderlich auf `None` fixiert.
- **Konsequenz:** Nach der Ersteinrichtung mit einem Dashboard zeigt der Sensor dauerhaft das Attribut `index_build: null` (und der Diagnosebericht `index_build: null`), obwohl ein Dashboard vorhanden ist und ein Indexbau stattfand. Zudem trifft die Annahme, dass das Panel nach dem Pass nie auf den Indexbau warten muss, für diesen Fall nicht zu.
- **Vorschlag:** Nach dem Schreiben der Snapshots im Opening pass (oder vor dem Auslesen von `store.last_index_build()`) sicherstellen, dass bei existierendem HEAD der Index initialisiert ist, falls noch kein Bau stattfand:
  ```python
  else:
      if store.last_index_build() is None and (store.path / ".git").exists():
          # Build index once if HEAD was created during this pass
          store.survey()
      coordinator.startup_seconds = time.monotonic() - started
      coordinator.startup_index_seconds = store.last_index_build()
  ```

---

### Mittel

#### Befund 3: Veraltete Block-Prüfung und fehlende Prüfung von `schema == 2` in `run_checks.py`
- **Fundstelle:** Plan Zeile 682 (Task 3 Step 5) im Vergleich zu `tests/integration/run_checks.py:5061-5064`.
- **Beschreibung:** In `tests/test_report.py` ersetzt Task 3 den Check `test_the_four_blocks_are_all_there` vorbildlich durch `test_the_blocks_are_all_there` und prüft `schema == 2` sowie alle acht Top-Level-Schlüssel.
  In `tests/integration/run_checks.py` (Zeile 5061) lässt der Plan die alte Prüfung jedoch unverändert stehen:
  ```python
  check(
      "the report carries all four blocks",
      {"environment", "settings", "totals", "dashboards"} <= set(body),
      f"got {sorted(body)}",
  )
  ```
  In Task 3 Step 5 greppt der Plan in Zeile 682 sogar explizit nach `"four blocks"`.
  Zudem wird an keiner Stelle in `run_checks.py` geprüft, ob `body.get("schema") == 2` ist.
- **Konsequenz:** Der Integrationstest gegen die reale HA-Instanz validiert den Berichtsvertrag nur unvollständig: Weder wird geprüft, ob `startup` als Strukturblock vorhanden ist, noch ob `schema` korrekt auf 2 angehoben wurde.
- **Vorschlag:** In `tests/integration/run_checks.py` den Check auf fünf Blöcke anpassen und `schema` prüfen:
  ```python
  check(
      "the report carries all five blocks and schema 2",
      {"environment", "settings", "startup", "totals", "dashboards"} <= set(body)
      and body.get("schema") == 2,
      f"got {sorted(body)} schema={body.get('schema')}",
  )
  ```

---

#### Befund 4: Keine Prüfung von `index_build` im Diagnosebericht gegen den Sensor in `run_checks.py`
- **Fundstelle:** Plan Zeilen 668–678 (Task 3 Step 5).
- **Beschreibung:** Task 3 Step 5 fügt in `run_checks.py` folgende Prüfung ein:
  ```python
  check(
      "the report carries the startup time the sensor shows",
      startup_state is not None
      and body.get("startup", {}).get("seconds") == startup_state,
      f'report={body.get("startup")} sensor={startup_state}',
  )
  ```
  Hier wird ausschließlich `seconds` verglichen. Das Feld `index_build` im Bericht wird nicht gegen das Sensor-Attribut `index_build` abgeglichen.
- **Konsequenz:** Sollte `coordinator.startup_index_seconds` in `diagnostics.py` oder `report.py` fehlerhaft weitergereicht, gerundet oder verloren werden, bleibt das im Container-Integrationstest unbemerkt.
- **Vorschlag:** In `run_checks.py` auch das Attribut `index_build` vergleichen:
  ```python
  startup_index = (
      _seconds(entity_attributes(access, startup_entity).get("index_build"))
      if startup_entity
      else None
  )
  check(
      "the report carries the startup index time the sensor shows",
      body.get("startup", {}).get("index_build") == startup_index,
      f'report={body.get("startup")} sensor={startup_index}',
  )
  ```

---

### Niedrig

#### Befund 5: Spezifikation der Feldregeln für `startup` im Berichtsvertrag nicht tabellarisch nachgeführt
- **Fundstelle:** Plan Zeilen 726–734 (Task 4 Step 2) im Vergleich zu `docs/superpowers/specs/2026-09-19-beobachten-design.md:322-333`.
- **Beschreibung:** Die Spezifikation `2026-09-19-beobachten-design.md` führt im Abschnitt »Der Vertrag des Berichts« eine verbindliche Tabelle von Regeln für jedes Feld (`schema`, `measured_at`, `stale`, `bytes_*`, Datumsformate). Der Plan ergänzt am Dateiende einen Nachtrag in Prosa, aktualisiert jedoch die formale Tabelle der Feldregeln nicht explizit für `startup.seconds` und `startup.index_build` (Typ `float | null`, Rundung auf 0.1, Einheit Sekunden, Wertebereich $\ge 0$).
- **Konsequenz:** Die Spezifikation für den Block `startup` bleibt an dieser Stelle etwas vager als für die übrigen Felder des Berichts.
- **Vorschlag:** Im Nachtrag zu `2026-09-19-beobachten-design.md` eine entsprechende Regelzeile für `startup.seconds` und `startup.index_build` analog zur Tabelle in B10 ergänzen.

---

#### Befund 6: Zählung der erwarteten roten Checks in Task 2 Step 3 unpräzise
- **Fundstelle:** Plan Zeilen 269–270 (Task 2 Step 3).
- **Beschreibung:** Der Plan gibt als erwartetes Ergebnis an:
  > »Expected: `all six readings are registered`, beide `startup time`-Checks und `a reload leaves exactly the six readings` FAIL (es gibt den Sensor noch nicht); sonst gegenüber Step 1 nichts neu rot.«
  
  Da `check_startup_time` pro Aufruf zwei separate `check()`-Aufrufe ausführt (`the startup time is a number of seconds` und `the index build fits inside the startup time`) und zweimal aufgerufen wird (beim Start und beim Reload), schlagen tatsächlich **vier** Checks mit `startup time`/`index build` fehl, plus die beiden Mengenprüfungen (`all six readings` und `a reload leaves exactly the six readings`). Insgesamt schlagen 6 Checks fehl.
- **Konsequenz:** Ein Umsetzer könnte irritiert sein, wenn 6 statt 4 neue FAIL-Zeilen im Output erscheinen.
- **Vorschlag:** Im Text präzisieren: »die vier Checks aus den beiden `check_startup_time`-Aufrufen«.

---

## Prüfpunkte im Detail

### 1. Korrektheit gegenüber dem bestehenden Code
- **Stellen und Zitate:** Alle im Plan genannten Fundstellen (`capture.py:358`, `store.py:688, 2695, 2738-2757`, `__init__.py:131-135`, `sensor.py:131-137`, `report.py:25, 90-97`, `diagnostics.py:39-54`, `tests/test_report.py:31-43`) wurden am Code verifiziert. Sie stimmen wörtlich mit dem Quelltext überein.
- **Imports und APIs:**
  - `time.monotonic()` in `__init__.py` und `store.py` ist sauber. `import time` ist in `store.py` bereits vorhanden, der Plan fügt es in `__init__.py` korrekt hinzu.
  - `UnitOfTime.SECONDS` und `SensorDeviceClass.DURATION` sind Standard-APIs von Home Assistant (ab 2024.11 und in 2026.8.3 voll unterstützt).
  - `CoordinatorEntity[MeasurementCoordinator]` mit überschriebenem `available = True` und `extra_state_attributes` ist typkonform und funktionsfähig.
  - `_device_info(entry)` eliminiert Redundanz bei der Gerätezuordnung in `sensor.py`.
- **Ratchet und Linter:**
  - `python3 tools/complexity_ratchet.py` bleibt grün (keine Funktion überschreitet Schwellenwerte).
  - `lint-imports` bleibt grün (`store.py` und `report.py` bleiben vollständig frei von `homeassistant`).

### 2. Innere Konsistenz
- Die Namen und Typen (`HistoryStore.last_index_build() -> float | None`, `coordinator.startup_seconds`, `coordinator.startup_index_seconds`, `report.build(..., startup_seconds=..., startup_index_seconds=...)`) passen nahtlos zusammen.
- Die Tests in Task 1 Step 2 und Task 3 Step 2 werden exakt aus dem im Plan angegebenen Grund rot (`AttributeError` bzw. `TypeError`).

### 3. Vollständigkeit
- Es gibt keine vergessenen Aufrufstellen von `report.build`. Alle vier Vorkommen im Repository (`diagnostics.py` sowie dreimal in `tests/test_report.py`) werden im Plan aktualisiert.
- `strings.json` und `translations/en.json` werden synchron geändert, sodass `test_the_english_translation_is_the_strings_file` grün bleibt.
- Lücke: In `tests/integration/run_checks.py` wird der Wechsel auf Schema 2 und der neue Block `startup` im bestehenden Block-Check nicht abgeprüft (siehe Befunde 3 und 4).

### 4. Messpunkt-Tragfähigkeit
- Für den Normalfall mit bestehender Historie ist die Begründung tragfähig: Der Opening pass führt `_has_history` aus, was `_revision_index` anstößt und den Index vollständig baut. Da das Panel für `dashboard_listing()` diesen Index benötigt, ist das Ende des Opening pass eine obere Grenze dafür, ab wann das Panel seine Liste zeigen kann.
- Für Randfälle (Neuinstallation mit 1 Dashboard, fehlgeschlagenes `store.ensure`) bricht die Annahme jedoch ein (siehe Befunde 1 und 2).

### 5. Ausführbarkeit der Container-Schritte
- Die Docker- und `run_checks.py`-Befehle entsprechen exakt dem im Projekt etablierten Ablauf (`docker/README.md`, `CLAUDE.md`).
- Die Git-Commit-Botschaften folgen strikt den Projektkonventionen (Präfix `[52] `, Imperativ, max. 50 Zeichen Subject, Zeilenumbruch bei 72 Zeichen im Body).

---

## Gesamturteil

Umsetzbar nach Korrekturen.

ENDE DES REVIEWS
