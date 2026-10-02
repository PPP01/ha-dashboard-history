# Startdauer als Diagnose-Sensor – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein sechster Diagnose-Sensor zeigt, wie lange ein Start der Integration gebraucht hat, bis die Historie für das Panel indiziert ist – mit der Bauzeit des Revisionsindex als Attribut und denselben zwei Zahlen im Diagnose-Bericht (GitHub #52).

**Architecture:** `HistoryStore` merkt sich die Dauer seines **ersten** vollständigen Indexbaus, einmal gesetzt. `_async_open` ruft nach dem Opening pass ausdrücklich `store.survey()` im Executor auf – das bringt den Index auf den HEAD nach dem letzten Schreibvorgang – und erst danach die Zeit seit Beginn von `async_setup_entry` und die erste Bauzeit am `MeasurementCoordinator` ab, vor der ersten Messung. Eine eigene kleine Entitätsklasse in `sensor.py` liest die beiden Felder; `report.build` nimmt sie als Block `startup` auf.

**Tech Stack:** Python 3.12–3.14, Home Assistant ≥ 2024.11 (getestet gegen 2026.8.3 im Container), `dulwich==1.2.14`, pytest.

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` (bindend), für Sensoren und Bericht `docs/superpowers/specs/2026-09-19-beobachten-design.md` (B1, B6, B10, »Der Vertrag des Berichts«, »Test-Plan«). Die erste Entscheidung über den Messpunkt steht im Kommentar zu #52 (<https://github.com/PPP01/ha-dashboard-history/issues/52#issuecomment-5946856877>); diese Fassung korrigiert sie nach Review-Runde 1 (siehe unten).

## Fassung 2 – was sich nach Review-Runde 1 geändert hat

Vier Reviews (`docs/superpowers/reviews/2026-10-02-startdauer-sensor-review-1-{terra,gemini,astra,gemini-risiko}.md`) haben gezeigt, dass Fassung 1 auf einer falschen Annahme stand: »der Opening pass baut den Index selbst«. Er tut es meistens, aber nicht immer, und nie für den HEAD nach seinem *letzten* Schreibvorgang:

- `_write_one` ruft `_has_history` **vor** `write_snapshot` auf (`capture.py:358`, `369`). Nach dem letzten Write steht HEAD einen Commit weiter, der Index noch auf dem alten. Mein Experiment in Fassung 1 hatte zusätzlich `survey()` aufgerufen – genau den Aufruf, der im Pass fehlt.
- Auf einer frischen Historie gibt es vor dem ersten Write kein HEAD, `_revision_index` liefert `None`, und bei nur einem Dashboard folgt kein zweiter Aufruf.
- Eine Historie, die nur noch gelöschte Dashboards enthält, oder ein Pass, der die Konfigurationen nicht lesen konnte, erreicht `_has_history` gar nicht.
- Ein Pass ohne Ausnahme ist kein Erfolg: `capture.py` schluckt Lese- und Schreibfehler (`184–186`, `244–246`), und `async_setup_entry` schluckt ein gescheitertes `store.ensure` (`66–73`).
- `last_index_build()` hätte den *letzten* Bau geliefert, also auch einen Neubau nach einem `forget`, der vor der Übernahme am Passende lief.

Daraus folgt diese Fassung: ein ausdrücklicher `survey()`-Abschluss mit Erfolgsbedingung, `first_index_build()` statt `last_index_build()`, keine Messung ohne Repository, und ein Berichtsvertrag, der an Ort und Stelle angepasst wird. Astras Vorschlag eines Abschluss-Helfers unter `self._lock` und `_index_gate` ist bewusst **nicht** übernommen: Er greift in die Sperr-Invarianten ein, die #42 erst festhalten will, und für eine Diagnosezahl ist das unverhältnismäßig. Stattdessen ist die Behauptung unten genau begrenzt.

Nach Review 2 (`docs/superpowers/reviews/2026-10-02-startdauer-sensor-review-2-fable.md`) außerdem: `_first_index_build` wird **vor** `self._index` gesetzt, nicht danach (W1). Der sperrfreie Schnellpfad in `_revision_index` hätte den Index sonst einem Leser zeigen können, für den die Zeit noch fehlt. Vertrag, Coordinator-Kommentar und Nachtrag sagen jetzt ausdrücklich, dass die Indizierung gemessen wird, nicht der Erfolg der Aufzeichnung (W2). Dazu kommen die Hinweise H1, H2, H3 und H5 als Präzisierungen im Text. Die Reihenfolge aus W1 kann einfädig kein Test festnageln; sie steht deshalb als Kommentar am Code.

## Was die Zahl verspricht – und was nicht

**`seconds`** ist die Zeit von Beginn `async_setup_entry` bis zu dem Moment, in dem `store.survey()` nach dem Opening pass zurückkehrt. `survey()` ist genau der Aufruf, den das Panel für seine Dashboard-Liste macht (`operations.py:418` → `store.dashboard_listing()` → `survey()`); es baut oder verlängert den Index für den dann aktuellen HEAD und legt die Übersicht in seinen Cache. Bis dahin war der Index also für das Panel fertig. **Das ist eine obere Grenze für die Wartezeit auf die Liste beim Start, solange kein gleichzeitiges `forget` die Historie umschreibt.** Ein `forget`, das einen Schreibvorgang des Passes überlappt, hält ihn an `self._lock` fest und verlängert die Zahl; es wird mitgezählt, nicht herausgerechnet. Eines, das nur den Abschluss-`survey()` überlappt, wird weder gezählt noch gebremst – `survey()` hält `self._lock` nicht –, und dasselbe gilt für einen Forget-Checkpoint, den `repair_pending_forget` nicht schließen konnte. Beides fällt unter den Vorbehalt eben. Eine Änderung oder ein `forget` *nach* dem Abschluss kann erneut Arbeit für das Panel erzeugen – keine einmal genommene Startzahl kann dafür eine Grenze sein.

**`index_build`** ist die Dauer des ersten vollständigen Indexbaus dieser Store-Instanz, gleich wer ihn auslöst – Opening pass, Abschluss-`survey()` oder ein früh geöffnetes Panel. Alle drei gehören zu den Kosten dieses Starts. Ein späterer Neubau (nach einem `forget`) überschreibt den Wert nicht. Wurden in einem Start zwei volle Bauten nötig (`repair_pending_forget` verwirft den Cache, `store.py:1941`), zählt nur der erste, auf dem HEAD, der zu dem Zeitpunkt galt – bei einem Bau vor der Reparatur also die noch unreparierte Historie; `seconds` enthält beide.

**Gemessen wird die Indizierung, nicht der Erfolg der Aufzeichnung.** Keine Zahl gibt es, wenn das Repository nicht angelegt oder das Abonnieren nicht gestartet werden konnte (`started = None`), wenn der Opening pass mit einer Ausnahme abbricht oder wenn `survey()` scheitert. Fehler, die der Pass je Dashboard protokolliert und übergeht (`capture.py:182–186`, `237–238`, `244–246`), verhindern die Zahl nicht: Die Historie ist dann trotzdem für das Panel indiziert, und genau das misst sie.

**Nicht gemessen:** Floor und erste Messung (`__init__.py:147-154`) – auf sie wartet das Panel nicht; die Zeit vor `async_setup_entry`; die übrige Arbeit in `async_dashboards` jenseits von `survey()`.

## Global Constraints

- `store.py` und `report.py` bleiben frei von Home Assistant – kein `import homeassistant`, auch nicht indirekt (`lint-imports` prüft das).
- Nichts darf den Start von Home Assistant blockieren; `_async_open` bleibt Hintergrund-Task, an `async_setup_entry` kommt nur ein `time.monotonic()` hinzu. Das zusätzliche `survey()` läuft im Executor, im Hintergrund-Task.
- Code, Kommentare, Docstrings, Log-Texte, Entitätsnamen, Commit-Messages: **Englisch**. Dieses Journal (Plan, `status.md`, Spec): Deutsch mit echten Umlauten und »…«.
- Commit-Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen, Präfix `[52] `; Body max. 72 Zeichen pro Zeile, erklärt das *Warum*. Die Attributionszeile fügt der Umsetzer selbst an.
- Der Bericht verrät nichts über die Installation: nur Zahlen, auf eine Zehntelsekunde gerundet. `schema` steigt bei jeder Änderung an der Form – hier von 1 auf 2.
- Komplexität darf nur sinken: `python3 tools/complexity_ratchet.py` muss grün bleiben, ohne dass die Baseline wächst.
- `strings.json` und `translations/en.json` bleiben identisch (`tests/test_integration_files.py::test_the_english_translation_is_the_strings_file`).
- Kein neuer Erwerb von `self._lock` und keine neue Sperrenfolge (siehe #42).

## Review Focus

1. **Ein Store, dessen Repository nicht angelegt werden konnte** – `survey()` wirft dort nicht, sondern liefert eine leere Übersicht (nachgeprüft am 2026-10-02). Ohne eigene Bedingung zeigte der Sensor die Dauer eines Starts ohne Historie. Abgedeckt: `started` wird `None`, wenn `store.ensure` scheitert, und `_async_open` misst dann nicht (Task 2, Schritt 5). Im Container nicht provozierbar.
2. **Eine fehlgeschlagene erste Messung** – der Sensor zeigt seine Zahl trotzdem, nicht »unavailable«; das überschriebene `available` (Task 2). Im Container nicht provozierbar.
3. **Ein Neubau nach einem `forget`** überschreibt `index_build` nicht – `first_index_build()` (Task 1, Test mit erzwungenem Neubau).
4. **Eine frische Historie mit genau einem Dashboard** – der Abschluss-`survey()` baut den Index für den ersten Commit; `index_build` ist eine Zahl, nicht dauerhaft `null` (Task 1, Test »fresh history«).
5. **Ein Reload** misst seinen eigenen Start neu: neuer Store, neuer Coordinator, neue Zeitmarke (Task 2, `run_checks` nach dem Reload).

## Dateien

| Datei | Änderung |
|---|---|
| `custom_components/dashboard_history/store.py` | `_timed_build` liefert die Dauer mit; `_revision_index` setzt `_first_index_build` einmal, vor dem Veröffentlichen von `_index`; Getter `first_index_build()` |
| `custom_components/dashboard_history/coordinator.py` | Felder `startup_seconds`, `startup_index_seconds` |
| `custom_components/dashboard_history/__init__.py` | Zeitmarke in `async_setup_entry` (`None` bei gescheitertem `ensure`), Abschluss `_async_time_the_start` nach dem Opening pass |
| `custom_components/dashboard_history/sensor.py` | Klasse `StartupTime`, Helfer `_device_info`, sechs statt fünf Entitäten |
| `custom_components/dashboard_history/strings.json`, `translations/en.json` | Name `startup` → »Startup time« |
| `custom_components/dashboard_history/report.py` | Block `startup`, `SCHEMA = 2` |
| `custom_components/dashboard_history/diagnostics.py` | reicht die beiden Coordinator-Felder an `report.build` |
| `tests/test_store.py`, `tests/test_report.py` | neue bzw. angepasste Tests |
| `tests/integration/run_checks.py` | Registry-Zeilen, sechs Sensoren, Startdauer nach Start und Reload, Kategorie und Gerät, Berichtsblöcke und Schema, Bericht gegen Sensor |
| `docs/superpowers/specs/2026-09-19-beobachten-design.md` | B1, Vertrag (Beispiel und Regeln), Test-Plan an Ort und Stelle, dazu ein Nachtrag |
| `docs/superpowers/status.md` | Modultabelle |

**Bewusst nicht:** den Index auf Platte legen; die Wartezeit im Browser messen; Floor und erste Messung mitzählen; die Zeit vor `async_setup_entry`; `state_class` (keine Langzeitstatistik); ein Abschluss unter `self._lock`; ein `CHANGELOG.md`-Eintrag – der entsteht mit dem nächsten Release.

---

### Task 1: Der Store merkt sich die Dauer seines ersten vollen Indexbaus

**Files:**
- Modify: `custom_components/dashboard_history/store.py` (Konstruktor um Zeile 686–688, `_revision_index` um Zeile 2695–2736, `_timed_build` um Zeile 2738–2757, danach `index_warming`)
- Test: `tests/test_store.py` (nach `test_building_the_index_is_logged_with_its_size_and_time`)

**Interfaces:**
- Produces: `HistoryStore.first_index_build() -> float | None` – Sekunden des ersten vollständigen Baus dieser Instanz, `None` vor dem ersten. Weder ein Verlängern über `_extended_index` noch ein späterer voller Neubau ändert den Wert. Er wird gesetzt, **bevor** `self._index` veröffentlicht wird: Über den sperrfreien Schnellpfad in `_revision_index` (`store.py:2721–2723`) kann ein anderer Thread den veröffentlichten Index sofort sehen, und der Abschluss-`survey()` darf dann keine fehlende Zeit vorfinden (Review 2, W1).
- Intern geändert: `HistoryStore._timed_build(repo, head) -> tuple[RevisionIndex, float]` (einziger Aufrufer ist `_revision_index`, `store.py:2734`).

- [ ] **Step 1: Failing tests schreiben**

In `tests/test_store.py` direkt nach der Funktion `test_building_the_index_is_logged_with_its_size_and_time` einfügen. Sie endet mit der Zeile `assert not [r for r in caplog.records if "revision index" in r.getMessage()]`, nicht schon mit `assert len(lines) == 1`:

```python
def test_the_store_keeps_how_long_its_first_full_build_took(store):
    """For the startup sensor: the log line says it once, this keeps it."""
    assert store.first_index_build() is None
    store.write_snapshot("home", "a: 1\n", "home first")
    store.survey()
    took = store.first_index_build()
    assert took is not None and took >= 0


