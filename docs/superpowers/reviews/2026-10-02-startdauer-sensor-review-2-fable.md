# Review 2 (Fable): Startdauer als Diagnose-Sensor – Fassung 2

**Gegenstand:** `docs/superpowers/plans/2026-10-02-startdauer-sensor.md`, Fassung 2 (uncommittet im Arbeitsbaum, Branch `startup-duration-sensor`). Code-Stand `main` bei `5004421`. Runde 1: `2026-10-02-startdauer-sensor-review-1-{terra,gemini,astra,gemini-risiko}.md`.

**Auftrag:** gezielt, nicht breit – fünf Punkte: (1) Befunde aus Runde 1, (2) der `survey()`-Abschluss, (3) `first_index_build()`, (4) die neuen Tests, (5) neue Fehler durch Fassung 2.

**Methode:** Scratch-Kopie aus `git archive HEAD`. Dort Task 1 bis 3 wörtlich nach Plan angewendet, dazu die `run_checks.py`-Änderungen aus Task 2 und 3. Ausgeführt: die vier neuen Store-Tests vor und nach der Umsetzung, zwei absichtlich falsche Umsetzungen, `tests/test_store.py` + `tests/test_store_concurrency.py` (278 passed), `tests/test_report.py` rot (11 failed, `TypeError` wie angegeben) und grün (15 passed), `tests/test_integration_files.py` (7 passed), `python3 tools/complexity_ratchet.py` (»20 known values, none grew«), `lint-imports` (2 kept, 0 broken), `py_compile` für `__init__.py`, `sensor.py`, `coordinator.py`, `diagnostics.py` und `run_checks.py`, `ruff --select F` auf `run_checks.py` (sauber). Im Container nur lesend: `RegistryEntry.as_partial_dict`, `DataUpdateCoordinator._async_refresh`, `CoordinatorEntity.available`, JSON-Form von `EntityCategory` – kein Neustart, kein `run_checks.py`. Die Scratch-Kopie ist gelöscht.

Zeilenangaben zum Plan beziehen sich auf die Fassung im Arbeitsbaum, zum Code auf `5004421`.

---

## Kritisch

Keine Befunde dieser Schwere.

## Wichtig

### W1 – Die gewählte Reihenfolge »erst `_index` veröffentlichen, dann die Zeit setzen« öffnet ein Fenster, in dem der Abschluss-`survey()` den Index sieht, die Zeit aber nicht

- **Fundstelle:** Plan Z. 186–194 (Task 1 Step 3) und Z. 79 (»Er wird erst gesetzt, nachdem `self._index` veröffentlicht ist«); `store.py:2721–2723` (Schnellpfad von `_revision_index` *ohne* `_index_gate`); Plan Z. 553–554 (`_async_time_the_start` liest `store.first_index_build()` nach dem `await`).
- **Beschreibung:** Baut ein anderer Thread den ersten Index – ein früh geöffnetes Panel über `dashboard_listing()` → `survey()`, oder ein Diagnose-Download über `measure()` –, dann steht nach `self._index = found` der Index für HEAD, und `_first_index_build` ist noch `None`, bis die nächste Anweisung läuft. Der Abschluss-`survey()` aus `_async_time_the_start` prüft in `_revision_index` *vor* dem Gate `cached.head == head` (Z. 2721–2723), kehrt ohne das Gate zurück, beendet `survey()` und `_async_time_the_start` liest `None`. In der Scratch-Kopie mit einem künstlich verbreiterten Fenster (ein `sleep` zwischen den beiden Zuweisungen, nur dort) reproduziert: `{'index_build_at_close': None, 'index_head_ok': True, 'index_build_later': 0.0018}`. Im Produktivcode ist das Fenster wenige Bytecodes breit – ein GIL-Wechsel nach einem CPU-gebundenen Bau reicht. Selten, aber dann dauerhaft: `coordinator.startup_index_seconds` wird nie wieder geschrieben.
- **Konsequenz:** Genau der Fall, den Review Focus 4 ausschließen will (»`index_build` ist eine Zahl, nicht dauerhaft `null`«), bleibt möglich – ausgerechnet bei einem Start, in dem jemand das Panel sofort öffnet, also der Diagnosefall, für den die Zahl gedacht ist. Astras Argument für diese Reihenfolge (ein gespeicherter Zeitwert dürfe nicht als Bereitschaftsnachweis gelesen werden) trifft den einzigen Leser nicht: `_async_time_the_start` liest erst, nachdem `survey()` zurückgekehrt ist, und dann ist der Index für HEAD ohnehin veröffentlicht oder die Übersicht aus dem Cache. Die Umkehrung löst also ein Problem, das dieser Leser nicht hat, und schafft eines, das er hat.
- **Vorschlag:** Unter dem Gate zuerst `_first_index_build` setzen, dann `self._index = found`; der Kommentar begründet es umgekehrt: *»Before `_index` is published: the lock-free fast path above hands the index out without the gate, and whoever sees it that way must see the time too. The only reader of the time asks after a survey has returned, never as a sign the index is there.«* Unter dem GIL werden die Zuweisungen eines Threads in Programmreihenfolge sichtbar; ein neuer Sperrerwerb ist nicht nötig. Die vier Tests bleiben in beiden Reihenfolgen grün (nachgeprüft), ein einfädiger Test kann die Reihenfolge nicht festnageln – der Kommentar muss die Begründung tragen. Plan Z. 79 und Z. 56 (»nach dem Veröffentlichen von `_index`«) entsprechend ändern.

