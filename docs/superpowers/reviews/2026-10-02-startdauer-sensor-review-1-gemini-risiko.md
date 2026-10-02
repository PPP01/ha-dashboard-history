# Review: Risiko-Analyse zur Startdauer und Indexbauzeit

Geprüft gegen Arbeitsbaum/`main` bei `5004421` und den Plan `docs/superpowers/plans/2026-10-02-startdauer-sensor.md`.

## 1. Aussagen zu den beiden Teilen der Frage

- **Teil 1 (Fremde Zahl): Trifft zu.** Der Coordinator kann nach dem Plan eine Startdauer oder Indexbauzeit übernehmen, die nicht zu diesem Start gehört.
- **Teil 2 (Keine obere Grenze): Trifft zu.** Der Coordinator kann die Startdauer setzen, bevor der Revisionsindex für den aktuellen HEAD tatsächlich verfügbar ist; die Zahl ist in mehreren regulären Szenarien keine obere Grenze für die Wartezeit des Panels.

---

## 2. Begründung und Ablauf der Ereignisse

### Zu Teil 1: Übernahme einer fremden Zahl

#### Szenario A: Konkurrierendes `forget` während des Opening pass
1. `async_setup_entry` (`custom_components/dashboard_history/__init__.py:43`) registriert die WebSocket-API (`websocket_api.async_register(hass)`), bevor der Hintergrund-Task `_async_open` gestartet wird (`__init__.py:87`).
2. Während `capture.async_opening_pass()` im Hintergrund läuft, wird per WebSocket ein administratives `forget` (`operations.async_forget`, `custom_components/dashboard_history/operations.py:1785` → `store.forget`, `custom_components/dashboard_history/store.py:1746`) aufgerufen.
3. `store.forget` erwirbt `self._lock` (`store.py:1792`), setzt `self._index = None` (`store.py:1808`) und schreibt die Historie um.
4. Ein nachfolgender Dashboard-Schritt im Pass (oder das Panel) ruft `_has_history` → `list_changes` → `_revision_index` (`store.py:2734`) auf. Da `self._index is None` ist, wird `_timed_build` erneut ausgeführt.
5. `self._last_index_build` wird überschrieben mit der Dauer des Indexbaus auf der durch `forget` neu geschriebenen Historie.
6. Ein Schreibvorgang des Passes (`_write_one` → `write_snapshot`, `store.py:1286`) blockiert währenddessen an `self._lock`, wodurch die gesamte Rewrite-Dauer (typischerweise 15–25 Sekunden) in `time.monotonic() - started` einfließt.
7. Am Ende des Passes (`__init__.py:349–350` im Plan) übernimmt der Coordinator im `else`-Zweig `coordinator.startup_seconds` (durch `forget` massiv aufgebläht) und `coordinator.startup_index_seconds = store.last_index_build()` (die Bauzeit nach dem `forget`).
8. Diese Werte gehören zu einer administrativen Historien-Bereinigung und nicht zu den Kosten dieses Starts – ein Widerspruch zur Annahme des Plans (`coordinator.py:282–284`: »a forget that rewrites the history rebuilds the index later, and that is not this start's cost«).

#### Szenario B: Paralleler Indexbau durch das Panel vor Schreibvorgängen des Passes
1. Öffnet ein Anwender oder ein noch geöffneter Tab beim Start sofort das Panel, sendet das Frontend eine WebSocket-Anfrage nach den Dashboards.
2. `operations.async_dashboards` (`operations.py:418`) ruft `store.dashboard_listing()` auf, was über `store.survey()` (`store.py:3432`) `_revision_index()` ausführt.
3. Befindet sich `_async_open` zu diesem Zeitpunkt noch in `repair_pending_forget` (`__init__.py:127`) oder `_async_read` (`custom_components/dashboard_history/capture.py:169`), findet das Panel `_index is None` vor und baut den Index via `_timed_build` (`store.py:2734`).
4. `self._last_index_build` wird durch das Panel gesetzt.
5. Schreibt der Opening pass anschließend noch Änderungen (siehe Teil 2), veraltet dieser Index sofort wieder; der im Coordinator gespeicherte Wert `startup_index_seconds` gehört zu einem Stand vor dem Pass.

---

### Zu Teil 2: Keine obere Grenze für die Wartezeit des Panels

#### Szenario A: Schreibvorgänge des Passes verschieben HEAD nach dem Indexaufruf
1. In `capture.py:358` ruft `_write_one` für ein Dashboard `self._has_history(name)` auf. Dies fragt `list_changes` ab und nutzt `_revision_index(repo)` (`store.py:2695`).
2. Erst in Zeile 369 ruft `_write_one` `store.write_snapshot(...)` auf. Bei geänderter Konfiguration committet `porcelain.commit` (`store.py:1314`) und HEAD zieht weiter.
3. Nach dem letzten Schreibvorgang des Passes (oder wenn nur ein Dashboard geändert wird) erfolgt bis zum Ende von `async_opening_pass()` kein weiterer Aufruf von `_revision_index`.
4. Am Messpunkt nach `await capture.async_opening_pass()` (`__init__.py:349–350` im Plan) zeigt `self._index.head` daher noch auf den alten Stand vor dem letzten Commit. Der Revisionsindex für den aktuellen HEAD ist im Speicher nicht verfügbar.
5. Öffnet das Panel anschließend die Historie, muss `store.dashboard_listing()` → `_revision_index()` den Index erst via `_extended_index` (`store.py:2732`) auf den neuen HEAD verlängern (oder bei Fehlschlag neu bauen). Diese Wartezeit fällt erst nach der gesetzten Startdauer an.

#### Szenario B: Erststart auf einem frischen Repository (ein Dashboard)
1. Bei einer Neuinstallation oder einem leeren Repository ist HEAD vor dem Pass ungeboren (`_resolve(repo, "HEAD") is None`, `store.py:2719`).
2. `_write_one` ruft `_has_history` auf. Da `head is None` ist, liefert `_revision_index` direkt `None` zurück (`store.py:2720`). `_timed_build` wird **nicht aufgerufen**, `self._last_index_build` bleibt `None`.
3. `write_snapshot` committet den ersten Stand und erzeugt HEAD.
4. Der Pass endet.
5. `_async_open` setzt `coordinator.startup_seconds` auf die reine Schreibdauer (wenige Millisekunden) und `coordinator.startup_index_seconds` auf `None`.
6. Ein Index für den aktuellen HEAD wurde **nie gebaut**.
7. Öffnet das Panel die Übersicht, blockiert es auf dem vollständigen Indexbau (`_timed_build`). Die Startdauer des Sensors war **keine obere Grenze** für die Wartezeit des Panels.

#### Szenario C: Pässe, in denen `_has_history` nie aufgerufen wird
1. Schlägt `_async_read` fehl (z. B. wenn `async_get_all_configs` eine Ausnahme wirft, die in `capture.py:182–186` abgefangen wird), liefert `_async_read` `None` und `async_capture` bricht mit `[]` ab.
2. Ebenso wenn keine Dashboards vorhanden sind (`configs` ist leer) oder alle Dashboards unsichere Schlüssel haben (`capture.py:202`).
3. In diesen Fällen wird die Schleife über `configs` übersprungen; `_write_one` und `_has_history` werden 0-mal aufgerufen.
4. `async_opening_pass()` kehrt regulär ohne Exception zurück und betritt den `else`-Zweig nach wenigen Millisekunden.
5. War die Historie bereits gefüllt, ist `self._index` weiterhin `None`.
6. Das Panel muss beim Laden den vollen Indexbau abwarten. Die Startdauer ist keine obere Grenze.

---

## 3. Die kleinste Änderung am Plan, die es behebt

In Task 2, Schritt 5 des Plans (`docs/superpowers/plans/2026-10-02-startdauer-sensor.md` bzw. `custom_components/dashboard_history/__init__.py`), den Index vor dem Zeitstoppen explizit über `store.survey` auf den aktuellen HEAD bringen:

In `_async_open`:
```python
    try:
        await capture.async_opening_pass()
        await hass.async_add_executor_job(store.survey)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
    else:
        coordinator.startup_seconds = time.monotonic() - started
        coordinator.startup_index_seconds = store.last_index_build()
```

### Warum dies beide Probleme löst:
1. `store.survey()` (`store.py:3404`) ruft `_revision_index(repo)` für den tatsächlich aktuellen HEAD auf.
2. Wurde durch Schreibvorgänge des Passes ein neuer HEAD erzeugt, verlängert `survey` den Index via `_extended_index` (`store.py:2732`) auf diesen HEAD und wärmt den Survey-Cache (`store.py:3426`).
3. War es ein Erststart oder wurde `_has_history` nicht aufgerufen, führt `survey` den erforderlichen `_timed_build` (`store.py:2734`) durch. `_last_index_build` erhält den echten Messwert statt `None`.
4. Die Startdauer wird erst gestoppt, wenn der Index für den aktuellen HEAD fertig im Speicher liegt. Wenn das Panel unmittelbar danach `dashboard_listing()` aufruft, wird das Ergebnis ohne weiteren Indexbau direkt aus dem Cache geliefert. `startup_seconds` ist damit eine echte obere Grenze.
5. Schlägt `survey` fehl, greift das `except` und der `else`-Zweig wird nicht betreten (Review Focus 4 gewahrt).

ENDE DES REVIEWS