def test_extending_the_index_leaves_the_build_time_alone(store):
    """A write after the build only extends the index, and costs no start."""
    store.write_snapshot("home", "a: 1\n", "home first")
    store.survey()
    took = store.first_index_build()
    store.write_snapshot("home", "a: 2\n", "home second")
    store.survey()
    assert store.first_index_build() == took


def test_a_later_full_rebuild_leaves_the_first_build_time_alone(
    store, monkeypatch, caplog
):
    """A `forget` drops the cache and the next reader builds again.

    That rebuild is the forget's cost, not the start's. The second build
    is slowed down so that its time cannot coincide with the first.
    """
    import logging
    import time

    store.write_snapshot("home", "a: 1\n", "home first")
    store.survey()
    first = store.first_index_build()
    real = store._built_index

    def slow(repo, head):
        time.sleep(0.05)
        return real(repo, head)

    monkeypatch.setattr(store, "_built_index", slow)
    # What `forget` does to the cache before it rewrites (store.py:1808).
    store._index = None
    # `list_changes`, not `survey`: the survey has a cache of its own,
    # keyed by HEAD, and would answer from it without touching the index.
    with caplog.at_level(logging.INFO):
        store.list_changes("home", limit=1)
    assert any("Built the revision index" in r.getMessage() for r in caplog.records)
    assert store.first_index_build() == first