### W2 – Die Vertragszeile »Opening pass … gescheitert → `null`« verspricht mehr, als der Code hält

- **Fundstelle:** Plan Z. 1030 (Regeltabelle: »Beide `null`, solange … nicht gemessen werden konnte (Repository nicht anlegbar, Opening pass oder `survey()` gescheitert)«), Z. 433–435 (Coordinator-Kommentar »an opening pass or closing survey that failed«); `capture.py:182–186` (`_async_read` schluckt, liefert `None`), `237–238` (Löschungen), `244–246` (jedes Dashboard einzeln); `__init__.py:66–73`.
- **Beschreibung:** `async_opening_pass()` wirft praktisch nie. Ein Pass, der keine Konfiguration lesen konnte, ein Pass, in dem jeder Schreibvorgang scheiterte – beide kehren normal zurück, der `else`-Zweig läuft, `survey()` indiziert die vorhandene Historie, die Zahl wird gesetzt. Fassung 2 fängt davon nur den Fall ab, in dem `store.ensure` (oder `capture.async_start`) wirft. Für die *Bedeutung* des Sensors ist das in Ordnung – gemessen wird »bis indiziert«, nicht »bis aufgezeichnet«, und der Index für den vorhandenen HEAD steht danach wirklich (Terras Befund 2 ist damit bewusst umgedeutet, und die Umdeutung trägt). Aber die Vertragszeile sagt »Opening pass gescheitert«, und das liest ein Tester als »nichts aufgezeichnet«. Ein Bericht mit `startup.seconds = 0.3` und `totals.revisions = 0` nach einem Pass, der alles verschluckt hat, ist dann formal vertragswidrig.
- **Konsequenz:** Die bindende Spec beschreibt einen Nullfall, den der Code nicht liefert; nächste Reviews berufen sich darauf.
- **Vorschlag:** In der Regeltabelle: »Opening pass mit Ausnahme abgebrochen oder `survey()` gescheitert«, plus ein Satz: »Lese- und Schreibfehler, die der Pass selbst protokolliert und verschluckt, verhindern die Messung nicht – gemessen wird, bis die *vorhandene* Historie indiziert ist, nicht, ob der Pass etwas aufgezeichnet hat.« Denselben Satz in den Coordinator-Kommentar (Z. 433–435) und in den Nachtrag (Z. 1047).

## Hinweis

### H1 – »Ein `forget` während des Starts … wird mitgezählt« gilt nur, wenn es einen Schreibvorgang überlappt

