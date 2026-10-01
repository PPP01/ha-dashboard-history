# Review: Plan zu Issue #49

## Kritisch

### Die zwei Store-Lesungen können Generationen eines `forget` vermischen

**Fundstelle:** Plan, Aufgabe 1 Schritt 7, Zeilen 282 ff.; `custom_components/dashboard_history/operations.py:406-435`; bindende Spec, Entscheidung 24, `docs/superpowers/specs/2026-08-30-dashboard-history-design.md:647-669`; vorhandener Retry-Helfer `operations.py:600-665`.

**Beschreibung:** Der Plan liest zuerst `survey()` und startet danach in einem zweiten Executor-Job `unversioned_counts()`. Beide Ergebnisse werden anschließend gemeinsam zu einer Dashboard-Antwort verbunden. Ein `forget` kann vollständig zwischen den zwei `await`-Punkten laufen. Dann stammen `found.names` und `found.live` noch aus der alten Historiengeneration, die Zähler aber aus dem neuen Index — oder der zweite Read scheitert mit `KeyError` beziehungsweise `MissingCommitError`. Genau diese Mischung fehlerfreier, aber zeitlich verschiedener Antworten verbietet Entscheidung 24 ausdrücklich; sie verlangt eine Wiederholung der ganzen Sequenz einschließlich HEAD- und Checkpoint-Prüfung. Der vorhandene Helfer beschreibt an Zeilen 612-622 exakt diesen Fall für zwei Executor-Aufrufe.

**Konsequenz:** Die Liste kann nach einem `forget` falsche Nullen anzeigen, Einträge aus einer bereits entfernten Historie mitliefern oder als WebSocket-Fehler abbrechen. Die Behauptung des Plans, bei einem während `forget` verlorenen Index komme einfach `{}` zurück, trifft für den vorgeschlagenen Code nicht allgemein zu: `_naming_a_forget_race` übersetzt die Ausnahme nur, es schluckt sie nicht.

**Vorschlag:** `survey()` und `unversioned_counts()` als eine vollständige Versuchseinheit lesen und diese Einheit mit dem vorhandenen asynchronen Rennschutz wiederholen; dabei muss das Ergebnis erst nach unverändertem HEAD und fehlendem Checkpoint verwendet werden. Alternativ gehört ein synchroner kombinierter Store-Read hinter den entsprechenden Store-Retry. Ergänze einen deterministischen Konkurrenztest nach den vorhandenen Mustern in `tests/test_store_concurrency.py`, der den Umbau zwischen den beiden Teilreads erzwingt und nur eine konsistente, neu aufgebaute Antwort akzeptiert.

## Wichtig

### Die Live-Prüfung beweist weder den gelöschten Fall noch einen richtigen Zählerwert

**Fundstelle:** Plan, Aufgabe 1 Schritt 8, Zeilen 311-328; `tests/integration/run_checks.py:532-540` und der vorhandene, tatsächlich gelöschte Prüfdatensatz bei `tests/integration/run_checks.py:747-755`.

**Beschreibung:** Die erste neue Prüfung fordert lediglich einen nichtnegativen Integer. Eine Implementierung, die für jedes lebende Dashboard konstant `0` zurückgibt, besteht sie. Die zweite Prüfung ist an dieser Stelle vakuos, wenn die Testinstanz noch kein gelöschtes Dashboard enthält: `all(...)` über eine leere Menge ist `True`. Das Skript erzeugt und überprüft einen gelöschten Datensatz erst später; der Plan nutzt ihn nicht für die zugesicherte Eigenschaft `unversioned == 0`.

**Konsequenz:** Der Integrationsanteil kann grün sein, obwohl die WebSocket-Verkabelung den errechneten Wert verwirft oder ein gelöschtes Dashboard serverseitig mit einem positiven Wert zurückgibt. Die Panel-Tests decken das nicht ab, weil sie ihre `unversioned`-Werte ausschließlich künstlich in `el._dashboards` einsetzen.

**Vorschlag:** Beim ohnehin erzeugten Löschfall an Zeile 747 zusätzlich `entry["unversioned"] == 0` prüfen. Ergänze einen isolierten End-to-End-Fall mit bekannter Abfolge: Version auf dem neuesten Stand ergibt `0`, ein weiterer aufgezeichneter Stand ergibt `1`, und nach dem Entfernen der Version ergibt sich die erwartete Gesamtzahl. Damit wird auch der Übergang von `HistoryStore.unversioned_counts()` zur WebSocket-Antwort geprüft.

### Der behauptete Zustand »Index nicht gebaut« wird weder getestet noch vom vorgeschlagenen Code geliefert

**Fundstelle:** Plan, Review Focus Zeile 44, Interface Zeile 63, Methode Zeilen 254-263 und Test Zeilen 93-94; `custom_components/dashboard_history/store.py:2665-2706`.

