# Prüfung der Startmessung und ihrer Nebenläufigkeit

Bezugsstand: `5004421`; geprüft wurde der uncommittete Plan im Arbeitsbaum. Codepfade beziehen sich auf `custom_components/dashboard_history/`, Planstellen auf `docs/superpowers/plans/2026-10-02-startdauer-sensor.md`.

## 1. Fremde Zahl: Trifft zu für einen anderen Indexbau; trifft nicht zu für einen früheren Start

`startup_seconds` kommt tatsächlich aus diesem Setup. `async_setup_entry()` erzeugt jedes Mal einen neuen Store und Coordinator (`__init__.py:28–31`); der Plan erzeugt die lokale Zeitmarke und übergibt genau diese Objekte an `_async_open` (Plan:299–324). `_last_index_build` beginnt je Store mit `None` (Plan:94–100). Geteilt wird zwischen Storeinstanzen die Schreibsperre, nicht dieses Feld (`store.py:166–175`, `642–688`). Ein noch laufender Executor des alten Starts schreibt damit nicht in den neuen Coordinator oder dessen Store.

Die Indexbauzeit ist dagegen lediglich die Dauer des **zuletzt abgeschlossenen vollständigen Baus dieser Storeinstanz** (Plan:119–120, 133–135). Sie ist weder an den ersten Startbau noch an einen HEAD oder den Abschluss des Opening pass gebunden. Die Kopie im Coordinator verhindert Änderungen erst **nach** Plan:350. Die Zusage aus Plan:30 und 282–284, ein durch `forget` ausgelöster Neubau werde nicht als Startbau übernommen, gilt vor dieser Zeile nicht.

Eine mögliche Abfolge:

1. Das Panel oder `_has_history()` baut den kalten Index A; der geplante `_timed_build()` speichert dessen Dauer `a`.
2. Der letzte `_write_one()` des Passes endet im Executor. Seine Rückkehr in den Event-Loop steht noch aus. Die Schreibsperre ist bereits freigegeben (`store.py:1286–1320`; `capture.py:241–243`).
3. Ein bereits laufender `forget`-Auftrag bekommt die Schreibsperre, verwirft den Index und schreibt HEAD um (`store.py:1792–1811`, `2066–2069`). Anschließend baut ein Panel-Leser über `dashboard_listing()` → `survey()` einen neuen Index B (`operations.py:418`; `store.py:3608–3609`, `3432`). `_last_index_build` wird `b`.
4. Der Opening-Task wird fortgesetzt und kopiert `b` statt `a` (Plan:349–350). Dafür ist kein `await` zwischen den beiden Zuweisungen nötig: Das mögliche Überholen liegt schon vor der Fortsetzung, und Executor-Threads laufen außerdem unabhängig vom Event-Loop.

Das ist keine Vermischung zweier Reloads: B wurde während der Lebensdauer des neuen Stores gebaut. Es ist eine Vermischung des anfänglichen Indexbaus mit der Wartungsoperation, die der Plan ausdrücklich ausschließen will. Würde der Vertrag stattdessen bewusst »letzter vollständiger Bau vor dem Messabschluss« lauten, wäre `b` vertragsgemäß; den ersten oder gesamten Indexaufwand dieses Starts misst es dann allerdings nicht.

Ein parallel vom Panel gestarteter **erster** Bau ist für sich genommen unproblematisch und gehört zu diesem Start. `_index_gate` serialisiert die vollständigen Bauten und Erweiterungen derselben Instanz (`store.py:2724–2735`). Ein späteres `_has_history()` wartet gegebenenfalls darauf. Das gilt aber nur, wenn es tatsächlich noch einen solchen Aufruf gibt und dieser einen Index benötigt.