def test_a_fresh_history_gets_its_index_from_the_survey_after_its_first_write(store):
    """The opening pass on a fresh history with one dashboard.

    `_has_history` runs before the write, finds no HEAD and builds
    nothing; nothing reads after the write. Only the survey that
    `_async_open` runs after the pass builds the index the panel needs.
    """
    assert store.list_changes("home", limit=1) == []
    store.write_snapshot("home", "a: 1\n", "home first")
    assert store.first_index_build() is None
    store.survey()
    assert store.first_index_build() is not None
```

- [ ] **Step 2: Rot sehen**

Run: `python3 -m pytest tests/test_store.py -k "first_full_build or build_time_alone or first_build_time_alone or fresh_history_gets" -v -p no:cacheprovider`
Expected: alle vier FAIL mit `AttributeError: 'HistoryStore' object has no attribute 'first_index_build'`.

- [ ] **Step 3: Umsetzen**

Im Konstruktor direkt nach `self._index_warming = False`:

```python
        # How long the first full build of `_index` took, in seconds, or
        # None before it. Set once and never again: a rebuild after a
        # `forget` is that forget's cost, and the startup sensor wants
        # this start's. See `_revision_index`.
        self._first_index_build: float | None = None
```

In `_revision_index` den Block unter dem Gate

```python
            found = None
            if cached is not None:
                found = self._extended_index(repo, cached, head)
            if found is None:
                found = self._timed_build(repo, head)
            self._index = found
            return found
```

ersetzen durch:

```python
            found = None
            if cached is not None:
                found = self._extended_index(repo, cached, head)
            took = None
            if found is None:
                found, took = self._timed_build(repo, head)
            # Before `_index` is published, not after: the fast path above
            # hands the index out without the gate, so a reader can see it
            # the moment it is set - and the time must be there by then.
            if took is not None and self._first_index_build is None:
                self._first_index_build = took
            self._index = found
            return found
```

`_timed_build` ersetzen durch:

```python
    def _timed_build(self, repo: Repo, head: str) -> tuple[RevisionIndex, float]:
        """The full build, said aloud, flagged while it runs, and timed.

        Once per start on an installation nobody has rewritten, and it is
        the slowest thing the panel waits for: the line is what tells a
        slow start from a slow anything else.
        """
        self._index_warming = True
        started = time.monotonic()
        try:
            found = self._built_index(repo, head)
        finally:
            self._index_warming = False
        took = time.monotonic() - started
        _LOGGER.info(
            "Built the revision index: %d commits, %d dashboards in %.1f s",
            len(found.order),
            len(found.by_key),
            took,
        )
        return found, took
```

Direkt nach `index_warming`:

```python
    def first_index_build(self) -> float | None:
        """Seconds the first full build of the revision index took, or None."""
        return self._first_index_build