- **Fundstelle:** Plan Z. 27; `store.py:1792` (`forget` unter `self._lock`), `1808–1809` (verwirft `_index` und `_survey`), `3404–3434` (`survey()` hält `self._lock` nicht).
- **Beschreibung:** Ein `forget`, das erst beginnt, nachdem der letzte Write des Passes zurück ist, und mit dem Abschluss-`survey()` überlappt, wird weder gebremst noch mitgezählt: `survey()` baut für den alten HEAD, `forget` verwirft den Cache, das Panel baut danach neu. Durch »solange kein gleichzeitiges `forget` die Historie umschreibt« ist der Fall ausgeschlossen, aber der Satz danach klingt, als sei jedes `forget` während des Starts abgedeckt. Dasselbe gilt für einen Checkpoint, den `repair_pending_forget` nicht schließen konnte (`store.py:1917–1925`): `survey()` indiziert die halb umgeschriebene Historie, die Zahl wird gesetzt.
- **Vorschlag:** »Ein `forget`, das einen Schreibvorgang des Passes überlappt, hält ihn an `self._lock` fest und verlängert die Zahl; eines, das nur den Abschluss überlappt, wird weder gezählt noch gebremst – beides fällt unter den Vorbehalt oben.« Keine Codeänderung; Astras Abschluss-Helfer unter beiden Sperren bleibt zu Recht abgelehnt (siehe Tabelle).

### H2 – Der Kommentar zu `started = None` nennt nur einen von zwei Pfaden

- **Fundstelle:** Plan Z. 453–454 (»None below if there is no repository«) und Z. 482–484.
- **Beschreibung:** Das `except` deckt auch `capture.async_start()` ab; wirft das, existiert ein Repository, die Historie wird vom Panel indiziert, aber der Start nicht gemessen. Harmlos und vertretbar (ohne Aufzeichnung ist die Zahl ohnehin wenig wert), nur der Kommentar stimmt dann nicht. Typ und Lesbarkeit (`started: float | None = time.monotonic()` als erste Anweisung, einmal `None` gesetzt) sind in Ordnung.
- **Vorschlag:** »None below if the recording could not start – no repository, or no subscription«.

### H3 – Zwei »fünf« überleben den Abschluss-`grep` aus Task 4

- **Fundstelle:** `sensor.py:32` (»five entities are a device page somebody reads, fifteen are one they skim past«), Spec Z. 97 (»Fünf Entitäten sind eine Geräteseite, die man liest; fünfzehn …«); Plan Z. 1072 (`grep` nach `five readings|fünf Sensoren|Fünf Sensoren`).
- **Beschreibung:** Beide Stellen begründen, warum Detailzahlen Attribute sind, und bleiben als Begründung lesbar – aber sie zählen jetzt falsch, und der `grep` findet sie nicht.
- **Vorschlag:** Entweder beide auf sechs ziehen oder bewusst stehen lassen und das im Nachtrag sagen; den `grep` um `five entities|Fünf Entitäten` erweitern, damit die Entscheidung sichtbar ist.

### H4 – Die Endzeit wird nach der Rückkehr in den Event-Loop genommen

- **Fundstelle:** Plan Z. 549–553.
- **Beschreibung:** Zwischen Rückkehr des Executors und `time.monotonic()` liegt die Loop-Latenz; sie zählt mit. Für eine Zehntelsekunde ohne Belang. Wer es exakter will, misst in einer kleinen Executor-Funktion (`survey()` + `monotonic()` in einem Aufruf) – das würde zugleich W1 anders lösen, wenn die Funktion den Wert unter `_index_gate` läse, wäre aber ein neuer Sperrerwerb. Die Reihenfolge-Korrektur aus W1 ist die kleinere Änderung.

### H5 – Zwei volle Bauten in einem Start: die Aussage stimmt, mit einer Einschränkung