**Beschreibung:** Der einzige vorgeschlagene Test erzeugt gar kein Repository. In einem vorhandenen Repository mit HEAD baut `_revision_index()` den Index dagegen synchron auf; während ein anderer Thread ihn baut, wartet der Aufrufer am `RLock` und erhält anschließend ebenfalls den Index. `None` bedeutet hier praktisch »kein HEAD«, nicht »noch nicht gebaut«. Der Plan nennt daher einen nicht vorhandenen Rückgabestatus und testet den leeren Repository-Fall nicht.

**Konsequenz:** Die Dokumentation der neuen API wäre irreführend. Vor allem bleibt ungetestet, dass ein durch `ensure()` angelegtes, aber noch leeres Repository wie versprochen `{}` liefert.

**Vorschlag:** Beschreibung auf »kein Repository oder kein HEAD« präzisieren und einen separaten Test mit `store.ensure()` ohne Snapshot ergänzen. Falls ein nichtblockierender Aufwärmzustand tatsächlich gewünscht ist, muss er als eigenes, real implementiertes Interface entworfen werden; die aktuelle Index-Synchronisation bietet ihn nicht.

## Hinweis

### Der Cache-Nutzen ist nicht regressionsgesichert

**Fundstelle:** Plan, Aufgabe 1 Schritt 4, Zeilen 184-195, und Schritt 5, Zeilen 215-235; bestehende Kostengrundlage in `custom_components/dashboard_history/store.py:2199-2225`.

**Beschreibung:** Die funktionalen Tests für neue und entfernte Tags beweisen korrekt, dass Ref-Listen nicht an HEAD gecacht werden. Sie beweisen aber nicht die zentrale Performance-Eigenschaft des vorgeschlagenen `_tag_targets`-Caches: dass ein unveränderter annotierter Tag nach dem ersten Aufruf nicht erneut aus dem Objektspeicher gelesen wird. Die Messung in Aufgabe 3 ist nur Bericht und kann deshalb nicht fehlschlagen.

**Konsequenz:** Eine spätere Vereinfachung, die alle Tag-Objekte bei jedem Listenaufruf lädt, würde die Tests bestehen, aber bei vielen automatischen Versionen den im Plan ausdrücklich vermiedenen Aufwand zurückbringen.

**Vorschlag:** Einen kleinen HA-freien Test ergänzen, der nach dem ersten Aufruf die Objektauflösung beobachtet und beim zweiten Aufruf mit unveränderten Refs keine erneute Auflösung derselben Tag-SHA zulässt. Die temporäre Dulwich-Prüfung dieses Reviews bestätigt die zugrunde gelegte Form: `as_dict(b"refs/tags")` liefert etwa `home/v1.0.0` als relativen Ref-Namen und dessen `bytes`-SHA; ein erzeugter annotierter Tag besitzt `object[1]` als Commit-SHA. Die vorgesehene Ref-Aufspaltung ist damit für diesen normalen Fall korrekt.

### Panel-Schnittstelle und CSS-Reihenfolge sind ansonsten nachvollziehbar

**Fundstelle:** Plan, Aufgabe 2, Zeilen 372-470; `custom_components/dashboard_history/panel.js:3203-3210`, `panel.js:3250-3287`, `custom_components/dashboard_history/panel/style.js:385-414`, `tests/test_panel_assets.py:38-72`.

**Beschreibung:** `_renderDashboard()` ist tatsächlich der einzige Renderer für die drei Seitengruppen; dadurch erreichen die vorgesehenen Klassen Simple und Advanced. Die Selektor-Spezifität von `.dash[aria-current="true"]` und `.dash.untidy` ist gleich, sodass die nachgestellte orange Regel gewinnt. Die vorgeschlagenen CSS-Kommentare enthalten weder Backticks noch `${`, und verletzen damit die Asset-Wächter nicht.

**Konsequenz:** Für den normalen Browserpfad besteht hier kein Widerspruch zwischen Plan, Code und den harten Regeln. Der manuelle Schmalfenster-Check bleibt dennoch sinnvoll, da die automatischen Tests keinen Zeilenumbruch eines langen Dashboard-Titels mit Chip messen.

**Vorschlag:** Die Umsetzung kann den Panel-Teil wie beschrieben beibehalten; optional einen Browser-/Layout-Test ergänzen, falls die Anforderung »Chip bricht die Zeile nicht um« verbindlich statt nur manuell geprüft sein soll.

## Urteil

Der Plan ist **umsetzbar nach Korrekturen**. Die Ref- und Panel-Annahmen sind überwiegend belastbar und die harten Regeln zu Home-Assistant-freiem Store, Executor, Dulwich, CSS-Template und Komplexitätsprüfung sind berücksichtigt. Vor der Umsetzung muss jedoch die durch zwei getrennte Store-Reads eingeführte `forget`-Rennbedingung nach der bindenden Entscheidung 24 geschlossen und mit einem Test abgesichert werden; danach sollten die Live-Prüfungen echte Zählerwerte und den nichtvakuosen Löschfall nachweisen.

ENDE DES REVIEWS