```

- [ ] **Step 4: Grün sehen**

Run: `python3 -m pytest tests/test_store.py tests/test_store_concurrency.py -q -p no:cacheprovider`
Expected: `0 failed`, darunter die vier neuen und `test_building_the_index_is_logged_with_its_size_and_time` unverändert.

Run: `python3 tools/complexity_ratchet.py`
Expected: grün (`_revision_index` wächst um zwei Zweige und bleibt unter dem Grenzwert 10).

- [ ] **Step 5: Commit**

```bash
git add custom_components/dashboard_history/store.py tests/test_store.py
git commit -m "[52] Keep how long the first index build took" -m "The log line names the build time once per start and is gone when
the log rotates. A startup sensor needs the number itself, so the
store keeps the duration of its first full build. A later rebuild
after a forget is that forget's cost and does not replace it. The
value is set before the index is published, because readers see the
index through a fast path without the gate."
```

---

### Task 2: Startdauer messen und als sechsten Sensor zeigen

**Files:**
- Modify: `custom_components/dashboard_history/coordinator.py` (Konstruktor, nach `self.measured_at`)
- Modify: `custom_components/dashboard_history/__init__.py` (Imports, `async_setup_entry`, `_async_open`, neue Funktion `_async_time_the_start`)
- Modify: `custom_components/dashboard_history/sensor.py`
- Modify: `custom_components/dashboard_history/strings.json`, `custom_components/dashboard_history/translations/en.json`
- Test: `tests/integration/run_checks.py` (Helfer bei `entity_ids`/`entity_attributes`, Abschnitt »Das Beobachten: Sensoren und Bericht«)

**Interfaces:**
- Consumes: `HistoryStore.first_index_build() -> float | None` (Task 1), `HistoryStore.survey()` (vorhanden).
- Produces: `MeasurementCoordinator.startup_seconds: float | None`, `MeasurementCoordinator.startup_index_seconds: float | None`; Entität mit Unique-ID `<entry_id>_startup`, Entity-ID `sensor.dashboard_history_startup_time`, Attribut `index_build`. In `run_checks.py`: `entity_registry_rows(access) -> dict[str, dict]`, `_seconds(value) -> float | None`, `check_startup_time(access, readings, when) -> None`.

`__init__.py` und `sensor.py` importieren Home Assistant und sind aus pytest nicht erreichbar – die Prüfung ist `run_checks.py` im Container (Aufbau und Fallstricke: `docker/README.md`). Deshalb zuerst eine Vergleichsbasis.

- [ ] **Step 1: Vergleichsbasis im Container**

```bash
docker compose -f docker/compose.yaml up -d
docker restart dashboard-history-test
python3 tests/integration/run_checks.py 2>&1 | tee /tmp/run-checks-before.txt | tail -5
```

Die Namen der roten Checks festhalten: `grep FAIL /tmp/run-checks-before.txt | sed 's/  — .*//' > /tmp/fail-before.txt`. Hinter `—` stehen Messwerte, die von Lauf zu Lauf wechseln; verglichen wird deshalb nur über die Namen. Was hier schon rot ist, liegt am Zustand der Prüfbank und ist nicht Gegenstand dieses Plans.

- [ ] **Step 2: Failing Checks in `run_checks.py` schreiben**

`entity_ids` ersetzen durch die beiden folgenden Funktionen – die zweite ist die alte, jetzt auf der ersten:

```python
def entity_registry_rows(access: str) -> dict[str, dict]:
    """This integration's registry rows, by the key in their unique id.

    Through the entity registry rather than by writing the ids out,
    because an entity_id is derived from the entity's *name* and not
    from its description key: the reading keyed `revisions` is called
    "Recorded states" and therefore lands at
    `sensor.dashboard_history_recorded_states`. Ids written by hand
    would break silently the first time a label is reworded.

    `config/entity_registry/list` does carry `unique_id`, although the
    websocket module never mentions the word - the field comes out of
    `RegistryEntry.as_partial_dict`, together with `entity_category`
    and `device_id`. Checked against 2026.8.3 rather than grepped for.
    """
    identifier = entry_id(access)

    async def ask() -> list:
        async with Socket(access) as socket:
            return await socket.call("config/entity_registry/list")

    prefix = f"{identifier}_"
    return {
        row["unique_id"][len(prefix):]: row
        for row in asyncio.run(ask())
        if row.get("config_entry_id") == identifier
        and str(row.get("unique_id", "")).startswith(prefix)
    }


def entity_ids(access: str) -> dict[str, str]:
    """This integration's readings, by the key in their unique id."""
    return {key: row["entity_id"] for key, row in entity_registry_rows(access).items()}