- **Fundstelle:** Plan Z. 29; `store.py:1907–1911`, `1941–1942`.
- **Beschreibung:** `repair_pending_forget` verwirft den Cache nur, wenn ein Checkpoint vorhanden *und* gültig ist. Zwei Bauten entstehen, wenn Panel oder Diagnose-Download vor der Reparatur bauen; der erste zählt dann und beschreibt die *unreparierte* Historie (die vergessenen Commits noch enthalten, also eher größer). »Gleich wer ihn auslöst« deckt das; ein Halbsatz »auf dem HEAD, der zu dem Zeitpunkt galt« würde es benennen. `_reconcile_index_with_head` und `_drop_from_index` betreffen die git-Staging-Datei, nicht `_index` – kein weiterer Pfad.

---

## Prüfpunkt 2 – Trägt der `survey()`-Abschluss?

Alle Rückkehrpfade von `survey()` (`store.py:3419–3472`) gegen die Aussage in »Was die Zahl verspricht« (Plan Z. 27):

| Pfad | Index für HEAD? | Schädlich für die Aussage? |
|---|---|---|
| `repo is None` → `Survey([], set(), {})` (Z. 3420–3421) | nein | Nur erreichbar, wenn `.git` nach `ensure` verschwand; `ensure`-Fehler setzt `started = None`. Nicht schädlich. |
| `head is None` → leer (Z. 3423–3424) | kein Index nötig | Historie ohne Commit: die Liste ist leer und sofort da. `index_build` `null`, `seconds` gesetzt – so steht es im Vertrag (Z. 1030) und im Test `test_an_empty_history_reports_honest_zeros`. Nicht schädlich. |
| Cache-Treffer `_survey[0] == head` (Z. 3425–3427) | ja, zuvor | Nur `survey()` selbst schreibt `_survey`, und zwar nach `_revision_index` für denselben HEAD; `forget`/`repair` verwerfen beide Caches gemeinsam (Z. 1808f., 1941f.). Ein Treffer bedeutet: eine frühere `survey()` hat den Index für diesen HEAD gebaut oder verlängert, und die Zeit war vor Freigabe des Gates gesetzt. Nicht schädlich. |
| `_revision_index` liefert `None` (Z. 3432–3434) | – | Nur bei `head is None`, oben behandelt. |
| `KeyError` am Baum (Z. 3437–3442) → leer | Index gebaut | Ein `forget` dazwischen – fällt unter den Vorbehalt. |
| `_revision_index` über den Schnellpfad ohne Gate (Z. 2721–2723) | ja | **W1:** Index da, Zeit möglicherweise noch nicht. |
| Ausstehender, nicht reparierbarer Checkpoint | ja, für den halb umgeschriebenen HEAD | `survey()` prüft keinen Checkpoint; `dashboard_listing` fällt bei `ForgetRaceExhausted` auf dieselbe `survey()` zurück (Z. 3611–3613). Die Liste kommt aus dem Cache – die Zahl bleibt eine obere Grenze. Siehe H1. |

Die Aussage ist, mit dem Vorbehalt gegen gleichzeitiges `forget`, haltbar: Nach Rückkehr von `survey()` ist entweder der Index für den dann gültigen HEAD veröffentlicht und die Übersicht im Cache, oder es gibt keinen Commit. Was nach dem Abschluss passiert (ein Save über `capture.async_start()`, das schon vor dem Pass abonniert war, ein `forget`), kann keine Startzahl begrenzen – der Plan sagt das.

## Prüfpunkt 3 – `first_index_build()`

- **Unter `_index_gate`?** Ja: die Zuweisung steht im `with self._index_gate:`-Block (Plan Z. 183–194).
- **Nach dem Veröffentlichen von `self._index`?** Ja – und das ist W1.
- **Nie überschrieben?** Ja: `if took is not None and self._first_index_build is None`. `_extended_index` liefert `took = None`. Gegen »letzter statt erster« wird Test 3 rot (gezeigt).
- **Lesen ohne Sperre vom Event-Loop?** Ein Attribut-Lesezugriff auf `float | None` unter dem GIL ist atomar; das `await hass.async_add_executor_job(store.survey)` ordnet den Lesezugriff nach dem Executor-Aufruf. Unbedenklich – bis auf das Fenster aus W1, das nicht vom Lesen, sondern von der Schreibreihenfolge im Bau-Thread kommt.
- **`repair_pending_forget`, zwei Bauten, nur der erste zählt:** stimmt, beide liegen nach `started`; siehe H5.