`repair_pending_forget()` wird im vorhandenen Produktivpfad ausdrücklich **vor** dem Opening pass awaited (`__init__.py:126–132`); ein zweiter, nach dem Pass gestarteter Reparaturauftrag derselben Instanz ist im Code nicht vorhanden. Ein früher Panel-Bau kann allerdings schon vor bzw. während dieser Reparatur stattfinden: Das Panel ist vor dem Hintergrundtask registriert (`__init__.py:42–44`, `87–91`), und Reparatur und Leser teilen nicht `_index_gate`. Die Reparatur verwirft den Cache und schreibt HEAD um (`store.py:1899`, `1941–1944`). Ein anschließend nötiger zweiter Bau ist dann realer Aufwand dieses Starts; das einzelne Feld hält nur den letzten, nicht die Summe beider Bauten.

## 2. Keine obere Grenze: Trifft zu

Schon ohne konkurrierendes `forget` stimmt die Voraussetzung aus Plan:15 und 345–348 nicht.

**Letzter Schreibvorgang des Passes:** `_write_one()` ruft `_has_history()` **vor** `write_snapshot()` auf (`capture.py:358`, `369–374`). Damit ist der Index zunächst für H0 verfügbar. `write_snapshot()` schreibt danach H1, aktualisiert den Revisionsindex aber nicht (`store.py:1286–1320`). Nach dem letzten Dashboard folgt im Pass kein obligatorischer Indexaufruf (`capture.py:239–277`, `95–114`). Der Coordinator setzt die Startzeit, obwohl `_index.head` noch H0 ist. Erst der nächste Leser verlängert über `_revision_index()` → `_extended_index()` auf H1 (`store.py:2718–2735`). Das im Plan erwähnte Experiment »zweiter Schreibvorgang **und `survey()`**« enthält genau den zusätzlichen Aufruf, der im Opening pass fehlt.

**Frischer Store mit genau einem Dashboard:** Vor dem ersten Schreiben existiert kein HEAD. `_has_history()` erhält eine leere Liste; `_revision_index()` liefert bei fehlendem HEAD `None` (`store.py:2718–2720`). Das anschließende Schreiben erzeugt den ersten Commit, aber keinen Index. Der Pass endet, der Coordinator meldet eine Startdauer und `index_build = None`; ein späteres Panel oder die erste Messung muss den vollständigen Index erst bauen (`store.py:3432`, `3633`).

**Kein `_has_history()`-Aufruf:** Ein Store kann eine lange Historie ausschließlich gelöschter Dashboards enthalten und HA keine aktuelle Dashboard-Konfiguration liefern. Die Löschprüfung fragt nur `list_dashboards()` ab, das den HEAD-Baum liest, aber keinen Revisionsindex baut (`capture.py:323–325`; `store.py:3367–3386`). Die Schleife über Konfigurationen ist leer. Die für das Panel weiterhin wichtige Historie gelöschter Dashboards wird erst beim späteren `survey()` indexiert. Auch ein fehlgeschlagenes Lesen der Konfigurationen kann den Pass ohne `_has_history()` normal beenden (`capture.py:168–185`). Eine wirklich leere Historie **ohne HEAD** ist dagegen kein Gegenbeispiel: Dort muss kein Index gebaut werden, um eine leere Liste zu liefern.

Die ersten drei erfolgreichen Store-Abfolgen wurden in temporären Repositories am unveränderten Code nachgestellt: nach dem ersten `_write_one()` existiert HEAD bei `_index is None`; nach einem weiteren geänderten `_write_one()` ist `_index.head != HEAD`; nach Reload einer ausschließlich gelöschten Historie lässt `list_dashboards()` den Index ungebaut. Erst `survey()` baut bzw. verlängert ihn. Die Methoden `_write_one` und `_has_history` wurden dafür unverändert aus dem Quelltext ausgeführt; dies war kein vollständiger HA-Lauf.

**Rewrite am Passende:** Noch gravierender ist die Abfolge »letztes `_has_history()` fertig → letzter Write fertig → `forget` verwirft Index und verschiebt HEAD → Startwerte werden übernommen«. Es gibt nach dem letzten Write weder eine Sperre gegen `forget` noch eine Bereitschaftsprüfung. Nun kann statt einer kurzen Erweiterung ein voller Neubau fehlen. Läuft dieser gerade im Panel-Executor, wartet der Getter `last_index_build()` nicht darauf.