```

Direkt nach der Funktion `entity_attributes` einfügen:

```python
def _seconds(value) -> float | None:
    """A state or attribute as seconds, or None if it is not a number."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def check_startup_time(access: str, readings: dict[str, str], when: str) -> None:
    """The startup sensor holds seconds, and the index build fits inside them.

    `index_build` must be a number here, not `null`: the bench always
    has a history, so the survey that closes the start has built an
    index, and `null` would mean it did not run. It is part of the
    startup time, never more; both are rounded to a tenth, hence the
    slack of one.
    """
    entity = readings.get("startup")
    seconds = _seconds(entity_state(access, entity)) if entity else None
    index = (
        _seconds(entity_attributes(access, entity).get("index_build"))
        if entity
        else None
    )
    check(
        f"the startup time is a number of seconds ({when})",
        seconds is not None and seconds >= 0,
        f"state={seconds}",
    )
    check(
        f"the index build fits inside the startup time ({when})",
        seconds is not None and index is not None and 0 <= index <= seconds + 0.1,
        f"startup={seconds} index_build={index}",
    )
```

Den Registrierungs-Check ersetzen:

```python
    readings = entity_ids(access)
    check(
        "all five readings are registered",
        set(readings) == {"last_capture", "size", "revisions", "dashboards", "versions"},
        f"got {sorted(readings)}",
    )
```

durch:

```python
    rows = entity_registry_rows(access)
    readings = {key: row["entity_id"] for key, row in rows.items()}
    check(
        "all six readings are registered",
        set(readings)
        == {"last_capture", "size", "revisions", "dashboards", "versions", "startup"},
        f"got {sorted(readings)}",
    )
    # Its own class, not a `Reading`, so the category and the device are
    # set in a second place - checked against a reading that has them.
    startup_row = rows.get("startup", {})
    check(
        "the startup reading is diagnostic and on the readings' device",
        startup_row.get("entity_category") == "diagnostic"
        and startup_row.get("device_id") is not None
        and startup_row.get("device_id") == rows.get("versions", {}).get("device_id"),
        f'category={startup_row.get("entity_category")} '
        f'device={startup_row.get("device_id")}',
    )
    check_startup_time(access, readings, "after the start")
```

Den Reload-Check ersetzen:

```python
    check(
        "a reload leaves exactly the five readings, none orphaned",
        set(after) == set(readings) and standing == 5,
        f"{sorted(after)} / {standing}",
    )
```

durch:

```python
    check(
        "a reload leaves exactly the six readings, none orphaned",
        set(after) == set(readings) and standing == 6,
        f"{sorted(after)} / {standing}",
    )
    # After the wait above, and that is enough: `_async_open` sets the
    # startup time before the first measurement, so a `revisions` that
    # is no longer `unknown` means the startup time is in too.
    check_startup_time(access, after, "after a reload")
```

- [ ] **Step 3: Rot sehen**

Run: `python3 tests/integration/run_checks.py 2>&1 | tee /tmp/run-checks-red.txt | grep -E "six readings|startup|index build"`
Expected: sieben FAIL – `all six readings are registered`, `the startup reading is diagnostic and on the readings' device`, je zweimal `the startup time is a number of seconds` und `the index build fits inside the startup time` (»after the start« und »after a reload«), `a reload leaves exactly the six readings, none orphaned`. Sonst gegenüber Step 1 nichts neu rot.

- [ ] **Step 4: Coordinator-Felder**

In `coordinator.py`, Konstruktor, direkt nach `self.measured_at: float | None = None`:

```python
        # How long this entry took from the start of `async_setup_entry`
        # until its history was indexed for the panel, and how long the
        # first full build of the revision index took within that. Set
        # once by `_async_open`, before the first measurement, so the
        # refresh that follows writes them to the entities.
        #
        # None until then, and None for good if the start could not be
        # timed - recording that could not start, an opening pass that
        # raised, or a closing survey that failed. Errors the pass logs
        # and skips per dashboard do not count: this times the indexing,
        # not the recording.
        self.startup_seconds: float | None = None
        self.startup_index_seconds: float | None = None
```

- [ ] **Step 5: Zeitmarke, Bedingung und Abschluss in `__init__.py`**

Import ergänzen (nach `import logging`):

```python
import time
```

In `async_setup_entry` als erste Anweisung nach dem Docstring:

```python
    # Taken first, so the startup sensor counts everything this entry
    # does before its history is usable - and nothing Home Assistant did
    # before it got here. None below if the recording could not start -
    # no repository, or no subscription: such a start is not timed.
    started: float | None = time.monotonic()
```

Den Block um `store.ensure`

```python
    try:
        await hass.async_add_executor_job(store.ensure)
        # Subscribing only, and that is the whole of what is awaited
        # here: it closes the window the opening pass opens, and it
        # costs nothing.
        capture.async_start()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
```

ersetzen durch:

```python
    try:
        await hass.async_add_executor_job(store.ensure)
        # Subscribing only, and that is the whole of what is awaited
        # here: it closes the window the opening pass opens, and it
        # costs nothing.
        capture.async_start()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
        # A survey of a store without a repository answers an empty
        # list rather than raising, so the closing step could not tell.
        started = None
```

Den Aufruf im Hintergrund-Task erweitern:

```python
        _async_open(hass, entry, store, capture, milestones, coordinator, started),
```

Signatur von `_async_open` erweitern:

```python
async def _async_open(
    hass: HomeAssistant,
    entry: ConfigEntry,
    store: HistoryStore,
    capture: HistoryCapture,
    milestones: Milestones,
    coordinator: MeasurementCoordinator,
    started: float | None,
) -> None:
```

Den Block um den Opening pass

```python
    try:
        await capture.async_opening_pass()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
```

ersetzen durch:

```python
    try:
        await capture.async_opening_pass()
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not start recording")
    else:
        if started is not None:
            await _async_time_the_start(hass, store, coordinator, started)
```

Direkt nach `_async_open` (vor `async_unload_entry`) einfügen:

```python
async def _async_time_the_start(
    hass: HomeAssistant,
    store: HistoryStore,
    coordinator: MeasurementCoordinator,
    started: float,
) -> None:
    """Index the history for the panel, then say how long the start took.

    The opening pass does not leave the index ready on its own: it asks
    `_has_history` before each write, so the last write moves HEAD past
    the index, and a fresh history, one with only deleted dashboards or
    a pass that could not read the configurations never builds it at
    all. `survey` is what the panel asks for its list. Run here, the
    panel finds it cached, and the time taken after it is an upper bound
    for the panel's wait at start - unless a `forget` rewrites the
    history meanwhile, which is then counted in. See #52.
    """
    try:
        await hass.async_add_executor_job(store.survey)
    except Exception:  # noqa: BLE001
        _LOGGER.exception("Dashboard History could not index its history")
        return
    coordinator.startup_seconds = time.monotonic() - started
    coordinator.startup_index_seconds = store.first_index_build()
```

- [ ] **Step 6: Übersetzung**

In `strings.json` **und** `translations/en.json` den Eintrag `versions` unter `entity.sensor` ersetzen:

```json
      "versions": {
        "name": "Versions"
      }
```

durch:

```json
      "versions": {
        "name": "Versions"
      },
      "startup": {
        "name": "Startup time"
      }
```

- [ ] **Step 7: Sensor**

In `sensor.py`:

Modul-Docstring `"""What the history costs and holds, as five diagnostic entities."""` ersetzen durch:

```python
"""What the history costs and holds, and how long it took to start.