## Prüfpunkt 4 – Die neuen Tests

| Test | ohne Umsetzung | mit Umsetzung | gegen »letzter statt erster Bau« | gegen »Zeit vor `self._index = found`« |
|---|---|---|---|---|
| `test_the_store_keeps_how_long_its_first_full_build_took` | FAIL, `AttributeError … first_index_build` | PASS | PASS | PASS |
| `test_extending_the_index_leaves_the_build_time_alone` | FAIL, dito | PASS | PASS | PASS |
| `test_a_later_full_rebuild_leaves_the_first_build_time_alone` | FAIL, dito | PASS | **FAIL** | PASS |
| `test_a_fresh_history_gets_its_index_from_the_survey_after_its_first_write` | FAIL, dito | PASS | PASS | PASS |

Test 3 prüft wirklich einen Neubau: `store._index = None` entspricht `forget` (Z. 1808), `_built_index` wird als Instanzattribut überschrieben (die Staticmethod wird dadurch umgangen, der Aufruf `self._built_index(repo, head)` trifft die Funktion ohne Bindung – funktioniert), und die Logzeile »Built the revision index« wird verlangt. `list_changes` statt `survey` ist richtig, weil `_survey` am alten HEAD träfe. 0,05 s Schlaf gegen eine Erstbauzeit von etwa 2 ms auf einem Commit – die Unterscheidung ist robust. Die Reihenfolge der beiden Zuweisungen kann einfädig kein Test festnageln; erwartbar, siehe W1. `test_building_the_index_is_logged_with_its_size_and_time` bleibt unverändert grün. Ratchet: `_revision_index` steigt von C901 6 auf 7, unter dem Grenzwert 10; die fünf übrigen ruff-Meldungen in `store.py` stehen identisch in HEAD und in der Baseline.

## Prüfpunkt 5 – Neue Fehler durch Fassung 2

- **`started = None`:** siehe H2. Typ und Lesbarkeit in Ordnung; `py_compile` sauber.
- **`_async_time_the_start`:** `except Exception` fängt `ForgetRaceError` (Unterklasse von `KeyError`, Z. 578), `MissingCommitError` und `OSError`; `CancelledError` ist `BaseException` und beendet den Task, wie es der Docstring von `_async_open` für die anderen Hälften beschreibt – konsistent. Nach einem Fehler bleibt beides `None`, Floor und erste Messung laufen weiter. Nichts rutscht durch. Die Werte stehen vor `coordinator.async_refresh()`; `_async_refresh` ruft die Listener nach der ersten Aktualisierung auch dann, wenn sie scheitert (`previous_update_success` ist anfangs `True`; im Container nachgelesen), die Entität schreibt also ihren Zustand. `CoordinatorEntity.available` ist eine Property und liefert `last_update_success`; das Überschreiben mit `True` ist zulässig.
- **`run_checks.py`:** Sieben rote Checks in Task 2 Step 3 stimmen (1 Registrierung, 1 Kategorie/Gerät, 2 × 2 `check_startup_time`, 1 Reload). `check(name, ok, detail)`, `entity_state`, `entity_attributes`, `entry_id`, `Socket(...).call` passen zu den echten Signaturen (Z. 132, 241–276, 336, 4846–4851); `asyncio` ist importiert. `config/entity_registry/list` liefert `entity_category` und `device_id` aus `as_partial_dict` (im Container nachgelesen, HA 2026.8.3), `EntityCategory.DIAGNOSTIC` serialisiert zu `"diagnostic"`. Der Vergleich Bericht gegen Sensor (`round(x, 1)` beidseitig, Zustand als String → `float`) ist exakt: `float(str(round(x, 1))) == round(x, 1)` für die geprüften Werte. `ruff --select F` auf dem gepatchten Skript: sauber.
- **Spec-Ersetzungen Task 4:** alle alten Texte stehen wörtlich so in der Spec – Z. 85 (B1-Überschrift), 93 (Tabellenzeile `versions`), 95 (»Alle fünf tragen«), 286 (`"schema": 1,`), 293–295 (`settings`-Block, Einrückung zwei Leerzeichen wie im Plan), 328 (`bytes_allocated`-Zeile), 363 und 367 (Test-Plan); `status.md:227`. Die Spec endet mit einer Aufzählungszeile und Zeilenumbruch; das Anfügen des Nachtrags ist unproblematisch. Siehe H3 für die zwei übrigen »fünf«.

