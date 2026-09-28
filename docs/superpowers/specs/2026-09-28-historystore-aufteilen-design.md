# Design: `HistoryStore` – Invarianten zuerst, der Umbau geparkt

**Datum:** 2026-09-28
**Status:** Entwurf, zweite Fassung. Die erste Fassung (am selben Tag im Dialog abgestimmt) sah nach den Invarianten auch das Herauslösen von `forget` in ein Paket `store/` vor. Auf die Nachfrage des Nutzers, ob ein erfahrener Python-Entwickler das beim aktuellen Stand tun würde, und nach einer zweiten Messung **auf die Invarianten gekürzt**; der Umbau steht vollständig ausgearbeitet, aber geparkt in Abschnitt 3 (siehe »Warum diese Fassung kürzer ist«). Ein Hinweis von Astra zur Reihenfolge danach ist im »Ausblick« eingearbeitet. Terra-, Gemini- und Astra-Review dieser Fassung am 2026-09-28 eingearbeitet (siehe »Abgleich mit den Reviews«); **noch nicht freigegeben**.
**Vorhaben:** kein Buchstabe – drei kleine Commits ohne Produktivcode außer einem Docstring. Der geparkte Umbau bekäme bei seiner Umsetzung den nächsten freien Buchstaben.
**GitHub-Issue:** [#42](https://github.com/PPP01/ha-dashboard-history/issues/42) – bleibt nach dieser Arbeit für den geparkten Umbau offen
**Integration:** `dashboard_history`
**Bindend bei Widerspruch:** die Haupt-Spec (`2026-08-30-dashboard-history-design.md`), insbesondere Entscheidung 21 (ein Lock pro Pfad, Checkpoint, Reparatur), 24 (Lesezugriffe gegen ein gleichzeitiges `forget`) und 25 (Generationszähler)

## Kontext & Ziel

`store.py` ist seit dem 2026-09-01 von 679 auf 3537 Zeilen gewachsen, `HistoryStore` allein hat 79 Methoden. Issue #42 schlägt vor, die Klasse in sechs Verantwortlichkeiten hinter einer Fassade zu zerlegen – und zuerst die Lock-Invarianten festzuhalten, weil der Lock der Teil ist, den eine Aufteilung brechen kann, ohne dass ein Test es merkt.

Ziel ist, wie der Nutzer es gefasst hat, **bessere Codequalität: Änderungen sollen wieder leichter fallen, der Code soll nachvollziehbarer werden.** Das Issue ist Ausgangspunkt, nicht Vorgabe. Die Messungen unten zeigen: Das eigentliche Risiko in `store.py` sind Nebenläufigkeitsregeln, die nur in verstreuter Prosa stehen und zum Teil ungeprüft sind – nicht die Länge der Datei. Diese Arbeit macht die Regeln deshalb **sichtbar und geprüft** und baut sonst nichts um:

1. Ein Abschnitt im Modul-Docstring hält das Nebenläufigkeitsmodell an einer Stelle fest.
2. Ein Wächter macht aus jedem Deadlock durch doppeltes Sperren einen lauten Testfehler, in der ganzen Testsuite.
3. Nebenläufigkeitstests prüfen `forget` gegen jede andere Methode, die den Lock nimmt (außer `ensure`, begründet in Abschnitt 2 b) – mit dem Endzustand, nicht nur mit dem Ausschluss.

Alles **verhaltensneutral**: Am Produktivcode ändert sich nur ein Docstring.

### Verifizierte Ausgangslage (2026-09-28, am Quelltext nachgeprüft)

| Feststellung | Beleg |
|---|---|
| `store.py`: 3537 Zeilen, davon **1566 Code**, 1415 Docstring, 371 Kommentar, 185 leer | AST und `tokenize` über die Datei |
| Nur vier Funktionen reißen eine Komplexitätsgrenze, alle schon in der Baseline mit #42: `_read_checkpoint` (C901 15, PLR0912 15), `survey` (13), `_walked_changes` (12), `_resolve` (11). Keine kommt an `plan_undo` aus P (54) heran | `tools/complexity-baseline.json` |
| Größe der Verantwortlichkeiten in `HistoryStore` (Zeilen je Methode summiert): `forget` samt Checkpoint und Reparatur ~1040, Lesen und Index ~1020, Versionen 365, Messung 267, Aufzeichnen 170, Aufräumen alter Locks 95 | AST-Auswertung |
| Über die ganze Historie: `panel.js` 109 Commits, `store.py` 70, `operations.py` 55. **Fix-artige Commits** (Betreff beginnt mit Fix, Guard, Refuse, Correct, Do not, Stop, Prevent, Repair): `store.py` 15, `panel.js` 10, `operations.py` 8 | `git log --name-only`, `git log -i -E --grep` |
| Der letzte Commit an `store.py` war am 2026-09-22. Die Häufung lag am 20.–22. September und betraf `forget` und Nebenläufigkeit (Entscheidungen 21–25). Nach Commits je Methode vorn: `forget`, `_forget`, `list_changes` (je 8), `_rewrite_tags` (7). Keines der übrigen offenen Issues (#13, #14, #16, #17, #31, #34, #37, #39, #40, #43) betrifft den Store | `git log -p` mit Python-Funktionsköpfen; `gh issue list` |
| Zehn Methoden nehmen den Lock: `ensure`, `write_snapshot`, `mark_deleted`, `create_version`, `retitle_version`, `read_version`, `remove_version`, `set_description`, `forget`, `repair_pending_forget`. `measure`, `survey`, `list_changes`, `read_at` und alle übrigen Lesezugriffe laufen bewusst ohne ihn | Quelltext; bestätigt die Liste in #42 |
| Der Lock ist ein einfacher `threading.Lock` ohne Wiedereintritt, geteilt über `_lock_for` je aufgelöstem Pfad (Entscheidung 21, Korrektur 4). `_tag_at_locked` existiert, um ein doppeltes Sperren zu vermeiden, und sagt das in seinem Docstring | `store.py:80-89`, `:1325-1361` |
| **Die Caches `_index` und `_survey` gehören der Instanz**, nicht dem Pfad. Leser füllen sie ohne Lock; `forget` und `repair_pending_forget` leeren sie unter dem Lock. Beide hängen an HEAD, ein veralteter Eintrag wird beim nächsten Zugriff erkannt | `store.py:510-514`, `:1626-1627`, `:1759-1760`, `:2538-2547`, `:3199-3201` |
| **Der Checkpoint ist ein Signal in zwei Richtungen:** Schreiber verweigern (`_refuse_if_forget_pending`, Entscheidung 21); die Leser mit Retry trauen ihrem Ergebnis nicht, solange er existiert (`forget_in_progress` in `_retrying_a_forget_race`, Entscheidung 24). Auch `_indexed_revisions` und `_walked_changes` lesen Generationszähler und Checkpoint | `store.py:677-697`, `:2355-2435`, `:2466-2473`, `:2668-2675` |
| **Die ungesperrten Leser fallen in drei Gruppen.** Über den Retry aus Entscheidung 24 laufen nur `list_changes` und `search_changes` – Letzteres nur, wenn es die Versionen selbst liest –, eine Ebene höher `operations.async_history` und `operations.async_search`. Kein weggeräumtes Objekt treffen können `list_versions` (überspringt einen verschwundenen Tag) sowie `forget_generation` und `forget_in_progress` (lesen Dateien). Alle übrigen öffentlichen Leser (`survey`, `measure`, `previous_change`, `commit_times`, `commit_order`, `list_dashboards`, `list_all_dashboards`, `matching_revisions`, `same_state`, `resolve`, `read_at`, `read_meta_at`, `descriptions`) fangen ein weggeräumtes Objekt nur an einzelnen Stellen ab, nicht durchgehend: `_resolve` lädt das gerade gefundene Objekt ohne Schutz, `_read_from` den Blob, und der Aufbau des Index läuft ohne Schutz – sie können während eines `forget` weiterhin `KeyError` oder `MissingCommitError` werfen. Jede der 28 öffentlichen Methoden gehört genau einer Gruppe oder den zehn mit Lock an | `store.py:2284`, `:2800`, `operations.py:539`, `:704`; `store.py:2066-2072`; ungeschützt `store.py:2914`, `:2968`, `:2562`; Zuordnung per AST (Terra, Spec- und Plan-Review 2026-09-28) |
| Das Wissen darüber steht verstreut in rund zwanzig Docstrings (u. a. `__init__`, `_clear_stale_locks`, `_clear_stale_object_locks`, `_tag_at_locked`, `read_version`, `_finish_forget`, `_retrying_a_forget_race`, `measure`), nirgends an einer Stelle | Quelltext |
| Der `progress`-Callback von `forget` läuft innerhalb von `with self._lock`, zuerst als `say("rewriting", 0, n)` – nachdem die Caches geleert sind, bevor sich irgendein Ref bewegt und bevor der Checkpoint geschrieben ist | `store.py:1610`, `:1626-1627`, `:1781`, `:1834` |
| Vorhandene Nebenläufigkeitstests: dieselbe Lock-Instanz für zwei Instanzen desselben Pfads (`test_store.py:100`), Reparatur gegen einen gehaltenen Lock in zwei echten Threads (`:104-150`), acht parallele `write_snapshot` (`:434`). Rennen zwischen Lesern und `forget` werden per `monkeypatch` simuliert (Entscheidung 24). **Kein** Test lässt `forget` gegen `write_snapshot`, `mark_deleted`, die Versions-Schreiber oder `set_description` laufen | `test_store.py` |
| `test_store.py` ersetzt 43-mal private Namen per `monkeypatch` (`_each_change` 11, `_rewrite_tags` 10, `_resolve` 7, `_revision_index` 3, `_rewrite_notes` 3, `_read_generation` 3, je 1 `descriptions`, `_garbage_collect_protecting_index`, `_built_index`, `_repo`, `store_module._change`, `store_module.shutil.rmtree`; per AST gezählt – ein zeilenweiser Grep übersieht mehrzeilige Aufrufe und fand in der ersten Fassung nur 38, Gemini 2026-09-28), dazu rund 30 direkte Zugriffe auf Interna. Für diese Arbeit ohne Belang, für den geparkten Umbau entscheidend (Abschnitt 3) | Grep über `tests/` |
| Testsuite: 978 Tests, davon 241 in `test_store.py`. Abdeckung von `store.py` laut #42 90 % Zeilen und Zweige (gemessen 2026-09-27) | `pytest --co`; Issue |

## Nicht-Ziele (YAGNI)

- **Kein Umbau von `store.py`.** Keine Methode wandert, keine wird umbenannt, kein Paket entsteht. Der Zuschnitt dafür ist in Abschnitt 3 ausgearbeitet und geparkt.
- **Keine Verhaltensänderung,** auch keine »offensichtlich richtige«. Findet ein neuer Test einen echten Fehler, wird er ein Issue (siehe »Fehler- und Randfälle«).
- **Keine Kürzung der Prosa.** Die Docstrings bleiben; einzig der neue Abschnitt zum Nebenläufigkeitsmodell kommt dazu, und Docstrings, die dieses Modell heute wiederholen, bekommen höchstens einen Verweis darauf. Ob das Verhältnis von Prosa zu Code (1786 zu 1566 Zeilen) selbst ein Lesbarkeitsproblem ist, ist eine eigene Frage an den Nutzer (Entscheidung 6).
- **Kein Abbau der vier Baseline-Einträge.**
- **Keine Änderung an bestehenden Tests.** Nur neue Tests und eine neue Fixture.

## Entwurf

### 1. Das Nebenläufigkeitsmodell an einer Stelle

Ein Abschnitt »Concurrency« im Modul-Docstring von `store.py` (englisch, wie aller Code), der nur beschreibt, was heute gilt:

1. **Ein Lock pro aufgelöstem Pfad, nicht pro Instanz** (Entscheidung 21, Korrektur 4). Ein einfacher `threading.Lock` ohne Wiedereintritt: Was unter ihm aufgerufen wird, darf ihn nie selbst nehmen – `_tag_at_locked` ist das Beispiel dafür.
2. **Die zehn Methoden, die ihn nehmen,** und was bei jeder zusammen atomar ist. Bei `forget` und `repair_pending_forget`: Checkpoint, Generationszähler, HEAD, Notizen, Tags, Index und Aufräumen in einem kritischen Abschnitt.
3. **Bewusst ohne Lock** laufen alle übrigen Lesezugriffe – ein Sensor soll nie auf ein 15 s langes `forget` warten. `read_version` ist die eine lesende Ausnahme, mit dem Grund aus seinem Docstring. Was das kostet, ist verschieden, und der Abschnitt ordnet **jede** öffentliche Lesemethode genau einer von **drei Gruppen** zu: *konsistent oder verweigert* – `list_changes` und `search_changes` (wo es die Versionen selbst liest) bauen ihre Antwort über den Retry aus Entscheidung 24 neu auf oder werfen nach dem Budget `RuntimeError`; *kann kein weggeräumtes Objekt treffen* – `list_versions`, `forget_generation`, `forget_in_progress`; *Best Effort* – alle übrigen, die ein weggeräumtes Objekt nur an einzelnen Stellen abfangen und während eines `forget` weiterhin `KeyError` oder `MissingCommitError` werfen können, weil `_resolve`, `_read_from` und der Aufbau des Index ungeschützt laden. Die dritte Gruppe ist **nicht** durch Entscheidung 24 abgesichert und wird von keinem Test festgehalten – Best Effort ist alles, was sie verspricht (Terra, Spec-Review und Plan-Review 2026-09-28: die erste Fassung behauptete zwei Gruppen, die zweite ließ die ungeschützten Ladestellen weg).
4. **Caches pro Instanz** (`_index`, `_survey`): an HEAD gebunden, ohne Lock gefüllt, unter dem Lock geleert.
5. **Der Checkpoint als Signal in zwei Richtungen:** Schreiber verweigern; die Leser mit Retry verwerfen ihr Ergebnis, solange er existiert. Die übrigen Leser sehen ihn nicht an.

Jede Regel nennt die Entscheidung der Haupt-Spec, aus der sie stammt, und den Test, der sie prüft – nach dieser Arbeit hat jede einen.

### 2. Die Prüfung

**(a) Ein Wächter gegen doppeltes Sperren in der ganzen Testsuite.** Eine automatisch aktive Fixture in `tests/conftest.py` ersetzt `store._lock_for` durch eine Fabrik, die je aufgelöstem Pfad ein prüfendes Lock-Objekt liefert – ein eigenes Register je Test, dieselbe Identität für denselben Pfad (`test_store.py:100` bleibt grün). Das Objekt unterstützt `with` und `acquire`/`release` wie ein `threading.Lock`, merkt sich den haltenden Thread und wirft `RuntimeError`, wenn derselbe Thread es ein zweites Mal anfordert. Damit prüft jeder der 978 Tests, dass kein Codepfad den Lock doppelt nimmt; ein Deadlock, der sonst die Suite hängen ließe, wird ein lauter Fehler an der richtigen Stelle. Ein eigener kleiner Test belegt beides, was der Wächter kann: dass er bei doppeltem Sperren anschlägt und dass er einen gescheiterten Erwerbsversuch eines zweiten Threads meldet (und bei einem ungehinderten Erwerb nicht). Keine Wirkung außerhalb der Tests.

**Der Wächter hält außerdem fest, wer auf ihn warten musste** (Astra, 2026-09-28). Jede Anforderung versucht den zugrunde liegenden echten Lock zuerst ohne zu blockieren; scheitert das, weil ein anderer Thread ihn hält, vermerkt der Wächter den wartenden Thread und setzt ein `threading.Event` »umkämpft« – erst danach wartet er regulär. Die Fixture gibt den Tests Zugriff auf den Wächter eines Pfads (etwa `lock_guard.for_path(pfad)`), ohne dass sie `store._lock` oder einen anderen privaten Namen von `HistoryStore` anfassen müssen. Das ist die Beobachtung, auf der die Ausschluss-Prüfung in (b) beruht.

Die Fixture patcht `_lock_for` dort, wo `HistoryStore.__init__` es nachschlägt – heute `store._lock_for`. Das wirkt auf jede Instanz, die **während oder nach** dem Aufbau der Fixture entsteht; eine Instanz aus einer breiter gescopten Fixture behielte ihren echten Lock. Heute ist jede `HistoryStore`-Fixture funktionsweit (`test_store.py:28-32`), und die Wächter-Fixture wird so angelegt, dass pytest sie vor jeder anderen Fixture desselben Tests aufbaut (automatisch aktiv, funktionsweit). Eine Instanz mit breiterem Scope bekäme den Wächter nicht – das hält Erfolgskriterium 2 fest. Tests, die keinen `HistoryStore` bauen, bleiben ohne Verhaltenswirkung; importiert wird `store` von der Fixture trotzdem (Terra, 2026-09-28).

**(b) Die fehlenden Nebenläufigkeitstests – das zentrale Sicherheitsnetz.** Alle nach demselben Muster: `forget("gone", progress=…)` läuft in einem Thread und wartet im ersten Aufruf des Callbacks an einem `threading.Event` – es hält damit den Lock, hat die Caches geleert, aber noch keinen Ref bewegt und keinen Checkpoint geschrieben. Ein zweiter Thread startet die Gegenoperation. Jeder Test prüft drei Dinge:

- **Ausschluss, nachweislich:** Bevor der Test `forget` freigibt, wartet er (mit Timeout) darauf, dass der Wächter des Pfads einen **gescheiterten Erwerbsversuch des Gegenoperations-Threads** meldet. Bleibt die Meldung aus, schlägt der Test fehl. Dazu prüft er, dass die Gegenoperation zu diesem Zeitpunkt nicht fertig ist. Ein festes Zeitfenster reicht **nicht**: »nach dem Fenster nicht fertig« unterscheidet Warten auf den Lock nicht von einem Thread, der schlicht noch keine CPU-Zeit bekam – und weil jeder erwartete Endzustand der Tabelle genau der ist, den die Gegenoperation auch nach einem vollständig beendeten `forget` erreicht, bestünde der Test dann auch ohne jeden Ausschluss (Astra, 2026-09-28). Nebenbei wird der Test damit deterministisch: Er wartet auf ein Ereignis, nicht auf eine Uhr.
- **Kein Hängen:** Nach der Freigabe enden beide Threads, geprüft mit `join(timeout=…)`.
- **Der Endzustand ist richtig:**

**Gemeinsamer Aufbau**, damit jede erwartete Antwort zwingend folgt (Terra, 2026-09-28): `home` wird gespeichert, dann `gone`, dann `home` noch einmal mit neuem Inhalt (`home_v2`). `home_v2` trägt damit `gone.yaml` in seinem Baum und bekommt durch `forget("gone")` eine neue Sha – die alte Sha von `home_v2` ist die **weggeräumte Revision** der Tabelle. Eine Revision vor dem ersten Commit von `gone` taugt dafür nicht: `forget` baut sie mit gleichem Baum, gleichen Eltern und gleicher Nachricht neu, und ihre inhaltsadressierte Sha bleibt dieselbe. Vor `forget` wird eine annotierte Version `gone/v1.0.0` auf den Commit von `gone` gesetzt und eine annotierte Version `home/v1.0.0` auf `home_v2`. Jeder Test weist nach dem `forget` zuerst seine Vorbedingung nach – etwa `resolve(alte Sha von home_v2) is None` –, bevor er den Endzustand prüft.

| Gegenoperation, hinter `forget("gone")` eingereiht | erwarteter Endzustand |
|---|---|
| `write_snapshot` eines anderen Dashboards mit einem Inhalt, der sich vom Stand in HEAD sicher unterscheidet | Rückgabe `is not None`; der Commit sitzt auf dem umgeschriebenen HEAD; `gone` steht nicht in `list_all_dashboards()`, und seine Dateien kehren nicht über den Index in HEAD zurück |
| `mark_deleted("gone")` | `None`, kein neuer Commit |
| `create_version` unter einem frischen, nicht kollidierenden Namen (etwa `home/v9.0.0`) auf der weggeräumten Revision | `ValueError` mit dem Text »unknown revision …«, nicht der einer Namenskollision; kein Tag unter diesem Namen |
| `retitle_version("gone", "gone/v1.0.0", …)` | `ValueError` »unknown version …« |
| `remove_version("gone", "gone/v1.0.0")` | `ValueError` »unknown version …«; `gone/v1.0.0` existiert nicht |
| `set_description` auf der weggeräumten Revision | `False`, keine Notiz auf irgendeinem Commit mit diesem Text |
| `read_version("home", "home/v1.0.0")` – der eine gesperrte Leser | die **neue** Sha von `home_v2`, nie die alte: Die Vorschau sieht keinen halb umgeschriebenen Tag |
| `repair_pending_forget` auf einer zweiten Instanz | wartet; danach kein Checkpoint, HEAD, Notizen und Tags unverändert gegenüber dem Stand direkt nach dem `forget`, keine Reparatur. Nicht geprüft wird Unverändertheit des ganzen Dateisystems: Die Reparatur ruft `_ensure()` und fegt alte Objekt-Locks, auch wenn es nichts zu reparieren gibt (`store.py:1717-1729`) |

**Bewusst ohne eigenen Test: `ensure`.** Es nimmt den Lock, tut darunter aber nach dem ersten Aufruf je Pfad und Prozess nichts mehr als zu prüfen, ob `.git` existiert (`_swept_paths`, `store.py:523-534`); der erste Aufruf liegt vor jedem Schreiben dieses Prozesses. Dass es denselben Lock wie `forget` nimmt, belegen der Identitätstest (`test_store.py:100`) und der Wächter aus (a).

Dazu zwei Tests für die **bewusst ungesperrten** Lesezugriffe: `list_changes` und `measure` kehren zurück, **während** `forget` noch am Callback wartet – `forget` wird erst freigegeben, nachdem der Leser-Thread beendet ist, ein Warten auf den Lock ließe den Test also am `join`-Timeout scheitern statt ihn zu verlangsamen –, der Wächter meldet für den Leser-Thread keinen Erwerbsversuch, und das Ergebnis entspricht dem Stand vor dem `forget`.

Die Tests benutzen nur die öffentliche Schnittstelle, den öffentlichen Callback und den Wächter der Fixture, keinen privaten Namen von `HistoryStore`. Damit überstehen sie jeden späteren Umbau – auch den geparkten aus Abschnitt 3 – unverändert und sind dort der Beleg, dass der Umbau an der Nebenläufigkeit nichts geändert hat.

**Commits:** (1) der Docstring-Abschnitt, (2) der Wächter samt Selbsttest, (3) die Nebenläufigkeitstests, bei Bedarf in kleinen Gruppen. Jeder Commit nennt #42.

### 3. Geparkt: `forget` herauslösen

**Auslöser:** die nächste inhaltliche Änderung an `forget`, am Checkpoint oder an der Reparatur. Dann wird der Umbau als eigenes Vorhaben mit Buchstaben umgesetzt – als vorbereitender erster Schritt, damit die Änderung danach in einem kleineren, abgegrenzten Modul passiert. Vorher nicht: `store.py` ist seit dem 2026-09-22 unverändert, und ein Umzug von Code, den niemand anfasst, zahlt sich erst beim nächsten Anfassen aus (Entscheidung 1).

Der Zuschnitt, wie er im Dialog am 2026-09-28 abgestimmt wurde – festgehalten, damit er dann nicht neu erarbeitet werden muss, aber vor der Umsetzung gegen den dann aktuellen Code neu zu prüfen:

**Paket `store/` mit drei Modulen:**

| Schicht | Modul | Inhalt | ca. Zeilen |
|---|---|---|---|
| 2 | `history.py` | `HistoryStore` mit allem außer dem `forget`-Block; `_lock_for`, `_locks_by_path`, `_swept_paths`; Hilfen mit nur diesem Nutzer | ~2250 |
| 1 | `forget.py` | die 20 Methoden des `forget`-Blocks als Funktionen mit `store` als erstem Parameter; `_Progress` | ~1050 |
| 0 | `model.py` | das gemeinsame Vokabular: öffentliche Datenklassen, beide Ausnahmen, `_IDENTITY`, `_owns`, `_as_text`, die Dateinamen von Checkpoint und Zähler, `FORGET_RACE_RETRIES` | ~250 |

Die 20 Methoden: `forget` und `repair_pending_forget` (als `forget_locked`/`repair_locked`), `_forget`, `_finish_forget`, `_write_checkpoint`, `_read_checkpoint`, `_is_valid_commit`, `_is_valid_tag_target`, `_validate_checkpoint_semantics`, `_best_effort_checkpoint_key`, `_reconcile_index_with_head`, `_garbage_collect_protecting_index`, `_drop_from_index`, `_tree_without`, `_point_head`, `_raw_tags`, `_rewrite_notes`, `_planned_tag_changes`, `_rewrite_tags`, `_clear_stale_object_locks`. Keine andere Methode ruft sie auf.

**Regeln des Zuschnitts:**

- **Nur `history.py` nimmt den Lock.** Die öffentlichen Methoden behalten `with self._lock:` und rufen darin `forget.forget_locked(self, …)`; `forget.py` kennt weder `_lock` noch `threading`.
- **`forget.py` erreicht den Store nur über die übergebene Instanz,** nie über einen Import aus `history`. Das hält den Schichtenvertrag ein, und die Patches auf `HistoryStore._resolve`, `_revision_index`, `descriptions`, `_read_generation` und `_repo` greifen weiter.
- **Eine neue private Methode `HistoryStore._drop_caches()`** leert `_index` und `_survey`, statt dass `forget.py` in fremde Attribute schreibt.
- **Funktionen statt einer Klasse** (wie Entscheidung 3 in P); **kein eigenes Kontextobjekt** (Abweichung von Schritt 1 in #42 – mit einem einzigen herausgelösten Modul wäre es eine Schicht ohne zweiten Nutzer).
- **Relative Imports;** der Import von `versions` wird eine Ebene höher geholt (`from .. import versions as versioning`, flach weiterhin `import versions as versioning`), an beiden Ladewegen nachzuprüfen.
- **Logger über `logging.getLogger(__package__)`,** damit der Logger-Name unverändert bleibt.
- **`store/__init__.py` ohne Logik,** re-exportiert die zehn heute über `store` erreichten Namen (`HistoryStore`, `Change`, `Version`, `Measurement`, `DashboardFacts`, `RevisionIndex`, `StaleCursorError`, `GenerationReadError`, `FORGET_RACE_RETRIES`, `_as_text`) und trägt den Docstring aus Abschnitt 1. `operations.py` importiert `FORGET_RACE_RETRIES` statt des privaten Namens (Forderung aus #42), ohne Alias.
- **Schichtenvertrag `history` über `forget` über `model`, der mit jedem Modul wächst,** das ein Commit anlegt – nie eine fehlende Schicht, nie optionale Klammern, die man am Ende entfernen müsste (die Lücke aus P).
- **Sperrklinke:** die vier Baseline-Einträge ziehen mit neuen Schlüsseln und unveränderten Werten mit.
- **Kein Umzugsskript;** falls doch eins entsteht, muss es den Import-Alias im `try/except` auf oberster Ebene erkennen und mit klarer Meldung abbrechen.
- **Keine Zeilengrenze je Modul;** die Wache ist die Komplexität je Funktion.

**Tests beim Umzug:** 17 Stellen hängen um, keine Zusicherung ändert sich – `store_module._change` (→ `store.history._change`), `store_module.shutil` (→ `shutil`), die Wächter-Fixture (→ `store.history._lock_for`), `HistoryStore._rewrite_tags` ×10 (→ `store.forget._rewrite_tags`, ohne `staticmethod`-Hülle), `HistoryStore._rewrite_notes` ×3, `store._read_checkpoint()` und `HistoryStore._garbage_collect_protecting_index` (→ `store.forget`). Für jeden umgehängten Patch ist nachzuweisen, dass er greift (erwartete Ausnahme der Attrappe oder gezählte Aufrufe, sonst ein Aufrufzähler als einzige zulässige Ergänzung). Die Tests aus Abschnitt 2 bleiben unverändert.

**Reihenfolge:** `git mv store.py store/history.py` mit `__init__.py` und Logger; `model.py`; `forget.py`; Doku-Abgleich über `.md` **und** Code-Kommentare (bekannt: `operations.py:1166`, `:1689`, `__init__.py:122`, Verweise in Docstrings von `store.py` selbst; die harte Regel in `CLAUDE.md` nennt danach `store/`); Korrektheits-Review in einer frischen Session. `run_checks.py` nach jedem Commit, der Produktivcode bewegt, einmal mit einer alten `store.py` neben dem Paket.

**Offen gegen diesen Zuschnitt** (für die Prüfung vor der Umsetzung): `forget.py` griffe über die Instanz auf 16 private Teile von `HistoryStore` zu, und `model.py` entstünde nur, um einen Importkreis aufzulösen. Beides zeigt, dass die Kopplung durch den Umzug kaum sinkt – ein Grund, warum er jetzt nicht gebaut wird, und eine Frage, die vor der Umsetzung neu zu beantworten ist: ob sich bis dahin eine schmalere Schnittstelle zwischen `forget` und dem Rest anbietet.

## Fehler- und Randfälle

| Fall | Umgang |
|---|---|
| Der Wächter schlägt schon am heutigen Code an | Dann nimmt ein heutiger Pfad den Lock doppelt – ein echter Befund. Nicht in dieser Arbeit beheben; Issue schreiben, anhalten und mit dem Nutzer entscheiden |
| Ein Nebenläufigkeitstest findet einen echten Fehler, etwa einen Tag auf eine weggeräumte Revision | Nicht in dieser Arbeit beheben. Issue schreiben; der Test wird mit `pytest.mark.xfail(strict=True, reason=…)` samt Issue-Nummer eingecheckt, damit die spätere Behebung ihn umschlagen lässt, und hält bis dahin fest, was heute passiert |
| Ein Nebenläufigkeitstest ist in der CI instabil | Die Tests warten auf Ereignisse (Callback erreicht, Erwerbsversuch gescheitert, Thread beendet), nie auf eine Uhr; Timeouts sind nur die Obergrenze, nach der ein Test als rot gilt, statt die Suite hängen zu lassen. Schlägt ein Timeout in der CI an, wird er vergrößert, nie die Prüfung abgeschwächt |
| Der vorhandene `test_repair_waits_for_a_live_forget_on_another_instance` hat dieselbe Schwäche, die Astra für die neuen Tests fand (festes Zeitfenster) | Kein Teil dieser Arbeit – bestehende Tests bleiben unverändert. Als Nachbemerkung in den Plan: Mit dem Wächter ließe er sich später auf dieselbe Beobachtung umstellen |
| `forget` erreicht den Callback nicht, weil der Aufbau des Tests es vorher beendet (kein HEAD, `key` unbekannt) | Der Test prüft vor dem Start der Gegenoperation, dass der Callback erreicht wurde (`Event` mit Timeout); sonst schlägt er fehl, statt vakuös zu bestehen |
| Die Fixture stört einen Test, der den Lock bewusst aus einem zweiten Thread hält | Kann nicht: Der Wächter wirft nur bei einer zweiten Anforderung durch **denselben** Thread; ein anderer Thread wartet wie beim echten Lock |

## Test-Plan

- **Nach jedem Commit:** `python3 -m pytest tests/ -v` mit 0 failed, `tools/complexity_ratchet.py` und `lint-imports` grün.
- **Neu:** die Wächter-Fixture samt Selbsttest; je ein Test `forget` gegen jede Zeile der Tabelle in Abschnitt 2 (b), also acht; zwei für die ungesperrten Lesezugriffe.
- **`run_checks.py`:** nicht nötig – am Produktivcode ändert sich nur ein Docstring (Abweichung von #42, das es für jeden Schritt verlangt; begründet in Entscheidung 5).
- **Bestehende Tests:** unverändert.
- **Abdeckung:** die 90 % Zeilen und Zweige als Untergrenze, die nicht sinken darf – ausdrücklich **kein** Beleg für Nebenläufigkeit.

## Erfolgskriterien

1. Das Nebenläufigkeitsmodell steht an einer Stelle im Modul-Docstring von `store.py` und beschreibt die fünf Regeln aus Abschnitt 1; jede nennt ihren Test.
2. Der Wächter gegen doppeltes Sperren wirkt auf jeden `HistoryStore`, der während oder nach seinem Aufbau entsteht – nach heutigem Stand also in jedem Test, der einen baut –, und sein Selbsttest – doppeltes Sperren und gemeldeter Erwerbsversuch – ist grün.
3. Die zehn Tests aus Abschnitt 2 (b) laufen in der CI grün, oder als strikt erwarteter Fehlschlag mit verlinktem Issue.
4. `pytest` 0 failed; kein bestehender Test geändert; Sperrklinke und `lint-imports` unverändert grün.

## Dokumentation

- `docs/superpowers/status.md`: ein Eintrag, dass die Nebenläufigkeitsregeln des Stores seither beschrieben und geprüft sind, mit Verweis auf diese Spec, und dass #42 für den geparkten Umbau offen bleibt.
- Haupt-Spec: keine neue Entscheidung, kein Buchstabe. Ein Satz unter Entscheidung 21 oder 24, wo der Modul-Docstring die Regeln jetzt zusammenfasst, ist erlaubt, aber nicht nötig.
- `CLAUDE.md`: unverändert – keine harte Regel ändert sich.
- #42 bekommt nach der Umsetzung einen Kommentar (englisch, Vorschau vor dem Anlegen), der festhält, was erledigt ist und dass der Umbau mit Auslöser geparkt ist.

## Warum diese Fassung kürzer ist

Die erste Fassung sah nach den Invarianten ein Paket `store/` mit herausgelöstem `forget.py` vor (vier Commit-Schritte, 17 umgehängte Test-Stellen). Auf die Nachfrage des Nutzers, ob ein erfahrener Python-Entwickler das beim aktuellen Stand tun würde, zeigte eine zweite Messung:

- **Das Risiko in `store.py` ist die Nebenläufigkeit, nicht die Struktur.** 15 Fix-artige Commits, mehr als an jeder anderen Datei, fast alle an `forget` und am Zusammenspiel mit Lesern und Schreibern. Genau dort fehlen die Tests. Das rechtfertigt Abschnitt 1 und 2 sofort.
- **Niemand ändert gerade an `store.py`,** und keines der offenen Issues betrifft den Store. Ein Umbau zahlt sich erst beim nächsten Anfassen aus und kostet dann dasselbe.
- **Die Grenze wäre dünn** (siehe »Offen gegen diesen Zuschnitt« in Abschnitt 3): Code würde verschoben, die Kopplung sänke kaum.
- **Der Prozess passte nicht zum Nutzen:** Spec, externe Reviews, Plan und Review in einer frischen Session für einen Umzug, der nichts ändern soll, an Code, den niemand anfasst.

## Entscheidungen (vom Assistenten vorgeschlagen, im Dialog mit dem Nutzer am 2026-09-28 abgestimmt – Freigabe der Spec steht aus)

1. **Nur die Invarianten jetzt, der Umbau geparkt mit Auslöser.** Siehe »Warum diese Fassung kürzer ist«. Davor verworfen, in dieser Reihenfolge: die vollständige Aufteilung in sieben Module mit allen 43 Patches umgehängt (Hälfte der Zeilen ist Prosa, die Funktionen sind klein – nicht feiner teilen als nötig, wie bei P); Mixins (trennen nur Dateien, `import-linter` sieht Aufrufe über `self` nicht); das Herauslösen nur zustandsloser Funktionen (lässt alle Verantwortlichkeiten in einer Klasse). Der für später festgehaltene Zuschnitt ist der schlanke aus Abschnitt 3.
2. **Die Nebenläufigkeitstests sind das zentrale Sicherheitsnetz, gebaut über den öffentlichen `progress`-Callback.** Er läuft unter dem Lock, bevor sich ein Ref bewegt, und ist damit eine Haltestelle mitten in `forget`, ohne einen privaten Namen zu patchen. Den Ausschluss belegt ein beobachteter, gescheiterter Erwerbsversuch, nicht ein Zeitfenster (Astra). Geprüft wird daneben der Endzustand – etwa, dass eine hinter `forget` eingereihte `create_version` auf einer weggeräumten Revision als `ValueError` endet und nicht als Tag auf ein totes Objekt. Die 90 % Zeilenabdeckung zeigen, dass Code lief, nicht dass zwei Threads gleichzeitig darin waren.
3. **Ein Wächter gegen doppeltes Sperren für die ganze Testsuite.** Das Gegenstück zum Vergleichswerkzeug aus P: Er vergleicht keine Ergebnisse, sondern macht aus einem Fehler, der sonst still hängt, einen lauten – in allen Tests, die einen `HistoryStore` bauen, nicht nur in den neuen. Zugleich ist er das Messinstrument für den Ausschluss: Nur er kann sehen, dass ein Thread tatsächlich am Lock gescheitert ist.
4. **Kein Vergleichswerkzeug alt gegen neu, kein Test auf die Konstruktion eines eigenen Locks.** Ein Vergleich von Rückgabewerten fängt weder ein Rennen noch einen Deadlock. Der optionale Test aus #42 gegen einen eigenen Lock eines Collaborators hat ohne Collaborators keinen Gegenstand; für den geparkten Umbau fangen die Ausschluss-Tests aus Abschnitt 2 (b) das über das Verhalten, und ein Grep nach `_lock` und `threading` in `forget.py` gehört dann in dessen Erfolgskriterien. Kein Teil dieser Arbeit ruft `git` auf, auch keine Prüfhilfe.
5. **Kein `run_checks.py`** für diese Arbeit. #42 verlangt es für jeden Schritt, weil `operations.py` von pytest nicht erreichbar ist; hier ändert sich an keinem Codepfad etwas, den `run_checks.py` sehen könnte. Für den geparkten Umbau gilt die Forderung aus #42 unverändert.
6. **Die Prosa bleibt unangetastet.** Viele Docstrings sind ein Stück Designjournal – »gemessen am …«, »ein Review fand …«. Sie auf Vertrag, Invariante und das nicht offensichtliche Warum zu kürzen, brächte für die Lesbarkeit womöglich mehr als jeder Umzug; es ist aber eine Stilentscheidung über den Charakter des Projekts, und diese Notizen verhindern auch Rückfälle. Offene Frage an den Nutzer, kein Teil dieser Arbeit.
7. **Ein echter Fehler wird nicht nebenbei behoben,** sondern als Issue festgehalten und als strikt erwarteter Fehlschlag eingecheckt. So bleibt diese Arbeit verhaltensneutral, und die Behebung ist ein eigener, prüfbarer Commit, der den Test umschlagen lässt.
8. **Kein Buchstabe, kein externes Review, kein eigener Umsetzungsplan-Aufwand über das Nötige hinaus.** Drei kleine Commits ohne Produktivcode außer einem Docstring. Ein kurzer Plan genügt; ein Korrektheits-Review in einer frischen Session ist billig und bleibt als letzter Schritt vorgesehen, weil es bei P zwei echte Lücken fand.

### Abgleich mit den Reviews

*Terra (2026-09-28), zweite Fassung:* kein kritischer Befund. Alle Befunde am Code nachgeprüft und übernommen:

- **Hoch – das Modell beschrieb die ungesperrten Leser zu breit.** Nur `list_changes` und `search_changes` (plus `async_history`/`async_search` in `operations.py`) laufen über den Retry aus Entscheidung 24; `survey`, `measure` und die übrigen Leser fangen ein weggeräumtes Objekt an Ort und Stelle ab. Regel 3 und 5 in Abschnitt 1 nennen jetzt beide Gruppen mit ihren Mitgliedern, eine neue Zeile der Ausgangslage belegt das. Gerade dieser Befund zeigt, wofür der Abschnitt da ist: Die verstreute Prosa hatte auch den Verfasser der Spec zu einer zu breiten Aussage verleitet.
- **Mittel – vier Tests hätten ihre erwartete Antwort nicht zwingend erreicht:** eine Revision vor dem ersten Commit von `gone` behält ihre Sha (jetzt: gemeinsamer Aufbau mit `home_v2` und nachgewiesener Vorbedingung); `write_snapshot` mit unverändertem Inhalt committet nicht; die Versions-Tests brauchen eine vorab angelegte `gone/v1.0.0`; `create_version` braucht einen nicht kollidierenden Namen, damit der richtige `ValueError` geprüft wird.
- **Mittel – »ändert nichts« bei der Reparatur war zu absolut:** `_ensure()` und das Fegen alter Objekt-Locks laufen immer. Jetzt auf Checkpoint, HEAD, Notizen und Tags begrenzt.
- **Mittel – zwei Lock-Nehmer fehlten:** `read_version` bekommt einen eigenen Test (seine ganze Begründung für den Lock ist, keinen halb umgeschriebenen Tag zu sehen – genau das prüft er jetzt); `ensure` bleibt begründet ohne eigenen Test. Damit acht Zeilen und zehn neue Tests statt sieben und neun.
- **Niedrig – Wirkung der Fixture zu breit formuliert:** Sie wirkt auf Instanzen, die während oder nach ihrem Aufbau entstehen. Abschnitt 2 (a) und Erfolgskriterium 2 sagen das jetzt so.

Bestätigt ohne Änderung: die zehn Lock-Methoden, die Haltestelle im `progress`-Callback, die Caches pro Instanz, die Umsetzbarkeit des Wächters, kein heutiger Pfad mit doppeltem Sperren, die Testzahlen, die begründeten Abweichungen von #42.

*Gemini (2026-09-28), empirisch – jeder Fall in einem Wegwerf-Skript außerhalb des Repositorys ausgeführt:* kein kritischer Befund. Bestätigt durch Ausführung: die Haltestelle (beim ersten Callback Lock gehalten, Refs unverändert, kein Checkpoint), jede Zeile der Tabelle in Abschnitt 2 (b) (blockiert wie erwartet, Endzustand wie erwartet) sowie die zwei Lesezugriffe (antworten in unter 50 ms mit dem Stand vor dem `forget`), und der Wächter: die ganze bestehende Suite lief mit ihm grün (`976 passed, 2 skipped`), kein einziger Pfad sperrt doppelt. Die Zahlen der Ausgangslage bis auf die unten genannte bestätigt. Gemini prüfte die Tabelle noch in ihrer Fassung vor Terras Befunden; die `read_version`-Zeile kam danach dazu.

- **Mittel – Revisionswahl bei `create_version` und `set_description`:** deckungsgleich mit Terras Befund und durch den gemeinsamen Aufbau schon behoben. Gemini hat die Gegenprobe ausgeführt: Auf einer Revision vor dem ersten betroffenen Commit legt `create_version` den Tag an und `set_description` liefert `True` – der Test wäre mit falscher Revision rot geworden, nicht vakuös grün.
- **Mittel – 43 statt 38 Patches:** übernommen, in der Ausgangslage korrigiert. Am geparkten Zuschnitt ändert das nichts: Die vier zusätzlichen `_resolve`-Patches treffen eine Methode, die in `HistoryStore` bliebe, und der Patch auf `_garbage_collect_protecting_index` war dort schon unter den 17 Stellen gezählt.
- **Niedrig – #13 fehlte in der Liste offener Issues:** ergänzt; betrifft den Store nicht.
- **Niedrig – ein bestehender Test ist mit rund 1,2 % instabil:** `test_repair_clears_a_stale_object_lock` legt `objects/ab/` mit `mkdir(parents=True)` ohne `exist_ok=True` an (`tests/test_store.py:1936`) und scheitert mit `FileExistsError`, wenn eines der drei vorher geschriebenen Objekte zufällig mit `ab` beginnt. **Kein Teil dieser Arbeit** (»keine Änderung an bestehenden Tests«), aber ein echter Befund: als eigener, einzeiliger Commit vor Q0, nach Freigabe durch den Nutzer – sonst färbt er gelegentlich einen der neuen Commits rot, ohne mit ihm zu tun zu haben.

*Astra (2026-09-28), eine Frage – kann ein Test aus Abschnitt 2 (b) grün werden, ohne den Ausschluss zu beweisen?* **Trifft zu**, gezeigt an `repair_pending_forget`: Bekommt der Gegenoperations-Thread während des ganzen Zeitfensters keine CPU-Zeit, besteht »nach dem Fenster nicht fertig«, `forget` läuft durch, die Reparatur danach findet keinen Checkpoint – alle drei Prüfungen grün, auch wenn die Reparatur den Lock gar nicht nähme. Kein Fehler im Code (sie nimmt ihn als erste Anweisung, `store.py:1717`), sondern in der Beweiskraft des Tests. Der Befund gilt für **jede** Zeile der Tabelle, nicht nur für diese: Jeder erwartete Endzustand ist genau der, den die Gegenoperation auch nach einem beendeten `forget` erreicht. Übernommen wie vorgeschlagen: Der Wächter meldet einen gescheiterten Erwerbsversuch, und der Test gibt `forget` erst frei, wenn diese Meldung für den Gegenoperations-Thread vorliegt (Abschnitt 2 a und b). Für die ungesperrten Leser umgekehrt: keine Meldung, und Rückkehr, bevor `forget` freigegeben wird.

*Terra zum Plan (2026-09-28):* Ein Befund betrifft die Spec selbst und ist hier nachgezogen. **Hoch – auch die zweite Fassung von Regel 3 war zu breit:** Sie ordnete die direkten Lesehilfen den Lesern zu, die ein weggeräumtes Objekt abfangen. `_resolve` (`store.py:2914`) und `_read_from` (`:2968`) laden es aber ungeschützt, ebenso der Aufbau des Index; `resolve`, `read_at`, `read_meta_at` und alles, was vorher HEAD auflöst, können während eines `forget` weiterhin werfen. Regel 3 kennt jetzt drei Gruppen, und jede der 28 öffentlichen Methoden ist per AST genau einer zugeordnet. Dass es dieselbe Fehlerklasse zum zweiten Mal war – eine zu breite Aussage über ungesperrte Leser, aus verstreuter Prosa abgeleitet –, ist der stärkste Beleg dafür, wofür der neue Docstring-Abschnitt da ist. Die ungeschützten Ladestellen selbst sind **kein Teil dieser Arbeit** (keine Verhaltensänderung); festgehalten als [#44](https://github.com/PPP01/ha-dashboard-history/issues/44). Die Lücke ist älter als diese Arbeit: Die ungeschützte Ladestelle in `_resolve` stammt aus `ee67412` (2026-08-30), zum Rennen wurde sie mit dem sofortigen Wegräumen in `forget` (`3ad7c38`, 2026-09-01, `grace_period=0`); Entscheidung 24 sicherte danach nur die beiden Leser mit Retry und vier einzelne Stellen ab.

Die übrigen Befunde betrafen nur den Plan und sind dort eingearbeitet: der Reparatur-Test prüft jetzt Notizen und die vollständige Ref-Menge (mit Gegenprobe: eine Reparatur, die die Notiz verliert, wird rot); Task 3 und der Eintrag in `status.md` sind ein Commit, sodass es bei den drei Commits der Spec bleibt; ein Subject war 51 Zeichen lang; Gegenprobe 2 räumt über `trap` auch bei Abbruch auf. **Zurückgewiesen:** die angeblich falschen Testzahlen – 976 bestanden plus 4 neue sind 980, plus 14 sind 990; beides hat das Durchspielen des Plans genau so ausgegeben. Der Plan nennt die Erwartung trotzdem jetzt relativ, weil die absolute Zahl mit `.real-storage` schwankt.

*Gemini zum Plan (2026-09-28), den Plan wörtlich in einer Kopie durchgespielt:* Jeder Schritt mit »Expected« traf ein, Sperrklinke und Importverträge nach jedem Task grün, die Suite unter Last (acht parallele CPU-lastige Prozesse) stabil. Neu belegt: Entfernt man den Lock aus **einer einzigen** Methode, wird genau deren Test rot (bei `write_snapshot` zusätzlich der Verdrahtungstest des Wächters, der sie benutzt) – die Gegenprobe des Plans hatte das nur für alle acht zusammen gezeigt. Der einzige Befund (Subject mit 51 Zeichen) war bereits nach Terras Plan-Review behoben; Gemini hatte die Fassung davor gelesen, den erweiterten Reparatur-Test also nicht gesehen.

*Astra zum Plan (2026-09-28), eine Frage – misst `GuardedLock` richtig?* **Trifft zu**, reproduziert: Der Wächter merkte sich wartende Threads über `threading.get_ident()`, und CPython vergibt eine ID nach dem Ende ihres Threads neu. Ein frischer Thread konnte so den Vermerk »hat gewartet« eines beendeten erben, und `queued_behind` hätte bestanden, ohne dass er den Lock je angefordert hatte. In den zehn Tests trat das nicht auf, weil dort vor der Gegenoperation kein Thread gewartet und geendet hat – ein Zufall der Testform, keine Eigenschaft des Instruments. Übernommen: Der Wächter speichert Thread-Objekte statt IDs, für wartende wie für den haltenden Thread (`_owner`, gleiche Wiederverwendung). Ein neuer Selbsttest hält den Fall fest; gegen die ID-basierte Fassung war er in zehn von zehn Läufen rot, gegen die neue ist er grün. Damit fünf Selbsttests statt vier.

### Ausblick, außerhalb von #42

Gemessen an Änderungshäufigkeit und Testbarkeit liegt der größere Hebel für »Änderungen fallen leichter« vermutlich in `operations.py`: 1706 Zeilen, 55 Commits, drei Ausreißer aus #43, und für pytest unerreichbar, weil es Home Assistant importiert – allerdings nur über `HomeAssistant`, `HomeAssistantError`, `dt_util` und `const`. Von den 15 synchronen Hilfen darin haben 12 weder einen Bezug zu Home Assistant noch zum Store (`_preview`, `_reinsertion`, `_plan_undo`, `_marks_by_revision`, `_rendered`, `_refuse_unrecorded_state`, `_undo_state_checks` u. a.; AST-Auswertung 2026-09-28). Geprüft werden sie heute nur im Container: über `run_checks.py` und drei gezielte Skripte (`run_unrecorded_state_refusal.py`, `run_search_past_a_forget.py`, `run_stale_pagination_cursor.py`) – eine breitere Absicherung als in der ersten Fassung dieses Ausblicks behauptet, aber keine schnelle, unabhängige.

Zwei Einschränkungen aus einem Hinweis von Astra (2026-09-28), beide am Code bestätigt: **Die Hilfen sind überwiegend klein (3–38 Zeilen), die Komplexität steckt in den async-Abläufen** – die drei Baseline-Einträge sind `async_restore_state`, `async_undo_change` und `async_compare`. Nur die Hilfen herauszuziehen, baut diese Komplexität nicht ab; der Gewinn entsteht erst, wo sich fachliche Entscheidungen aus einem solchen Ablauf isolieren lassen. Und **kein vollständiger Umbau**: Der Vorschlag ist, einen überschaubaren, fachlich zusammenhängenden Ablauf herauszugreifen, seine Entscheidungslogik HA-frei und mit pytest prüfbar zu machen und daran zu sehen, ob die neue Grenze die nächsten Änderungen tatsächlich erleichtert.

**Reihenfolge, mit dem Nutzer abgestimmt:** (1) diese Arbeit; (2) ein begrenzter Ablauf aus `operations.py`, zuerst als Messung – welcher Ablauf, wie viel Entscheidungslogik sich daraus lösen lässt –, erst danach eine eigene Spec; (3) der geparkte `forget`-Umbau aus Abschnitt 3, sobald sein Auslöser eintritt.