Six diagnostic entities: five readings of a measurement, and the time
the last start took until the history was indexed.
"""
```

Import erweitern:

```python
from homeassistant.const import EntityCategory, UnitOfInformation, UnitOfTime
```

Vor `async_setup_entry` einen Helfer einfügen, damit beide Klassen dasselbe Gerät melden:

```python
def _device_info(entry: ConfigEntry) -> DeviceInfo:
    """The one device every entity of this integration hangs off."""
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Dashboard History",
        entry_type=DeviceEntryType.SERVICE,
    )
```

`async_setup_entry` ersetzen durch:

```python
async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback
) -> None:
    """Put the six readings up."""
    coordinator: MeasurementCoordinator = hass.data[DOMAIN]["coordinator"]
    add(
        [
            *(HistoryReading(coordinator, entry, reading) for reading in READINGS),
            StartupTime(coordinator, entry),
        ]
    )
```

In `HistoryReading.__init__` die Zuweisung

```python
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name="Dashboard History",
            entry_type=DeviceEntryType.SERVICE,
        )
```

ersetzen durch:

```python
        self._attr_device_info = _device_info(entry)
```

Am Dateiende anfügen:

```python
class StartupTime(CoordinatorEntity[MeasurementCoordinator], SensorEntity):
    """How long this start took until the history was indexed.

    Not a `Reading`: those read a `Measurement`, which `store.measure()`
    takes on a timer. A start is timed once, by `_async_open`, and the
    measurement has no part in it - a field on `Measurement` would be
    carried along by every measurement without being measured by any.
    """

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "startup"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator: MeasurementCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_startup"
        self._attr_device_info = _device_info(entry)

    @property
    def available(self) -> bool:
        """Always.

        The other readings go unavailable with a failed measurement,
        because their numbers come from it. This one does not, and a
        start that was timed stays timed.
        """
        return True

    @property
    def native_value(self) -> float | None:
        """Seconds until the history was indexed, or None before that."""
        seconds = self.coordinator.startup_seconds
        return None if seconds is None else round(seconds, 1)

    @property
    def extra_state_attributes(self) -> dict:
        """The first index build's share - whether it is the main cost."""
        index = self.coordinator.startup_index_seconds
        return {"index_build": None if index is None else round(index, 1)}
```

- [ ] **Step 8: Schnelle Prüfungen ohne Container**

```bash
python3 -m py_compile custom_components/dashboard_history/__init__.py custom_components/dashboard_history/sensor.py custom_components/dashboard_history/coordinator.py
python3 -m pytest tests/test_integration_files.py -q -p no:cacheprovider
python3 tools/complexity_ratchet.py
lint-imports
```

Expected: keine Ausgabe von `py_compile`; Tests grün; Ratchet und `lint-imports` grün.

- [ ] **Step 9: Grün im Container**

```bash
docker restart dashboard-history-test
python3 tests/integration/run_checks.py 2>&1 | tee /tmp/run-checks-after.txt | grep -E "six readings|startup|index build"
grep FAIL /tmp/run-checks-after.txt | sed 's/  — .*//' > /tmp/fail-after.txt
diff /tmp/fail-before.txt /tmp/fail-after.txt
docker logs dashboard-history-test 2>&1 | grep "Built the revision index" | tail -1
```

Expected: die sieben Checks aus Step 3 grün; `diff` zeigt keine neu roten Namen (fehlende Zeilen sind in Ordnung). `index_build` liegt in der Größenordnung der letzten Logzeile.

- [ ] **Step 10: Commit**

```bash
git add custom_components/dashboard_history/__init__.py custom_components/dashboard_history/coordinator.py custom_components/dashboard_history/sensor.py custom_components/dashboard_history/strings.json custom_components/dashboard_history/translations/en.json tests/integration/run_checks.py
git commit -m "[52] Show the startup time as a sensor" -m "After a restart the panel waits for the revision index, and how long
that takes was only in the log. The opening pass does not leave the
index ready for the HEAD its last write made, so the start closes with
the survey the panel asks for; the time taken after it bounds the
panel's wait unless a forget rewrites the history meanwhile.

A start without a repository is not timed: its survey answers an
empty list and could not tell. Its own entity class rather than a
Reading - the number comes from the start, not from a measurement,
and it stays available when one fails."
```

---

### Task 3: Die Startdauer im Diagnose-Bericht

**Files:**
- Modify: `custom_components/dashboard_history/report.py` (`SCHEMA`, `build`, neuer Helfer `_startup`)
- Modify: `custom_components/dashboard_history/diagnostics.py`
- Test: `tests/test_report.py`, `tests/integration/run_checks.py`

**Interfaces:**
- Consumes: `MeasurementCoordinator.startup_seconds`, `MeasurementCoordinator.startup_index_seconds` (Task 2); `_seconds` aus `run_checks.py` (Task 2).
- Produces: `report.build(measurement, secret, *, daily_versions, measured_at, stale, startup_seconds: float | None, startup_index_seconds: float | None) -> dict` mit Block `"startup": {"seconds": float | None, "index_build": float | None}`; `report.SCHEMA == 2`.

- [ ] **Step 1: Failing tests schreiben**

In `tests/test_report.py` `built` ersetzen durch:

```python
def built(**kwargs):
    settings = dict(
        daily_versions=True,
        measured_at=1758196800.0,
        stale=False,
        startup_seconds=12.34,
        startup_index_seconds=9.87,
    )
    settings.update(kwargs)
    return report.build(FACTS, SECRET, **settings)
```

`test_the_four_blocks_are_all_there` ersetzen durch:

```python
def test_the_blocks_are_all_there():
    body = built()
    assert set(body) == {
        "schema", "measured_at", "stale",
        "environment", "settings", "startup", "totals", "dashboards",
    }


def test_the_schema_counts_the_startup_block():
    # The shape changed, so the number did: reports from both versions
    # end up in the same issue threads and must stay apart.
    assert built()["schema"] == 2


def test_the_startup_time_is_reported_to_a_tenth():
    assert built()["startup"] == {"seconds": 12.3, "index_build": 9.9}


def test_a_start_not_yet_timed_reports_nulls():
    body = built(startup_seconds=None, startup_index_seconds=None)
    assert body["startup"] == {"seconds": None, "index_build": None}
```

In `test_an_empty_history_reports_honest_zeros` den Aufruf

```python
    body = report.build(
        Measurement(), SECRET, daily_versions=False, measured_at=1758196800.0, stale=False
    )
```

ersetzen durch:

```python
    body = report.build(
        Measurement(),
        SECRET,
        daily_versions=False,
        measured_at=1758196800.0,
        stale=False,
        startup_seconds=0.4,
        startup_index_seconds=None,
    )
```

und am Testende anfügen:

```python
    # No commit, no index to build - but the start was still timed.
    assert body["startup"] == {"seconds": 0.4, "index_build": None}