---

## Prüfpunkt 1 – Befunde aus Runde 1

| Review | Befund | Status in Fassung 2 | Urteil |
|---|---|---|---|
| Terra | Opening pass baut den Index nicht zuverlässig (Hoch) | behoben – Abschluss-`survey()`, Test »fresh history« | trägt (Prüfpunkt 2) |
| Terra | Normal zurückkehrender Pass ist kein Nachweis (Hoch) | teilweise – `ensure`-Fehler → `started = None`; verschluckte Lese-/Schreibfehler werden gemessen; Terras explizites Pass-Ergebnis bewusst nicht gebaut | Umdeutung auf »bis indiziert« trägt; die Vertragsformulierung nicht → **W2** |
| Terra | Berichtsvertrag widersprüchlich (Hoch) | behoben – Beispiel, Regeltabelle, B1, Test-Plan an Ort und Stelle (Task 4 Step 1–3) | trägt |
| Terra | Integrationscheck verlangt `index is not None` und `seconds > 0` (Mittel) | teilweise – `>= 0` übernommen; `index is not None` bewusst beibehalten, begründet im Docstring (die Bank hat immer eine Historie) | Ablehnung trägt: auf der Bank wäre `null` ein Fehler |
| Terra | Container-Test prüft Schema nicht (Mittel) | behoben – exakte Blockmenge und `schema == 2` | trägt |
| Terra | B1-Eigenschaften des sechsten Sensors ungetestet (Mittel) | behoben – `entity_registry_rows`, Kategorie und Gerät gegen `versions` | trägt (Felder im Container nachgelesen) |
| Terra | End-to-End-Test für die Store-Semantik fehlt (Mittel) | behoben in der Sache – Tests 3 und 4; durch `first_index_build()` ist die Abgrenzung »Opening-Wert gegen späteren Storewert« gegenstandslos | trägt |
| Terra | Mehrversions-Prüfung nicht reproduzierbar (Niedrig) | behoben – generischer Ablauf ohne lokale Pfade (Z. 1077) | trägt |
| Gemini | `ensure`-/Schreibfehler → Zahl statt `unknown` (Hoch) | teilweise – `ensure` ja, Schreibfehler nein (bewusst) | wie Terra 2 → **W2** |
| Gemini | Frisches Repo, ein Dashboard → `index_build` dauerhaft `null` (Hoch) | behoben – Abschluss-`survey()`, Test 4 | trägt, bis auf das Fenster **W1** |
| Gemini | Block-Check und `schema == 2` in `run_checks.py` (Mittel) | behoben | trägt |
| Gemini | `index_build` nicht gegen den Bericht geprüft (Mittel) | behoben – Vergleich des ganzen `startup`-Dicts | trägt |
| Gemini | Regeltabelle ohne `startup`-Zeile (Niedrig) | behoben – Z. 1030 | trägt, Formulierung siehe W2 |
| Gemini | Zählung der roten Checks unpräzise (Niedrig) | behoben – sieben, nachgezählt | trägt |
| Astra | Fremde Zahl: `last_index_build` nimmt einen `forget`-Neubau (1) | behoben – `first_index_build()`, einmal gesetzt, Test 3 | trägt |
| Astra | Früher Panel-Bau vor der Reparatur; zweiter Bau nicht summiert (1) | bewusst so – »nur der erste zählt, `seconds` enthält beide« (Z. 29) | trägt; siehe H5 |
| Astra | Keine obere Grenze: letzter Write, frischer Store, kein `_has_history` (2) | behoben – Abschluss-`survey()` | trägt (Prüfpunkt 2) |
| Astra | Rewrite am Passende ohne Sperre (2) | bewusst abgelehnt – Aussage auf »solange kein gleichzeitiges `forget`« begrenzt, kein Abschluss unter `self._lock` | trägt: für eine Diagnosezahl ist ein neuer Sperrerwerb vom Startpfad unverhältnismäßig, die Begrenzung ist ausgesprochen; Formulierung siehe H1 |
| Astra | Zeit gespeichert vor `self._index = found` (2) | behoben durch Umkehr der Reihenfolge | **die Umkehr erzeugt W1**; die Sorge traf den einzigen Leser nicht |
| Astra | `_revision_index` liest HEAD vor dem Gate; das Gate synchronisiert keine HEAD-Änderung (2) | nicht adressiert – vorbestehend, unter dem `forget`-Vorbehalt | Ablehnung trägt |
| Astra | Abschlusszeit nicht nach dem `await`, Indexwert nicht separat live lesen (Korrektur) | nicht übernommen | Endzeit: H4, ohne Belang; Live-Lesen: **W1** |
| Gemini-Risiko | Teil 1 A: `forget` während des Passes bläht `seconds` auf und überschreibt den Bau | behoben für den Bau (`first_index_build`); `seconds` bewusst mitgezählt und so beschrieben | trägt |
| Gemini-Risiko | Teil 1 B: Panel baut früh, Index veraltet nach Writes | behoben – `survey()` verlängert; erster Bau gehört zum Start | trägt |
| Gemini-Risiko | Teil 2 A–C: letzter Write, Erststart, kein `_has_history` | behoben – Abschluss-`survey()` | trägt |
| Gemini-Risiko | Kleinste Änderung: `survey` im `try` | übernommen in eigener Funktion mit eigenem `try` (gleichwertig, plus `started is None`-Bedingung) | trägt |