Dabei ist auch ein gerade gespeicherter Zeitwert kein Bereitschaftsnachweis: Im Plan schreibt `_timed_build()` die Dauer vor Logausgabe und Rückgabe (Plan:119–127); erst anschließend publiziert sein Aufrufer `self._index = found` (`store.py:2735`). Der Event-Loop kann dazwischen bereits den neuen Zeitwert lesen. `_index_warming` hilft ebenfalls nicht: Es wird schon im `finally` vor diesen Schritten gelöscht. Außerdem liest `_revision_index()` HEAD vor dem Erwerb des Gates und prüft unter dem Gate nur gegen diesen lokalen HEAD (`store.py:2718–2729`). Das Gate allein synchronisiert keine HEAD-Änderung durch einen Schreiber.

## Kleinste gezielte Korrektur am Plan

Für die beabsichtigte Aussage »anfänglicher Indexbau dieses Starts« Task 1 auf einen **einmalig gesetzten Wert je Storeinstanz** ändern, beispielsweise `first_index_build()`. Den ersten erfolgreich abgeschlossenen vollen Bau unter `_index_gate` festhalten und bei späteren Bauten nicht überschreiben. Der erste Bau darf vom Panel kommen. Damit entfällt die Übernahme einer späteren `forget`-Bauzeit; der Wert bezeichnet ausdrücklich den ersten Bau, nicht den gesamten Indexaufwand mehrerer Anläufe.

Task 2 braucht nach dem Opening pass einen expliziten Abschluss im Executor. Ein schmaler Store-Helfer soll in **einem** kritischen Abschnitt:

1. `self._lock` und danach `self._index_gate` erwerben. Diese Reihenfolge entspricht dem bestehenden `forget`-Pfad, der unter der Schreibsperre über `list_all_dashboards()` in den Index gelangt (`store.py:1792–1799`, `3400`). Kein Lock-Warten auf dem HA-Event-Loop.
2. Einen noch offenen Forget-Checkpoint verweigern, das Repository prüfen und `_revision_index(repo)` aufrufen. Durch die äußeren Sperren bleibt HEAD während dieses Aufrufs stabil; bestehende Reader-Bauten müssen vorher enden. Bei vorhandenem HEAD muss der gelieferte Index genau diesen HEAD tragen. Ein vorhandenes, noch commitloses Repository ist der erlaubte Fall ohne Index.
3. **Noch unter beiden Sperren** einen unveränderlichen Snapshot aus HEAD, Abschlusszeit `time.monotonic()` und erstem Indexbauwert erzeugen und zurückgeben.

`_async_open` übernimmt ausschließlich diesen Snapshot: `startup_seconds = snapshot.finished_at - started` und `startup_index_seconds = snapshot.index_seconds`. Bei fehlgeschlagenem Abschluss bleiben die Werte `None`. Die Abschlusszeit darf nicht erst nach dem Executor-`await` genommen und der Indexwert nicht separat live gelesen werden. Ein bloßes zusätzliches `await …(store.survey)` schließt die Lücke zu konkurrierenden Schreibern und zur anschließenden Wertübernahme nicht.

Die Behauptung im Plan ist dabei präzise auf den Snapshot zu begrenzen: **Bis zu diesem Zeitpunkt war der Index für den unter Sperre beobachteten HEAD verfügbar.** Eine unmittelbar danach beginnende neue Änderung oder ein neues `forget` kann erneut Arbeit fürs Panel erzeugen, noch bevor der Event-Loop die Werte publiziert. Keine einmalige Startzahl kann eine obere Grenze für beliebige spätere Panel-Aufrufe oder HEADs garantieren. Auch ein fertiger Revisionsindex ist keine Messung der gesamten Panel-Antwort samt den übrigen Arbeiten in `dashboard_listing()` und `async_dashboards()` (`store.py:3608–3609`; `operations.py:418–420`).

ENDE DES REVIEWS