```

In `test_never_measured_is_not_the_same_as_measured_and_empty` den Aufruf

```python
    body = report.build(
        None, SECRET, daily_versions=False, measured_at=None, stale=True
    )
```

ersetzen durch:

```python
    body = report.build(
        None,
        SECRET,
        daily_versions=False,
        measured_at=None,
        stale=True,
        startup_seconds=12.34,
        startup_index_seconds=9.87,
    )
```

und am Testende anfügen:

```python
    # A start is timed whether or not the measurement after it worked.
    assert body["startup"] == {"seconds": 12.3, "index_build": 9.9}
```

- [ ] **Step 2: Rot sehen**

Run: `python3 -m pytest tests/test_report.py -q -p no:cacheprovider`
Expected: alle Tests, die über `built()` oder die beiden geänderten Aufrufe laufen, FAIL mit `TypeError: build() got an unexpected keyword argument 'startup_seconds'`.

- [ ] **Step 3: Umsetzen**

In `report.py` `SCHEMA = 1` → `SCHEMA = 2`.

Vor `def build(` einfügen:

```python
def _startup(seconds: float | None, index_seconds: float | None) -> dict:
    """How long the start took until indexed, and the first build's share.

    To a tenth of a second: what a start costs, not when it happened.
    """
    return {
        "seconds": None if seconds is None else round(seconds, 1),
        "index_build": None if index_seconds is None else round(index_seconds, 1),
    }
```

Signatur von `build` erweitern:

```python
def build(
    measurement,
    secret: str,
    *,
    daily_versions: bool,
    measured_at: float | None,
    stale: bool,
    startup_seconds: float | None,
    startup_index_seconds: float | None,
) -> dict:
```

In **beiden** zurückgegebenen Dicts direkt nach `"settings": {"daily_versions": daily_versions},` einfügen, eingerückt wie die Nachbarzeile:

```python
            "startup": _startup(startup_seconds, startup_index_seconds),
```

In `diagnostics.py` im Aufruf `report.build(...)` nach `stale=not coordinator.last_update_success,` einfügen:

```python
        # Taken once, when the start was indexed - independent of
        # whether the refresh above worked.
        startup_seconds=coordinator.startup_seconds,
        startup_index_seconds=coordinator.startup_index_seconds,
```

- [ ] **Step 4: Grün sehen**

Run: `python3 -m pytest tests/test_report.py -q -p no:cacheprovider`
Expected: `0 failed`, auch `test_no_dashboard_name_survives_into_the_report`.

- [ ] **Step 5: Bericht gegen Sensor im Container**

In `run_checks.py` den Block-Check

```python
    check(
        "the report carries all four blocks",
        {"environment", "settings", "totals", "dashboards"} <= set(body),
        f"got {sorted(body)}",
    )
```

ersetzen durch:

```python
    # The exact set, not a subset: a missing block is what a subset
    # check lets through, and the schema has to move with the shape.
    check(
        "the report carries exactly its blocks, schema 2",
        set(body)
        == {
            "schema", "measured_at", "stale",
            "environment", "settings", "startup", "totals", "dashboards",
        }
        and body.get("schema") == 2,
        f"got {sorted(body)} schema={body.get('schema')}",
    )
```

Direkt nach dem Check `"the sensors show what the report says"` einfügen:

```python
    startup_entity = readings.get("startup")
    startup_state = (
        _seconds(entity_state(access, startup_entity)) if startup_entity else None
    )
    startup_index = (
        _seconds(entity_attributes(access, startup_entity).get("index_build"))
        if startup_entity
        else None
    )
    check(
        "the report carries the startup time the sensor shows",
        startup_state is not None
        and body.get("startup") == {"seconds": startup_state, "index_build": startup_index},
        f'report={body.get("startup")} sensor={startup_state}/{startup_index}',
    )
```

```bash
docker restart dashboard-history-test
python3 tests/integration/run_checks.py 2>&1 | tee /tmp/run-checks-report.txt | grep -E "startup|exactly its blocks|no dashboard name"
grep FAIL /tmp/run-checks-report.txt | sed 's/  — .*//' > /tmp/fail-report.txt
diff /tmp/fail-before.txt /tmp/fail-report.txt
```

Expected: `the report carries exactly its blocks, schema 2` und `the report carries the startup time the sensor shows` grün, beide Datenschutz-Checks (`no dashboard name appears …`) grün, `diff` ohne neu rote Namen.

- [ ] **Step 6: Commit**

```bash
git add custom_components/dashboard_history/report.py custom_components/dashboard_history/diagnostics.py tests/test_report.py tests/integration/run_checks.py
git commit -m "[52] Report the startup time" -m "Sensors stay on the installation; the diagnostics report is how
numbers from other installations come back. Two figures rounded to a
tenth of a second say nothing about the dashboards. The shape of the
report changed, so its schema goes to 2, and the live check now
compares the exact set of blocks instead of a subset."
```

---

### Task 4: Spec und Journal nachziehen, alles einmal durchlaufen

**Files:**
- Modify: `docs/superpowers/specs/2026-09-19-beobachten-design.md` (B1, »Der Vertrag des Berichts«, »Test-Plan«, Nachtrag am Ende)
- Modify: `docs/superpowers/status.md` (Modultabelle)

**Interfaces:**
- Consumes: alles aus Task 1–3.
- Produces: nichts Neues.

- [ ] **Step 1: B1 an Ort und Stelle**

In `docs/superpowers/specs/2026-09-19-beobachten-design.md`:

`### B1 – Fünf Sensoren, Detailzahlen als Attribute` → `### B1 – Sechs Sensoren, Detailzahlen als Attribute`

Nach der Tabellenzeile

```markdown
| `sensor.dashboard_history_versions` | Anzahl Marken | `measurement` | Tagesversionen an/aus |
```

einfügen:

```markdown
| `sensor.dashboard_history_startup_time` | Sekunden bis zur Indizierung beim letzten Start (seit #52, siehe Nachtrag 2026-10-02) | `duration` | Dauer des ersten vollen Indexbaus (`index_build`) |
```

Im Satz unter der Tabelle die Wörter `Alle fünf tragen` durch `Alle sechs tragen` ersetzen; der Rest des Satzes bleibt.

- [ ] **Step 2: Vertrag des Berichts an Ort und Stelle**

Im JSON-Beispiel `"schema": 1,` → `"schema": 2,` und nach dem Block

```json
  "settings": {
    "daily_versions": true
  },
```

einfügen:

```json
  "startup": {
    "seconds": 13.4,
    "index_build": 9.5
  },
```

In der Regeltabelle die Zeile

```markdown
| `bytes_allocated` | `null` auf Plattformen ohne `st_blocks` (siehe B2). Alle anderen Zahlfelder sind nie `null`. |
```

ersetzen durch:

```markdown
| `bytes_allocated` | `null` auf Plattformen ohne `st_blocks` (siehe B2). Alle anderen Zahlfelder außer denen in `startup` sind nie `null`. |
| `startup` | Sekunden, auf eine Zehntel gerundet. `seconds`: von Beginn `async_setup_entry` bis `survey()` nach dem Opening pass zurückkehrt, also bis die Historie für das Panel indiziert ist. `index_build`: Dauer des ersten vollen Indexbaus dieses Starts, ein Teil von `seconds`. Beide `null`, solange der Start nicht abgeschlossen ist oder nicht gemessen werden konnte: Aufzeichnung nicht startbar (Repository nicht anlegbar, Abonnieren gescheitert), Opening pass mit einer Ausnahme abgebrochen oder `survey()` gescheitert. Fehler, die der Pass je Dashboard protokolliert und übergeht, verhindern die Zahlen nicht – gemessen wird die Indizierung, nicht der Erfolg der Aufzeichnung. `index_build` außerdem `null` auf einer Historie ohne Commit. |
```

- [ ] **Step 3: Test-Plan an Ort und Stelle**

Im Abschnitt »Test-Plan«, Teil `run_checks.py`, die Wörter `Die fünf Entitäten entstehen` durch `Die sechs Entitäten entstehen` ersetzen, und im Punkt »Ein Reload« die Wörter `weiterhin genau fünf Entitäten` durch `weiterhin genau sechs Entitäten`. Der Rest der beiden Sätze bleibt.

- [ ] **Step 4: Nachtrag am Ende der Spec**

Am Ende der Datei anfügen:

```markdown

## Nachtrag 2026-10-02: Startdauer als sechster Sensor (#52)

Seit #52 sind es sechs Sensoren; B1, der Vertrag des Berichts und der Test-Plan sind an Ort und Stelle angepasst. Der sechste, »Startup time«, misst von Beginn `async_setup_entry` bis `survey()` nach dem Opening pass zurückkehrt, und trägt die Dauer des ersten vollen Indexbaus als Attribut `index_build`. Das abschließende `survey()` ist nötig, weil der Opening pass den Index nicht für den HEAD seines letzten Schreibvorgangs bereitstellt und auf einer frischen Historie gar nicht baut. Die Zahl ist eine obere Grenze für die Wartezeit des Panels beim Start, solange kein gleichzeitiges `forget` die Historie umschreibt; ein `forget`, das einen Schreibvorgang des Passes überlappt, wird mitgezählt, eines, das nur den Abschluss überlappt, nicht. Gemessen wird die Indizierung, nicht der Erfolg der Aufzeichnung: Fehler, die der Pass je Dashboard übergeht, verhindern die Zahl nicht. Begründung und Review-Befunde: `plans/2026-10-02-startdauer-sensor.md`, `reviews/2026-10-02-startdauer-sensor-review-1-*.md` und `…-review-2-fable.md`.

Der sechste Sensor ist bewusst kein `Reading`: Seine Zahl stammt nicht aus `store.measure()`. Er bleibt deshalb verfügbar, wenn eine Messung scheitert – abweichend von »`measure()` wirft« unter »Fehler- und Randfälle«, das für die fünf Messwerte gilt. Ein Start, dessen Aufzeichnung nicht starten konnte, wird nicht gemessen. Die Begründung unter B1 (»Fünf Entitäten sind eine Geräteseite, die man liest; fünfzehn …«) und ihr Gegenstück im Docstring von `Reading` bleiben bewusst stehen: Sie meinen die Größenordnung, und mit sechs gilt dasselbe.

Der Bericht trägt dieselben zwei Zahlen als Block `startup`; `schema` steigt dafür von 1 auf 2.
```

- [ ] **Step 5: `status.md`**

Die Zeile

```markdown
| `sensor.py` | Fünf Diagnose-Sensoren (Größe, Stände, Dashboards, Versionen, Zeitstempel) |
```

ersetzen durch:

```markdown
| `sensor.py` | Sechs Diagnose-Sensoren (Größe, Stände, Dashboards, Versionen, Zeitstempel, Startdauer) |
```

- [ ] **Step 6: Volle Prüfung**

```bash
python3 -m pytest tests/ -q -p no:cacheprovider
python3 tools/complexity_ratchet.py
lint-imports
grep -rn "five readings\|fünf Sensoren\|Fünf Sensoren\|\"schema\": 1" custom_components/ tests/ docs/superpowers/specs/2026-09-19-beobachten-design.md docs/superpowers/status.md
```

Expected: `0 failed` (die Gesamtzahl schwankt mit der echten `.storage` und ist kein Kriterium); Ratchet und `lint-imports` grün; der `grep` findet nichts.

Optional, für weitere Python-Versionen: dieselbe Suite in einer eigenen Umgebung pro Version (außerhalb des Repositorys, mit `pytest`, `pyyaml` und `dulwich==1.2.14` wie in `.github/workflows/test.yml`), Aufruf `<interpreter> -m pytest tests/ -q -p no:cacheprovider`. Ohne solche Umgebungen deckt die CI 3.13 und 3.14 ab.

- [ ] **Step 7: Commit**

```bash
git add docs/superpowers/status.md docs/superpowers/specs/2026-09-19-beobachten-design.md
git commit -m "[52] Bring the observing spec to six sensors" -m "The spec promised five sensors and a report of schema 1, in its
table, its example and its test plan. All three are changed where
they stand rather than contradicted by an addendum at the end, which
says why the time is taken after a closing survey."
```