---

## Positiv geprüft

Alle im Plan zitierten Codestellen stimmen wörtlich mit `5004421` überein (Konstruktor `686–688`, `_revision_index` `2695–2736`, `_timed_build` `2738–2757`, `capture.py:358/369`, `__init__.py:66–73/131–134/147–154`, `coordinator.py:79`, `sensor.py:1/16/131–137/156–160`, `report.py:25/90–97/121/146`, `diagnostics.py:53`, `test_report.py:31–43/71–73/82–84`, `run_checks.py:5020–5025/5060–5064/5105–5111/5138–5142`, `operations.py:418`, `store.py:1941`). `strings.json` und `translations/en.json` sind identisch und bleiben es nach Step 6. `_timed_build` hat genau einen Aufrufer. Die Behauptung »`survey()` wirft ohne Repository nicht« stimmt (Z. 3420–3421). `import time` fehlt in `__init__.py` und wird ergänzt; in `store.py` und `coordinator.py` ist es vorhanden. Die vier Commit-Botschaften halten Subject ≤ 50 Zeichen und Body ≤ 72.

## Urteil

**Umsetzbar nach Korrekturen.** Fassung 2 hat die Substanz von Runde 1 aufgenommen: Messpunkt, Erfolgsbedingung, Vertrag und Container-Prüfung sind repariert, die bewussten Ablehnungen sind begründet und tragen. Zu korrigieren vor der Umsetzung: W1 (Reihenfolge der beiden Zuweisungen in `_revision_index` tauschen, Kommentar und Plan Z. 56/79 anpassen – eine Zeile Code, das Fenster ist reproduziert) und W2 (Vertragszeile und Coordinator-Kommentar so formulieren, dass »Opening pass gescheitert« nur den Abbruch mit Ausnahme meint). H1–H3 sind Formulierungen, H4 und H5 brauchen nichts.

ENDE DES REVIEWS
