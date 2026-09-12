# Der Vergleichsmodus — Umsetzungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das zeilenweise, automatisch mitlaufende Put-back (»Also missing since then«) aus der History-Detailansicht entfernen und durch einen bewussten Vergleichsmodus ersetzen, der zwei frei gewählte Stände (jede Änderung, jede Version, oder der aktuelle Zustand) gegenüberstellt — mit Put-back nur, wenn eine Seite der aktuelle Zustand ist.

**Architecture:** Eine neue, dünne Operation `async_compare` in `operations.py` vergleicht zwei beliebige Stände über die bereits vorhandene, revisionsunabhängige `_explain_texts` — als WS-Befehl und, wie jede andere Operation, als Dienst. Sie entscheidet auch, welche der beiden Seiten chronologisch älter ist (`store.commit_times`), weil das Panel das nicht immer selbst herausfinden kann. `deleted_since` und `restore_deleted` bleiben unverändert bestehen und werden nur an einen neuen Einstieg im Panel umgehängt: einen Vergleichsmodus mit Checkboxen an jeder Zeile — auch an Versionsköpfen — plus einem Pseudo-Eintrag »Aktueller Zustand«, der bei zwei Auswahlen einen Dialog öffnet. Verweigert der Undo einer Zeile, verweist die Verweigerung neu auf diesen Vergleichsmodus, vorbelegt mit Vorgänger-Stand und »Aktueller Zustand« — derselbe Weg zurück, den die Zeile bisher automatisch zeigte. Der alte Zeilen-Block wird erst entfernt, nachdem sein Ersatz komplett steht, damit kein Zwischenstand ohne Weg zurück existiert.

**Tech Stack:** Python 3.12 (Entwicklung) / 3.14 (Container), dulwich, Home Assistant 2026.8.3, Vanilla-JS-Webkomponente ohne Bauschritt (ES-Module, dynamisch geladen aus `panel/`).

**Spec:** `docs/superpowers/specs/2026-08-30-dashboard-history-design.md` — **Entscheidung 19** ist die Begründung dieses Plans; Entscheidung 5 (Alternativen benennen), 9 (Zustand vs. Änderung, »eine zu spät«), 13 (keine zweite Vergleichsmethode), 15 (die Weiche, deren Rückfallseite umzieht) und 17 (einfacher/erweiterter Modus) sind die Nachbarn.

## Global Constraints

Wörtlich aus Spec und `CLAUDE.md`, sie binden **jede** Aufgabe:

- **Kein Systemaufruf von `git`.** Ausschließlich `dulwich` — betrifft diesen Plan nur mittelbar, da `store.py` nicht geändert wird.
- **Keine Home-Assistant-Interna abfangen oder ersetzen.** Kein Monkey-Patching.
- **Nichts blockiert den Start von Home Assistant.** Fehler werden protokolliert und verschluckt.
- **`yaml_io.py`, `analyze.py`, `restore.py`, `versions.py`, `store.py`, `keys.py` bleiben Home-Assistant-frei.** Keines dieser sechs Module wird in diesem Plan angefasst.
- **Blockierende Arbeit gehört in einen Executor** (`hass.async_add_executor_job`) — `dump()`, `store.resolve`/`read_at`/`commit_times`/`same_state` und `_explain_texts()` insbesondere.
- **Jeder WebSocket-Befehl und jeder Dienst verlangt Administratorrechte.** Der `_command`-Helfer in `websocket_api.py` erzwingt das für jeden registrierten Befehl automatisch; `services.py` registriert jeden Eintrag seiner `registrations`-Liste über `async_register_admin_service`, ebenso automatisch.
- **Nichts wird ohne Vorschau geschrieben.** Put-back bleibt `restore_deleted` mit `confirm`, unverändert — dieser Plan fügt keinen neuen Schreibpfad hinzu.
- **Zeilen-Checkbox meint den Stand danach** (Entscheidung 19) — dieselbe Revision, die `restore_state`/`create_version` überall meinen.
- **Vergleichsmodus nur im erweiterten Modus** (Entscheidung 17/19) — der einfache Modus bekommt keine Checkboxen.
- **Keine zweite Vergleichsmethode für Inhaltsgleichheit**, wo `store.same_state` bereits eine liefert (Entscheidung 13) — nur für den Fall »eine Seite ist der aktuelle Zustand«, den `same_state` strukturell nicht abdeckt (kein Commit), ist Textgleichheit der bereits gedumpten Stände die richtige, nicht eine dritte Methode.
- **Sprache:** Code, Kommentare, Docstrings, Log-Meldungen und Commit-Botschaften auf Englisch. Dieser Plan ist Deutsch, weil er nach innen gehört.
- **Commit-Format:** Subject im Imperativ, erster Buchstabe groß, max. 50 Zeichen; Leerzeile; Body max. 72 Zeichen, begründet das *Warum*; Abschluss `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`.
- **Nicht schieben, nicht taggen, nicht veröffentlichen.** Nur auf ausdrückliche Ansage des Nutzers.
- **Der Prüfstand ist die Wegwerf-Instanz auf Port 8124.** Nie während eines HA-Neustarts anpollen; nie über ein Präfix löschen, nur über den genau benannten eigenen Schlüssel.
- **Nach jeder Python-Änderung Container neu starten**, sonst hält er das alte Modul im Speicher und `pytest` ist grün, während die Integration falsch läuft.
- **`panel/style.js` ist EIN Template-Literal.** Genau zwei Backticks in der Datei, kein `${`. `tests/test_panel_assets.py` wacht darüber.

## Ausgangslage

```text
pytest:      583 passed, 1 skipped
run_checks:  176 von 176
```

Gemessen am 2026-09-12, vor Beginn dieses Plans. Beides muss am Ende mindestens so dastehen, mit den neuen Fällen obendrauf. Der eine Skip ist der Realdaten-Test ohne `DASHBOARD_HISTORY_REAL_STORAGE` — erwartet, kein Befund.

## Nach unabhängigem Review überarbeitet

Eine zweite Claude-Session (»ha-dashboard-history-ab«) hat diesen Plan gegen den echten Code und die Spec geprüft und zehn Funde gemeldet. Jeder wurde hier selbst noch einmal nachvollzogen, bevor er übernommen wurde — Cross-Session-Nachrichten sind ein Kollegen-Hinweis, keine Freigabe. Bestätigt und eingearbeitet:

- **Task 1** löste ursprünglich beide Seiten über `_state_at` auf. Das widerspricht der Spec: der Randfall »eine Seite ist die Löschzeile eines gelöschten Dashboards« verlangt, dass der Vergleich dort möglich bleibt. Behoben — siehe die Warnung dort.
- **Die Reihenfolge der Sortierung** lag beim Panel (`_changes.findIndex`), das dafür aber nicht immer die nötigen Daten hat (eine Auswahl kann einen Refresh überleben, der ihre Zeile aus `_changes` wirft). Jetzt entscheidet `async_compare` selbst, über `store.commit_times`, und meldet das Ergebnis in `revision_a`/`revision_b`/`time_a`/`time_b` zurück.
- **Der Dialog nannte keine Daten und keine automatischen Meldungen je Seite** — die Spec verlangt das ausdrücklich (Entscheidung 19: »Stand nach ›2 removed‹ vom …«), als Absicherung gegen genau die Verwechslung, die Entscheidung 9 für den Einzelfall entfernt hat. Behoben in Aufgabe 3.
- **Versionsköpfe bekamen keine Checkbox**, obwohl die Spec »jede Änderung, jede benannte Version« verlangt. Behoben in Aufgabe 2.
- **`compare` fehlte als Dienst.** Die README verspricht unbedingt, alles, was das Panel tut, stehe auch als Dienst zur Verfügung. Behoben in Aufgabe 1.
- **Der Klick auf »Compare with the current state«** konnte bei schon aktivem Vergleichsmodus mit bestehender Auswahl den Dialog zweimal (mit falschem Paar zuerst) oder gar nicht öffnen. Behoben in Aufgabe 4 durch direktes Setzen des Zustands statt Umschalten.
- **Die Reihenfolge der Aufgaben** entfernte den alten Zeilen-Block, bevor sein Ersatz stand — ein verweigerter Undo hätte in den Zwischen-Commits keinen Weg zurück gehabt. Dieser Plan baut deshalb jetzt Vergleichsmodus, Dialog und Verweigerungs-Verweis zuerst und entfernt den alten Block als letzten fachlichen Schritt (Aufgabe 5).
- **README, `look_at_panel.py` und die `pytest -k`-Selektoren** in der Aufräum-Aufgabe waren unvollständig bzw. schlicht falsch (der Selektor traf keinen einzigen Test). Behoben in Aufgabe 5/6.

## Dateiübersicht

| Datei | Verantwortung nachher |
|---|---|
| `operations.py` | zusätzlich: `async_compare` |
| `websocket_api.py` | zusätzlich: Befehl `compare` |
| `services.py` / `services.yaml` | zusätzlich: Dienst `compare` |
| `panel.js` | Vergleichsmodus-Zustand (`_compareMode`, `_compareSelection`), `_toggleCompareMode`, `_toggleCompareRevision`, `_openCompare`; `_restoreItem` verallgemeinert von `(change, item)` auf `(revision, item)`; `_renderDetail`, `_detailCalls`, `_expand`, `_take`, `_clearDetail` verlieren den `deleted_since`-Teil; der `offer`-Block verweist bei Undo-Verweigerung auf den Vergleichsmodus |
| `panel/rows.js` | `renderRow` **und** `versionHead` bekommen eine Checkbox im Vergleichsmodus; neuer Export `currentStateRow()` für den Pseudo-Eintrag |
| `panel/dialogs.js` | neuer `<dialog class="compare">` |
| `panel/style.js` | Checkbox, Vergleichs-Umschalter, Dialog-Layout — reine Ergänzung, keine Umbenennung bestehender Klassen |
| `tests/test_panel_behaviour.py` | drei bestehende Szenarien angepasst (siehe Aufgabe 5), neue Szenarien für Auswahl, Dialog, Verweigerungs-Verweis |
| `tests/integration/run_checks.py` | `run_compare`, in den Dispatcher am Ende der Datei eingehängt |
| `tests/integration/look_at_panel.py` | die `putBack`-Zählung sucht im Dialog statt in der Zeile; die `_items`-Attrappe entfällt |
| `README.md` | Dienste-Tabelle um `compare` ergänzt; der Abschnitt zur gelöschten Section verweist auf den Vergleichsmodus; alle übrigen Put-back-Stellen, die die Zeilen-Logik beschreiben, nachgezogen |
| `docs/superpowers/status.md` | Vorhaben J von »Nicht begonnen« auf »Erledigt« |

---

## Task 1: Backend — `async_compare`

**Files:**
- Modify: `custom_components/dashboard_history/operations.py`
- Modify: `custom_components/dashboard_history/websocket_api.py`
- Modify: `custom_components/dashboard_history/services.py`
- Modify: `custom_components/dashboard_history/services.yaml`
- Modify: `README.md`
- Test: `tests/integration/run_checks.py`

**Interfaces:**
- Consumes: `store.resolve`, `store.read_at`, `store.commit_times`, `store.same_state`, `_explain_texts`, `async_get_config`, `dump` — alle vorhanden, unverändert.
- Produces: `operations.async_compare(hass, store, key, revision_a=None, revision_b=None) -> dict`. Antwortform wie `async_explain`/`_explain_texts` (`groups`, `note`, `diff`, optional `error`), **zusätzlich** — sobald kein Fehler vorliegt — `revision_a`/`revision_b` (dieselben Werte, die hereinkamen, aber chronologisch geordnet: die ältere Seite steht danach unter `revision_a`, unabhängig davon, in welcher Reihenfolge der Aufrufer sie geschickt hat) und `time_a`/`time_b` (Unix-Zeitstempel der jeweiligen Seite, `None` für »Aktueller Zustand«). WS-Befehl `dashboard_history/compare`, Dienst `compare`. Aufgabe 3 (Panel-Dialog) liest `revision_a`/`revision_b`/`time_a`/`time_b`, um seine beiden lokal gespeicherten Auswahl-Einträge korrekt zuzuordnen — siehe dort, warum das Panel diese Zuordnung nicht mehr selbst berechnet.

⚠️ **Verworfener erster Entwurf, zur Erinnerung, warum die jetzige Fassung so aussieht:** Ein früherer Entwurf ließ beide Seiten über `_state_at` auflösen. Das widerspricht der Spec direkt — der Randfall »Vergleichsmodus: eine Seite ist die Löschzeile eines gelöschten Dashboards« (Fehler- und Randfälle-Tabelle) verlangt, dass der Vergleich dort **möglich bleibt**, weil `_explain_texts` eine fehlende Seite selbst erklären kann. `_state_at` verwandelt genau das in einen Fehler — der eigene Kommentar bei `_explain_sync` nennt das wörtlich »the same class of mistake this project has fixed three times«. Die Fassung unten löst wie `_explain_sync` über `store.resolve` + `store.read_at` auf und lässt eine fehlende Seite als `None` in `_explain_texts` laufen.

- [ ] **Schritt 1: `async_compare` schreiben**

In `operations.py`, direkt nach `async_explain` (nach der Funktion, die bei `_explain_texts` endet — siehe deren aktuelle Zeilen um `_explain_sync`/`_explain_texts`):

```python
async def async_compare(
    hass: HomeAssistant,
    store: HistoryStore,
    key: str,
    revision_a: str | None = None,
    revision_b: str | None = None,
) -> dict:
    """The difference between two states of one dashboard, any two at all.

    Unlike `async_explain`, which always compares a change against its
    own predecessor, this takes two revisions with no assumed relation
    between them - adjacent, far apart, or either one the dashboard's
    current live state. `_explain_texts` already makes no such
    assumption; only the caller above it did.

    `None` on a side means the current live state. It is not a
    revision - nothing committed it. At least one side must be an
    actual revision: comparing "now" against "now" is not a question
    this operation has an answer for.

    Deliberately not `_state_at` for a real revision: that reports an
    absent state as an error, and an absent state *is* a legitimate
    answer here - the deletion row of a deleted dashboard, which the
    spec's edge-case table says must stay comparable. `_explain_sync`
    made the same choice for the same reason; this mirrors it.

    The panel sends its two picks in whatever order somebody clicked
    them, and cannot always tell which is older itself - a picked row
    can survive a refresh that removed it from what is loaded (spec,
    same table). Ordering by chronology is therefore done here, not in
    the panel: `revision_a`/`revision_b` in the answer are the caller's
    own values, but reassigned so the older side is always `a`. Getting
    this backwards reads the whole explanation in reverse - "X added"
    for a card the dashboard actually lost - which is the trap decision
    9 removed for the single-change case and re-opens here if skipped.
    """
    if revision_a is None and revision_b is None:
        return {
            "groups": [],
            "note": "",
            "diff": "",
            "error": "nothing to compare: both sides are the current state",
        }

    async def resolved(revision):
        if revision is None:
            live = await async_get_config(hass, key)
            if live is None:
                return None, None, f"{key} does not exist right now"
            text = await hass.async_add_executor_job(dump, live)
            return None, text, None
        full = await hass.async_add_executor_job(store.resolve, revision)
        if full is None:
            return None, None, f"unknown revision: {revision}"
        text = await hass.async_add_executor_job(store.read_at, key, full)
        return full, text, None

    full_a, text_a, error = await resolved(revision_a)
    if error is not None:
        return {"groups": [], "note": "", "diff": "", "error": error}
    full_b, text_b, error = await resolved(revision_b)
    if error is not None:
        return {"groups": [], "note": "", "diff": "", "error": error}

    times = {}
    if full_a is not None and full_b is not None:
        times = await hass.async_add_executor_job(
            store.commit_times, [full_a, full_b]
        )

    def newer(x_full, y_full):
        if x_full is None:  # "current" - always the newest
            return True
        if y_full is None:
            return False
        return times.get(x_full, 0) > times.get(y_full, 0)

    if newer(full_a, full_b):
        full_a, full_b = full_b, full_a
        text_a, text_b = text_b, text_a
        revision_a, revision_b = revision_b, revision_a

    result = {
        "revision_a": revision_a,
        "revision_b": revision_b,
        "time_a": times.get(full_a),
        "time_b": times.get(full_b),
    }

    # Where both sides are real revisions, whether they hold the same
    # state is a question this store already answers - decision 13 asks
    # that the next place this comes up not become a second comparison
    # method beside it. Where one side is "current", `same_state` has
    # nothing to compare (no commit for a live state), and the diff
    # `_explain_texts` builds anyway is trusted instead: both texts
    # already resolved without error above, so an empty diff here is
    # never the accidental kind - only ever genuine equality.
    if full_a is not None and full_b is not None:
        same = await hass.async_add_executor_job(store.same_state, key, full_a, full_b)
        if same:
            return {**result, "groups": [], "note": "", "diff": ""}

    explanation = await hass.async_add_executor_job(_explain_texts, text_a, text_b, key)
    return {**result, **explanation}
```

- [ ] **Schritt 2: Den Befehl registrieren**

In `websocket_api.py`, in `_COMMANDS`, direkt nach dem `deleted_since`-Eintrag:

```python
    _command(
        f"{DOMAIN}/compare",
        {
            **_DASHBOARD,
            vol.Optional("revision_a"): str,
            vol.Optional("revision_b"): str,
        },
        operations.async_compare,
        lambda msg: {
            "key": msg["dashboard"],
            "revision_a": msg.get("revision_a"),
            "revision_b": msg.get("revision_b"),
        },
    ),
```

- [ ] **Schritt 3: Auch als Dienst registrieren**

README (Zeile 981) verspricht unbedingt: »Everything the panel does is available under Developer Tools → Actions.« `explain` hat einen Dienst neben seinem WS-Befehl; `compare` bekommt denselben, sonst bräche dieser Plan das Versprechen ohne es zu benennen (Entscheidung 9: »Dienste und Panel sind zwei dünne Häute über derselben Schicht«).

In `services.py`, neben `explain`:

```python
    async def compare(call: ServiceCall) -> dict:
        return await operations.async_compare(
            hass,
            store,
            call.data["dashboard"],
            call.data.get("revision_a"),
            call.data.get("revision_b"),
        )
```

Und in der `registrations`-Liste, neben dem `explain`-Eintrag:

```python
        ("compare", compare, DASHBOARD.extend({
            vol.Optional("revision_a"): cv.string,
            vol.Optional("revision_b"): cv.string,
        })),
```

In `services.yaml`, neben `explain`:

```yaml
compare:
  name: Compare two states
  description: >-
    The full difference between any two states of one dashboard - not
    necessarily adjacent ones, and either side may be left out to mean
    the dashboard's current live state.
  fields:
    dashboard:
      required: true
      example: dashboard-karte
      selector:
        text:
    revision_a:
      description: >-
        One side of the comparison. Left out, this side means the
        current live state - at least one of the two must be an actual
        revision.
      selector:
        text:
    revision_b:
      description: The other side, same rule.
      selector:
        text:
```

In `README.md`, in der Dienste-Tabelle (Zeile 993-994, neben `deleted_since`/`restore_deleted`):

```markdown
| `compare` | The full difference between any two states, not necessarily adjacent ones |
```

- [ ] **Schritt 4: Container neu starten**

```bash
docker compose -f docker/compose.yaml restart homeassistant
```

Ohne diesen Schritt läuft der Container weiter mit dem alten `operations.py` im Speicher, und Schritt 6 prüft nichts.

- [ ] **Schritt 5: `run_compare` schreiben**

In `tests/integration/run_checks.py`, nach `async def run_undo(access: str) -> None:` (vor `run_paging`):

```python
async def run_compare(access: str) -> None:
    """Comparing two arbitrary states, not necessarily adjacent ones."""
    key = "dh-compare-check"
    first = {"type": "markdown", "content": "First card"}
    second = {"type": "markdown", "content": "Second card"}
    third = {"type": "markdown", "content": "Third card"}

    def state(cards):
        return {"views": [{"path": "a", "title": "A", "cards": list(cards)}]}

    async def save(socket, cards):
        before = await socket.call("dashboard_history/history", dashboard=key, limit=1)
        rows = before["changes"]
        await socket.call(
            "lovelace/config/save", url_path=key, config=state(cards)
        )
        await _wait_for_new_state(
            socket, key, rows[0]["revision"] if rows else "", RECORDING_WAIT
        )

    async def newest(socket):
        answer = await socket.call("dashboard_history/history", dashboard=key)
        return answer["changes"][0]["revision"]

    async with Socket(access) as socket:
        listed = (await socket.call("lovelace/dashboards/list")) or []
        made_id = next(
            (entry["id"] for entry in listed if entry.get("url_path") == key), None
        )
        if made_id is None:
            made = await socket.call(
                "lovelace/dashboards/create", url_path=key, title="DH Compare"
            )
            made_id = made["id"]
            await asyncio.sleep(4)

        await save(socket, [first])
        first_rev = await newest(socket)
        await save(socket, [first, second])
        middle_rev = await newest(socket)
        await save(socket, [first, second, third])
        newest_rev = await newest(socket)

        # Two non-adjacent, real revisions.
        answer = await socket.call(
            "dashboard_history/compare",
            dashboard=key,
            revision_a=first_rev,
            revision_b=newest_rev,
        )
        check(
            "a compare across two non-adjacent states names both additions",
            len(answer.get("groups", [])) == 1
            and len(answer["groups"][0]["entries"]) == 2,
            str(answer.get("groups")),
        )
        check("no error on two known revisions", "error" not in answer)
        check(
            "the answer echoes back which side is the older one",
            answer.get("revision_a") == first_rev
            and answer.get("revision_b") == newest_rev,
            str({k: answer.get(k) for k in ("revision_a", "revision_b")}),
        )
        check(
            "both real sides carry their own commit time",
            isinstance(answer.get("time_a"), int) and isinstance(answer.get("time_b"), int)
            and answer["time_a"] <= answer["time_b"],
            str({k: answer.get(k) for k in ("time_a", "time_b")}),
        )

        # The same pair, arguments the other way round - the panel does
        # not always know which of its two picks is older (a picked row
        # can outlive a refresh that dropped it from what is loaded), so
        # sending them in click order rather than chronological order
        # must produce the identical, correctly-oriented answer.
        reversed_answer = await socket.call(
            "dashboard_history/compare",
            dashboard=key,
            revision_a=newest_rev,
            revision_b=first_rev,
        )
        check(
            "argument order does not change which side ends up 'a'",
            reversed_answer.get("revision_a") == first_rev
            and reversed_answer.get("revision_b") == newest_rev
            and reversed_answer.get("groups") == answer.get("groups"),
            str(reversed_answer),
        )

        # One side is the current live state.
        answer = await socket.call(
            "dashboard_history/compare",
            dashboard=key,
            revision_a=middle_rev,
        )
        check(
            "against the current state, one addition shows up",
            len(answer.get("groups", [])) == 1
            and len(answer["groups"][0]["entries"]) == 1,
            str(answer.get("groups")),
        )
        check(
            "'current state' always lands as the newer side, argument slot aside",
            answer.get("revision_a") == middle_rev and answer.get("revision_b") is None
            and answer.get("time_b") is None,
            str({k: answer.get(k) for k in ("revision_a", "revision_b", "time_b")}),
        )

        # Identical content on both sides.
        answer = await socket.call(
            "dashboard_history/compare",
            dashboard=key,
            revision_a=newest_rev,
            revision_b=newest_rev,
        )
        check(
            "comparing a state against itself yields an empty diff",
            answer.get("diff", "x") == "",
            repr(answer.get("diff")),
        )

        # Both sides the current state: refused, not silently answered.
        answer = await socket.call("dashboard_history/compare", dashboard=key)
        check(
            "comparing 'now' against 'now' is refused",
            bool(answer.get("error")),
            str(answer),
        )

        # Unknown revision.
        answer = await socket.call(
            "dashboard_history/compare",
            dashboard=key,
            revision_a="0" * 40,
            revision_b=newest_rev,
        )
        check(
            "an unresolvable revision is named as the error, not silently empty",
            "unknown revision" in (answer.get("error") or ""),
            str(answer.get("error")),
        )

        # One side is the deletion row itself - the case `_state_at`
        # would have wrongly turned into an error (see task 1's aside).
        await socket.call("lovelace/dashboards/delete", dashboard_id=made_id)
        deletion_rev = await _wait_for_newest(
            socket, key, "dashboard deleted", RECORDING_WAIT
        )
        answer = await socket.call(
            "dashboard_history/compare",
            dashboard=key,
            revision_a=newest_rev,
            revision_b=deletion_rev,
        )
        check(
            "comparing against a dashboard's own deletion row is not an error",
            "error" not in answer,
            str(answer),
        )
        check(
            "the deletion shows up as removals, not a silently empty diff",
            len(answer.get("groups", [])) >= 1,
            str(answer.get("groups")),
        )
```

- [ ] **Schritt 6: In den Dispatcher einhängen**

Am Ende von `run_checks.py`, nach `asyncio.run(run_undo(access))`:

```python
    print("\n  -- Eine Aenderung gezielt zuruecknehmen --")
    asyncio.run(run_undo(access))
    print("\n  -- Zwei beliebige Staende vergleichen --")
    asyncio.run(run_compare(access))
```

- [ ] **Schritt 7: Ausführen und grün sehen**

```bash
docker compose -f docker/compose.yaml up -d
python3 tests/integration/run_checks.py
```

Erwartet: `188 von 188 Prüfungen bestanden` (176 + 12 neue `check(...)`-Aufrufe oben — 12, nicht 6: die Sortier-Regressionsprüfungen und der Löschzeilen-Fall kamen bei der Überarbeitung dieser Aufgabe hinzu).

- [ ] **Schritt 8: Commit**

```bash
git add custom_components/dashboard_history/operations.py \
        custom_components/dashboard_history/websocket_api.py \
        custom_components/dashboard_history/services.py \
        custom_components/dashboard_history/services.yaml \
        README.md \
        tests/integration/run_checks.py
git commit -m "$(cat <<'EOF'
Add async_compare for comparing two arbitrary dashboard states

The row-level "also missing since then" put-back list is being
replaced by a deliberate compare mode (spec decision 19). This is
its backend half: two revisions in, the same explanation/diff shape
async_explain already returns, reusing _explain_texts unchanged.
Ordered chronologically here rather than by the caller, and exposed
as a service alongside the panel's WS command like every other
operation (README: "everything the panel does" is a service too).

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Panel.js + rows.js — Vergleichsmodus-Umschalter und Auswahl

**Files:**
- Modify: `custom_components/dashboard_history/panel.js`
- Modify: `custom_components/dashboard_history/panel/rows.js`
- Modify: `custom_components/dashboard_history/panel/style.js`
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `renderRow`/`versionHead` (bestehend, beide werden um Parameter erweitert), `_mode` (bestehend: `"simple" | "advanced"`).
- Produces: `this._compareMode` (bool), `this._compareSelection` (Array aus höchstens zwei Einträgen, je `{ revision: string|null, label: string }` — `revision: null` steht für »Aktueller Zustand«), `_toggleCompareMode()`, `_toggleCompareRevision(revision, label)`. Aufgabe 3 liest `_compareSelection`, sobald es zwei Einträge hat, und öffnet darüber den Dialog.

⚠️ Der alte Zeilen-Block (`this._items`, `deleted_since` in `_detailCalls`) existiert zu diesem Zeitpunkt noch — er wird erst in Aufgabe 5 entfernt, damit ein verweigerter Undo nie ohne Weg zurück dasteht. Diese Aufgabe fasst ihn nicht an.

- [ ] **Schritt 1: Fehlschlagenden Test zuerst schreiben**

In `tests/test_panel_behaviour.py`, ein neues Node-Szenario nach den bestehenden Auswahl-nahen Tests (z. B. direkt vor der `_SEARCH`-Szene):

```python
_COMPARE_SELECT = """
const el = new Panel();
el._render = () => {};
el._mode = "advanced";
el._changes = [];
// Reaching two picks fires _openCompare() once task 3 lands - a
// never-settling call and stand-ins for shadowRoot/_changes keep that
// harmless here, since this scenario only inspects the synchronous
// selection state and never awaits anything.
el._call = () => new Promise(() => {});
el.shadowRoot = node();

el._toggleCompareMode();
const afterOn = el._compareMode;

el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision("b", "2 moved");
const twoSelected = [...el._compareSelection];

// A third pick evicts the oldest, not the newest.
el._toggleCompareRevision("c", "1 added");
const afterThird = [...el._compareSelection];

// Picking an already-selected one again clears just that one.
el._toggleCompareRevision("c", "1 added");
const afterToggleOff = [...el._compareSelection];

el._toggleCompareMode();
const afterOff = { mode: el._compareMode, selection: [...el._compareSelection] };

console.log(JSON.stringify({ afterOn, twoSelected, afterThird, afterToggleOff, afterOff }));
"""


@pytest.fixture(scope="session")
def compare_select(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "compare_select", _COMPARE_SELECT)


def test_compare_mode_selection_keeps_at_most_two(compare_select):
    assert compare_select["afterOn"] is True
    assert [s["revision"] for s in compare_select["twoSelected"]] == ["a", "b"]
    # "a" was the oldest pick; the third eviction drops it, not "b".
    assert [s["revision"] for s in compare_select["afterThird"]] == ["b", "c"]
    assert [s["revision"] for s in compare_select["afterToggleOff"]] == ["b"]
    # Turning compare mode off clears the selection - reopening starts fresh.
    assert compare_select["afterOff"] == {"mode": False, "selection": []}
```

(Die exakte Einbettung folgt dem Muster von `_SEARCH`/`refreshed` direkt darüber — `_run_in_node` mit demselben `_PRELUDE`.)

- [ ] **Schritt 2: Ausführen, sehen dass es fehlschlägt**

```bash
python3 -m pytest test_panel_behaviour.py -k compare_mode_selection -v
```

Erwartet: FAIL — `_toggleCompareMode` existiert noch nicht.

- [ ] **Schritt 3: Zustand und Methoden in `panel.js` ergänzen**

Im Konstruktor, neben den anderen Feldern (z. B. neben `this._items = [];` — das bleibt bis Aufgabe 5 bestehen):

```js
    this._compareMode = false;
    this._compareSelection = [];
```

Neue Methoden, in der Nähe von `_setMode`:

```js
  /** Turns the compare mode's checkboxes on or off, clearing any pick. */
  _toggleCompareMode() {
    this._compareMode = !this._compareMode;
    this._compareSelection = [];
    this._render();
  }

  /**
   * One pick in the compare mode. `revision` is `null` for "Current
   * state" - the one pick that is not a recorded revision at all.
   *
   * A third pick evicts the oldest of the two standing picks (FIFO),
   * never an error: comparing is exploratory, and blocking a third
   * click would only make somebody uncheck one first for no reason.
   * Picking an already-selected revision again removes just that one.
   */
  _toggleCompareRevision(revision, label) {
    const at = this._compareSelection.findIndex((s) => s.revision === revision);
    if (at >= 0) {
      this._compareSelection.splice(at, 1);
    } else {
      this._compareSelection.push({ revision, label });
      if (this._compareSelection.length > 2) this._compareSelection.shift();
    }
    this._render();
  }
```

- [ ] **Schritt 4: Test grün sehen**

```bash
python3 -m pytest test_panel_behaviour.py -k compare_mode_selection -v
```

- [ ] **Schritt 5: Checkbox in `renderRow` und `versionHead` (rows.js)**

`renderRow` bekommt zwei neue, optionale Parameter:

```js
export function renderRow({
  change,
  newest = false,
  spokenFor = false,
  matching = [],
  detail = "",
  compareMode = false,
  compareChecked = false,
}) {
```

Und im zurückgegebenen Markup, vor `<span class="what">`:

```js
        <div class="change penholder" data-revision="${escape(change.revision)}">
          ${compareMode
      ? `<input type="checkbox" class="compare-check" data-compare="${escape(change.revision)}"
                 data-compare-label="${escape(change.description || change.message)}"
                 ${compareChecked ? "checked" : ""}>`
      : ""}
          <span class="what">${escape(change.description || change.message)}${chip}${named}
```

`versionHead` bekommt dieselben zwei Parameter — die Spec verlangt die Checkbox auf »jeder Änderung, jeder benannten Version«, nicht nur auf einzelnen Änderungen:

```js
export function versionHead({ section, here, top, compareMode = false, compareChecked = false }) {
  const [first, ...also] = section.versions;
  const count = section.rows.length;
  const extra = also
    .map(
      (v) =>
        `<span class="also">also ${escape(v.name)} — ${escape(v.title)}${pen(v)}${bin(v)}</span>`,
    )
    .join("");
  const back = here
    ? `<span class="count">${top === 0 ? "current state" : "same state as now"}</span>`
    : `<button class="act ghost" data-state="${escape(first.name)}"
               >Back to this version</button>`;
  return `
    <summary class="penholder">
      ${compareMode
      ? `<input type="checkbox" class="compare-check" data-compare="${escape(first.name)}"
                 data-compare-label="${escape(first.title || first.name)}"
                 ${compareChecked ? "checked" : ""}>`
      : ""}
      <span class="name">${escape(first.name.split("/").pop())}</span>
      <span class="grow">${escape(first.title || first.name)}${extra}</span>
      <span class="count">${count} change${count === 1 ? "" : "s"}</span>
      ${back}
      ${pen(first)}
      ${bin(first)}
    </summary>`;
}
```

(Nur `first` bekommt die Checkbox, nicht jeder Name unter `also` — dieselbe Beschränkung, die `pen`/`bin`/`data-state` an dieser Stelle bereits treffen. `first.name` — der Versions-Tag, z. B. `heizung/v1.0.0` — ist als Revision an `store.resolve` bereits gültig, wie `data-state` hier zeigt und der Test-Plan-Eintrag »`resolve()` über einen Versionsnamen« absichert; `async_compare` braucht dafür keine Änderung.)

Neuer Export daneben, für den Pseudo-Eintrag »Aktueller Zustand« (die Checkbox, die keine Revision trägt):

```js
/**
 * The compare mode's one pick that is not a row: "Current state".
 * Pinned above the list rather than drawn from `_changes[0]`, because
 * the newest entry is not always the current state (decision 9) - and
 * unlike every row, this pick's `data-compare` carries no revision.
 */
export function currentStateRow(checked) {
  return `
      <div class="card current-pick">
        <div class="change penholder">
          <input type="checkbox" class="compare-check" data-compare=""
                 data-compare-label="Current state" ${checked ? "checked" : ""}>
          <span class="what">Current state</span>
        </div>
      </div>`;
}
```

- [ ] **Schritt 6: `panel.js` reicht `compareMode`/`compareChecked` durch und rendert den Pseudo-Eintrag**

`_renderRow` (in `panel.js`):

```js
  _renderRow(change, spokenFor = false) {
    const newest = this._isNewest(change);
    return renderRow({
      change,
      newest,
      spokenFor,
      matching: newest ? this._matchingElsewhere(change) : [],
      detail: this._open === change.revision ? this._renderDetail(change) : "",
      compareMode: this._compareMode,
      compareChecked: this._compareSelection.some((s) => s.revision === change.revision),
    });
  }
```

`_renderVersionHead` (in `panel.js`), dieselbe Erweiterung:

```js
  _renderVersionHead(section) {
    const top = section.rows[0];
    return versionHead({
      section,
      top,
      here: this._changes[top]?.same_as_now,
      compareMode: this._compareMode,
      compareChecked: this._compareSelection.some((s) => s.revision === section.versions[0].name),
    });
  }
```

`renderSimple`/`renderRow`-Import-Liste um `currentStateRow` erweitern (`({ sections, someNames, renderRow, versionHead, currentStateRow } = rows);` in `panel.js`s `partsReady`-Block, und `let ..., currentStateRow;` in der Variablendeklaration daneben).

In `_renderMain`, direkt nach dem `if (this._mode === "simple") return (...);`-Block (der davor unverändert bleibt) `banner` um die Vergleichsleiste erweitern — die vier folgenden `return`-Zeilen der erweiterten Ansicht bleiben dieselben Zeilen, lesen ab jetzt aber `topBar` statt `banner`:

```js
    if (this._mode === "simple")
      return (
        banner +
        renderSimple({
          versions: this._versions,
          shown: this._matchingVersions(),
          changes: this._changes,
          searching: Boolean(query),
          open: this._verOpen,
        })
      );
    // "Current state" is left out for a dashboard Home Assistant does
    // not currently have: there is nothing there to compare against,
    // and Put-back only ever writes into a live state (spec decision
    // 19's edge case table).
    const compareBar = `<div class="compare-bar">
           <button class="act ghost" data-compare-toggle="1">
             ${this._compareMode ? "Exit compare mode" : "Compare mode"}
           </button>
         </div>
         ${this._compareMode && dashboard?.exists !== false
        ? currentStateRow(this._compareSelection.some((s) => s.revision === null))
        : ""}`;
    const topBar = banner + compareBar;
    const shown = this._shown();
    if (shown === null) return topBar;
    if (!shown.length)
      return `${topBar}<p class="empty muted">${query
        ? "Nothing matches."
        : "No changes recorded for this dashboard."}</p>`;
    if (query) return topBar + shown.map((c) => this._renderRow(c)).join("");
```

Und ganz am Ende von `_renderMain`, das letzte `return`:

```js
    return topBar + parts.join("") + older;
```

(Ersetzt `return banner + parts.join("") + older;` — die drei Zeilen dazwischen, die `cut`/`newest`/`label`/`parts`/`older` aufbauen, bleiben unverändert stehen.)

- [ ] **Schritt 7: Klick-Verdrahtung**

Bei den übrigen `onClick(...)`-Aufrufen ergänzen — ein Checkbox-Klick darf die darunterliegende Zeile nicht zusätzlich auf- oder zuklappen, dieselbe `event.stopPropagation()`-Vorsicht wie bei `[data-describe]`/`[data-retitle]` daneben:

```js
    onClick("[data-compare-toggle]", () => this._toggleCompareMode());
    onClick(".compare-check", (element, event) => {
      event.stopPropagation();
      const revision = element.dataset.compare || null;
      this._toggleCompareRevision(revision, element.dataset.compareLabel || "");
    });
```

- [ ] **Schritt 8: CSS ergänzen (`panel/style.js`)**

Am Ende der bestehenden Regeln, vor dem schließenden Backtick des Template-Literals:

```css
  .compare-bar { display: flex; justify-content: flex-end; padding: 8px 0; }
  .compare-check { margin-right: 8px; width: 16px; height: 16px; flex-shrink: 0; }
  .current-pick .change { background: var(--secondary-background-color, #eee); }
```

⚠️ Nur an dieser einen Stelle einfügen, vor dem abschließenden Backtick — `test_panel_assets.py` zählt die Backticks der Datei und schlägt fehl, sobald ein zweites Paar entsteht.

- [ ] **Schritt 9: Ganze Suite grün, `test_panel_assets.py` eingeschlossen**

```bash
python3 -m pytest tests/ -v
```

- [ ] **Schritt 10: Commit**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/rows.js \
        custom_components/dashboard_history/panel/style.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Add the compare mode's toggle and per-row selection

Advanced mode only (spec decision 17/19): a button turns on a
checkbox per row - version heads included, not just single changes -
plus a pinned "Current state" pick. At most two stay selected; a
third pick evicts the oldest. Nothing opens yet - that is the next
commit.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Panel.js + dialogs.js — Der Vergleichsdialog

**Files:**
- Modify: `custom_components/dashboard_history/panel.js`
- Modify: `custom_components/dashboard_history/panel/dialogs.js`
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `_compareSelection`, `_call`, `renderPlain`, `renderDiff`, `when`, `_answerFrom`, `_restoreItem` (wird hier verallgemeinert).
- Produces: `_openCompare()` (wird automatisch aufgerufen, sobald `_compareSelection.length === 2`), `_restoreItem(revision, item)` (neue Signatur, vorher `(change, item)`).

- [ ] **Schritt 1: `_restoreItem` verallgemeinern — und seinen noch bestehenden alten Aufrufer mitziehen**

```js
  _restoreItem(revision, item) {
    this._confirm(`Put back: ${item.label}`, (confirm, keep, dashboard) => [
      "restore_deleted",
      { dashboard, revision, position: item.position, confirm },
    ]);
  }
```

(Vorher nahm es `change` entgegen und griff auf `change.previous` zu.)

⚠️ Der alte Zeilen-Block existiert noch — Aufgabe 5 entfernt ihn erst — und sein `[data-restore]`-Handler ruft `_restoreItem` bisher mit dem ganzen `change`-Objekt auf. Nach dieser Verallgemeinerung muss er stattdessen die Revision selbst übergeben, sonst schickt er ab sofort ein Objekt statt eines Revisions-Strings an den Dienst:

```js
    onClick("[data-restore]", (element) => {
      const change = this._changeAt(this._open);
      const item = this._items.find(
        (candidate) => candidate.position === Number(element.dataset.restore),
      );
      if (change?.previous && item) this._restoreItem(change.previous, item);
    });
```

(Ersetzt nur die eine Zeile `if (change && item) this._restoreItem(change, item);` — der Rest des Handlers bleibt unverändert.)

- [ ] **Schritt 2: Dialog-Markup (`dialogs.js`)**

Nach dem `remove`-Dialog, vor dem schließenden Backtick des `DIALOGS`-Template-Literals:

```js
  <dialog class="compare">
    <h2>Compare two states</h2>
    <div class="body" data-compare-body></div>
    <div class="actions">
      <button class="act ghost" value="close">Close</button>
    </div>
  </dialog>`;
```

- [ ] **Schritt 3: Fehlschlagenden Test zuerst schreiben**

`_toggleCompareRevision` ist synchron, `_openCompare` wird asynchron sein (es ruft `_call` auf) und aus `_toggleCompareRevision` heraus **gestartet, aber nicht abgewartet** — dieselbe Feuer-und-vergiss-Form wie andere durch einen Klick gestartete Flüsse in dieser Datei. Das Szenario prüft deshalb das Ergebnis über die bereits offene `dialog.compare`, nachdem die gemockten Antworten aufgelöst wurden:

```python
_COMPARE_OPEN = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._mode = "advanced";
el.shadowRoot = node();

const calls = [];
el._call = (type, extra) => new Promise((resolve) => {
  calls.push({ type, extra, resolve });
});

el._toggleCompareMode();
el._toggleCompareRevision("a", "1 removed");
el._toggleCompareRevision(null, "Current state");
await settle();

const compareCall = calls.find((c) => c.type === "compare");
// The backend decides order, not this scenario - "a" comes back as
// revision_a because it really is the older side. A non-empty diff:
// an empty one would mean the two states are byte-identical, and then
// deleted_since could not honestly report anything missing either.
compareCall.resolve({
  groups: [], note: "", diff: "-Gone card\\n",
  revision_a: "a", revision_b: null, time_a: 1731000000, time_b: null,
});
await settle();

const missingCall = calls.find((c) => c.type === "deleted_since");
missingCall.resolve({ items: [{ position: 0, kind: "card", label: "Gone card", view: "a" }] });
await settle();

const dialog = el.shadowRoot.querySelector("dialog.compare");
const body = dialog.querySelector("[data-compare-body]");

console.log(JSON.stringify({
  compareArgs: compareCall.extra,
  missingArgs: missingCall.extra,
  bodyHtml: body.innerHTML,
  dialogOpen: dialog.open,
}));
"""


@pytest.fixture(scope="session")
def compare_open(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "compare_open", _COMPARE_OPEN)


def test_compare_dialog_opens_on_two_picks_and_offers_put_back(compare_open):
    # "a" was picked first, "current" second - the backend's revision_a
    # says "a" is genuinely the older side, and the dialog trusts that
    # rather than re-deriving order from `_changes` itself.
    assert compare_open["compareArgs"] == {"dashboard": "dash", "revision_a": "a"}
    assert compare_open["missingArgs"] == {"dashboard": "dash", "revision": "a"}
    # Spec decision 19/9: each side names its own automatic message, not
    # a bare "between X and Y" that could be either of the two rows.
    assert '"1 removed"' in compare_open["bodyHtml"]
    assert "Current state" in compare_open["bodyHtml"]
    assert "Gone card" in compare_open["bodyHtml"]
    assert "Put back" in compare_open["bodyHtml"]
    assert compare_open["dialogOpen"] is True
```

- [ ] **Schritt 4: Ausführen, sehen dass es fehlschlägt**

```bash
python3 -m pytest test_panel_behaviour.py -k compare_dialog_opens -v
```

Erwartet: FAIL — `_openCompare` existiert noch nicht, die Checkbox löst noch nichts aus.

- [ ] **Schritt 5: `_toggleCompareRevision` löst bei zwei Auswahlen `_openCompare` aus**

```js
  _toggleCompareRevision(revision, label) {
    const at = this._compareSelection.findIndex((s) => s.revision === revision);
    if (at >= 0) {
      this._compareSelection.splice(at, 1);
    } else {
      this._compareSelection.push({ revision, label });
      if (this._compareSelection.length > 2) this._compareSelection.shift();
    }
    this._render();
    if (this._compareSelection.length === 2) this._openCompare();
  }
```

- [ ] **Schritt 6: `_openCompare` schreiben**

```js
  /**
   * Opens the compare dialog for the two current picks.
   *
   * Sends both picks to `compare` in whatever order they were selected
   * - the backend works out which one is actually older, not this
   * method. A picked row can outlive a refresh that dropped it from
   * `_changes` (spec decision 19's own edge case), so `_changes`
   * cannot be trusted here the way an earlier draft of this method
   * trusted it. `revision_a`/`revision_b` come back reassigned into
   * chronological order; matching them against the two local picks
   * says which label and date belong on which side.
   */
  async _openCompare() {
    const [first, second] = this._compareSelection;
    const dialog = this.shadowRoot.querySelector("dialog.compare");
    const body = dialog.querySelector("[data-compare-body]");
    body.innerHTML = `<p class="muted row-loading"><span class="ring mini"></span> Comparing…</p>`;
    dialog.returnValue = "";
    dialog.showModal();

    const compareArgs = { dashboard: this._selected };
    if (first.revision !== null) compareArgs.revision_a = first.revision;
    if (second.revision !== null) compareArgs.revision_b = second.revision;
    const comparison = await this._call("compare", compareArgs);

    if (comparison.error) {
      body.innerHTML = `<p class="why">${escape(comparison.error)}</p>`;
      await this._answerFrom(dialog);
      return;
    }

    const older = first.revision === comparison.revision_a ? first : second;
    const newer = older === first ? second : first;

    // Spec decision 19/9: naming date and automatic message on each
    // side is not decoration - it is what removes the "one row too
    // early" trap decision 9 removed for the single-change case.
    // Without it, nothing here says which picked row ended up which
    // side of the sentence below.
    const describe = (entry, time) =>
      entry.revision === null
        ? "Current state"
        : `the state after "${escape(entry.label)}" (${escape(when(time))})`;

    let missingHtml = "";
    // Put back only where one side is the current state - the other
    // side is then the reference `deleted_since` and `restore_deleted`
    // already work against, unchanged.
    const historicalSide = newer.revision === null ? older : null;
    if (historicalSide) {
      const missing = await this._call("deleted_since", {
        dashboard: this._selected,
        revision: historicalSide.revision,
      });
      const items = missing.items || [];
      missingHtml = items.length
        ? `<p class="why" style="margin-top:16px">Missing since then, still gone:</p>` +
          items
            .map(
              (item) => `
          <div class="item">
            <span class="label">${escape(item.label)}
              <span class="where">${escape(item.kind)}${item.view ? ` · view ${escape(item.view)}` : ""}</span>
            </span>
            <button class="act" data-compare-restore="${item.position}">Put back</button>
          </div>`,
            )
            .join("")
        : `<p class="muted">Nothing from before this state is missing today.</p>`;
      dialog.dataset.compareReference = historicalSide.revision;
    } else {
      delete dialog.dataset.compareReference;
    }

    const diff = comparison.diff || "";
    body.innerHTML = diff
      ? renderPlain(
          comparison,
          `What changed between ${describe(older, comparison.time_a)} and ${describe(newer, comparison.time_b)}`,
        ) +
        `<details class="raw"><summary>Show the technical details</summary>${renderDiff(diff)}</details>` +
        missingHtml
      : `<p class="muted">No difference between these two states.</p>`;

    await this._answerFrom(dialog);
  }
```

- [ ] **Schritt 7: Klick-Verdrahtung für den Put-back-Knopf im Dialog**

```js
    onClick("[data-compare-restore]", (element) => {
      const dialog = element.closest("dialog.compare");
      const revision = dialog?.dataset.compareReference;
      if (!revision) return;
      const position = Number(element.dataset.compareRestore);
      this._restoreItem(revision, { position, label: element.closest(".item")?.querySelector(".label")?.textContent?.trim() || "" });
    });
```

- [ ] **Schritt 8: Test grün sehen, ganze Suite grün**

```bash
python3 -m pytest tests/ -v
```

- [ ] **Schritt 9: Commit**

```bash
git add custom_components/dashboard_history/panel.js \
        custom_components/dashboard_history/panel/dialogs.js \
        tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Open a compare dialog on two picks, put back only against current

Two selections in compare mode open a dialog with the full diff
between them. Order is decided by the backend (async_compare's own
revision_a/revision_b), not by scanning _changes here, since a pick
can outlive a refresh that dropped its row from what is loaded. Each
side names its own date and automatic message, the same safeguard
decision 9 built for the single-change case. Put-back is offered
only when one side is the current live state - the same
deleted_since/restore_deleted calls the removed row-level block
used, reached through a deliberate pick instead of automatically on
every earlier row.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Panel.js — Undo-Verweigerung verweist auf den Vergleichsmodus

**Files:**
- Modify: `custom_components/dashboard_history/panel.js`
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: `_offer`-Block in `_renderDetail`, `_compareMode`, `_compareSelection`, `_openCompare`, `_changeAt`.
- Produces: `_jumpToCompareFrom(previousRevision)` (setzt Vergleichsmodus, Auswahl und öffnet den Dialog in einem Zug) und ein neuer Knopf `[data-compare-from]` in der Verweigerungs-Meldung, der sie aufruft.

- [ ] **Schritt 1: Fehlschlagenden Test zuerst schreiben**

Ein Node-Szenario, das eine Zeile mit verweigertem Undo öffnet und prüft, dass die Verweigerung einen Knopf mit der Vorgänger-Revision trägt:

```python
_UNDO_REFUSED_LINKS_TO_COMPARE = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [{ revision: "b", previous: "a", message: "1 removed" }];
el._open = "b";
el._explanation = { groups: [], note: "" };
el._undo = { available: false, reason: "a section has no path to recognise it by" };
el._loadingDetail = null;
el._loadingUndo = null;

const html = el._renderDetail(el._changes[0]);
console.log(JSON.stringify({ html }));
"""


@pytest.fixture(scope="session")
def undo_refused_links_to_compare(tmp_path_factory):
    return _run_in_node(
        tmp_path_factory, "undo_refused_links_to_compare", _UNDO_REFUSED_LINKS_TO_COMPARE
    )


def test_undo_refusal_offers_a_way_into_compare_mode(undo_refused_links_to_compare):
    html = undo_refused_links_to_compare["html"]
    assert "cannot be taken back exactly" in html
    assert 'data-compare-from="a"' in html
```

Ein zweites Szenario für den Klick selbst — bewusst mit einer bereits **bestehenden, andersartigen** Auswahl im Vergleichsmodus, dem Fall, an dem ein früherer Entwurf dieses Handlers doppelt geöffnet oder das falsche Paar erwischt hätte:

```python
_COMPARE_FROM_CLICK = """
const el = new Panel();
el._render = () => {};
el._selected = "dash";
el._changes = [
  { revision: "z", previous: "y", message: "unrelated" },
  { revision: "b", previous: "a", message: "1 removed" },
];
let openCount = 0;
el._openCompare = () => { openCount += 1; return Promise.resolve(); };

// Compare mode is already on, with an unrelated row already picked -
// exactly the state a naive toggle-based jump would mishandle: one
// _toggleCompareRevision call away from firing _openCompare with the
// wrong pair already.
el._toggleCompareMode();
el._toggleCompareRevision("z", "unrelated");

el._jumpToCompareFrom("a");

console.log(JSON.stringify({
  openCount,
  mode: el._compareMode,
  selection: el._compareSelection.map((s) => s.revision),
}));
"""


@pytest.fixture(scope="session")
def compare_from_click(tmp_path_factory):
    return _run_in_node(tmp_path_factory, "compare_from_click", _COMPARE_FROM_CLICK)


def test_jump_to_compare_from_replaces_any_standing_selection(compare_from_click):
    # Exactly the predecessor and "current state" - the unrelated "z"
    # pick from before the call is gone, not merged into a triple, and
    # _openCompare fires exactly once rather than once with the wrong
    # pair and once more on top of the dialog that first call opened.
    assert compare_from_click["mode"] is True
    assert compare_from_click["selection"] == ["a", None]
    assert compare_from_click["openCount"] == 1
```

Der `[data-compare-from]`-Klick selbst (dass der Knopf existiert und `_jumpToCompareFrom` mit der richtigen Revision aufruft) ist bereits über `test_undo_refusal_offers_a_way_into_compare_mode` oben abgesichert — der prüft, dass das Markup `data-compare-from="a"` trägt, und die allgemeine Klick-Verdrahtung (`onClick`) ist an keiner anderen Stelle dieses Plans gesondert getestet, sondern folgt demselben, bereits bestehenden Muster wie jeder andere `onClick(...)`-Aufruf in dieser Datei.

- [ ] **Schritt 2: Ausführen, sehen dass beide fehlschlagen**

```bash
python3 -m pytest test_panel_behaviour.py -k "undo_refusal_offers or jump_to_compare_from" -v
```

- [ ] **Schritt 3: Den `offer`-Block ergänzen**

In `_renderDetail`, die Verweigerungs-Verzweigung erweitern:

```js
        : this._undo
          ? `<p class="why">This change cannot be taken back exactly:
             ${escape(this._undo.reason || "no reason given")}.</p>
             <div class="backto">
               <button class="act ghost" data-compare-from="${escape(change.previous || "")}"
                       >Compare with the current state</button>
             </div>`
```

(Nur wenn `change.previous` existiert — bei der ersten aufgezeichneten Zeile gibt es diesen Zweig ohnehin nicht, da `_renderDetail` dort schon vorher zurückkehrt.)

- [ ] **Schritt 4: Eine eigene Methode statt einer Inline-Verzweigung — Zustand direkt setzen, nicht per Umschalten**

⚠️ **Nicht** über `_toggleCompareMode()`/`_toggleCompareRevision()` nacheinander lösen: Ist der Vergleichsmodus bereits an und eine andere Zeile schon angekreuzt, feuert das erste `_toggleCompareRevision` bereits bei zwei Einträgen (der alten Auswahl plus dem neuen Vorgänger) und öffnet `_openCompare` mit dem **falschen** Paar; das zweite Toggle verdrängt zwar die alte Auswahl wieder, öffnet aber ein zweites Mal — im Browser ein `showModal()` auf einem bereits offenen Dialog (`InvalidStateError`). Stattdessen den gewünschten Endzustand in einem Zug setzen. Als eigene Methode statt als Inline-Funktion in der Klick-Verdrahtung, aus demselben Grund, aus dem `_toggleCompareMode`/`_toggleCompareRevision` eigene Methoden sind: direkt testbar, ohne einen Klick über den Schatten-DOM simulieren zu müssen — dieselbe Testform, die dieser Plan durchgehend für Zustandsänderungen benutzt.

Neue Methode, in der Nähe von `_toggleCompareRevision`:

```js
  /**
   * The jump a refused undo offers into compare mode: the row's own
   * predecessor against the current state, the same pair the removed
   * row-level list used to show automatically.
   *
   * Sets the end state directly rather than calling
   * `_toggleCompareMode`/`_toggleCompareRevision` in sequence - doing
   * that with a *different* pick already standing would fire
   * `_openCompare` once with the wrong pair and once more on top of
   * the dialog that first call already opened.
   */
  _jumpToCompareFrom(previousRevision) {
    if (!previousRevision) return;
    const row = this._changeAt(previousRevision);
    this._compareMode = true;
    this._compareSelection = [
      { revision: previousRevision, label: row?.description || row?.message || "" },
      { revision: null, label: "Current state" },
    ];
    this._render();
    this._openCompare();
  }
```

Klick-Verdrahtung, nur noch der dünne Aufruf:

```js
    onClick("[data-compare-from]", (element, event) => {
      event.stopPropagation();
      this._jumpToCompareFrom(element.dataset.compareFrom);
    });
```

- [ ] **Schritt 5: Beide Tests grün sehen, ganze Suite grün**

```bash
python3 -m pytest tests/ -v
```

- [ ] **Schritt 6: Commit**

```bash
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Link a refused undo to the compare mode instead of a dead end

Undo refuses structurally for some changes - a deleted section has
no path to recognise it by (README) - and once the row-level list is
gone, that refusal has nowhere left to point. Spec decision 5
promises an alternative on every refusal; this is it, prefilled with
the row's predecessor and the current state. Sets compare mode's
state directly rather than toggling it, so a pick already standing
from before this click cannot open the dialog twice or with the
wrong pair.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Panel.js — Alten Zeilen-Block entfernen

**Files:**
- Modify: `custom_components/dashboard_history/panel.js`
- Test: `tests/test_panel_behaviour.py`

**Interfaces:**
- Consumes: nichts Neues.
- Produces: `_detailCalls(change)` liefert ab jetzt `[explainPromise, undoPromise]` (zwei Einträge, vorher drei).

Läuft absichtlich **nach** den Aufgaben 2-4: Der Vergleichsmodus, sein Dialog und der Verweigerungs-Verweis stehen bereits, bevor der alte Weg verschwindet — kein Commit dieses Plans lässt einen verweigerten Undo je ohne Weg zurück da stehen. `_restoreItem` trägt bereits die neue Signatur `(revision, item)` (Aufgabe 3), und dessen alter Aufrufer wurde dort schon auf `change.previous` umgestellt — diese Aufgabe entfernt nur noch den ganzen Block, ohne an `_restoreItem` selbst etwas zu ändern.

- [ ] **Schritt 1: Fehlschlagende Tests zuerst anpassen**

Drei Stellen in `tests/test_panel_behaviour.py` hängen strukturell an `deleted_since` als Teil von `_detailCalls`. Sie werden jetzt korrekt gemacht, bevor der Code sich ändert — sie schlagen bis Schritt 2 rot fehl, das ist der Sinn dieser Reihenfolge.

**1a.** In der Node-Szene um `test_a_row_is_opened_by_its_revision_and_asks_against_its_own_predecessor` (Assert bei `assert addressing["bottom"]["types"] ==`):

```python
    assert addressing["bottom"]["types"] == ["explain", "undo_change"]
```

(vorher `["deleted_since", "explain", "undo_change"]`).

**1b.** Im `_CACHE_LIMITS`-Skript: Die Zeile

```js
held["deleted_since"]?.resolve({ items: [] });
```

und im `many._call`-Mock die `type === "deleted_since"`-Verzweigung entfernen, sodass er nur noch zwischen `explain` und allem sonst (`undo_change`) unterscheidet:

```js
many._call = (type) =>
  Promise.resolve(
    type === "explain"
      ? { groups: [], note: "", diff: "x" }
      : { available: true },
  );
```

Und in `test_a_failed_undo_is_not_remembered_as_an_answer`:

```python
    assert cache_limits["askedOnReExpand"] == 2
```

(vorher `3`).

**1c.** Im `_REFRESH_OPEN`-Skript und `test_an_open_row_survives_a_refresh_that_moved_it`: Die Zeile, die `deletedSince` aus den Aufrufen liest, sowie `reply("deleted_since", ...)`, entfernen; die Assertion auf `refresh_open["deletedSince"] == "b"` entfällt. Der Rest der Prüfung — dass die Zeile nach einem Refresh anhand ihrer Revision wiedergefunden wird und `explain` erneut gegen die richtige Revision fragt — bleibt unverändert bestehen:

```python
def test_an_open_row_survives_a_refresh_that_moved_it(refresh_open):
    assert refresh_open["rows"] == ["new", "a"]
    assert refresh_open["open"] == "a"
    assert refresh_open["explained"] == "a"
```

- [ ] **Schritt 2: Prüfen, dass diese drei jetzt fehlschlagen**

```bash
python3 -m pytest test_panel_behaviour.py -k "asks_against_its_own_predecessor or failed_undo or survives_a_refresh" -v
```

(Nicht `-k "bottom or cache_limits or refresh_open"` — das trifft keinen einzigen Testnamen, `-k` matcht gegen Testnamen, nicht gegen Fixture-Namen; geprüft: `--collect-only` mit diesem Ausdruck meldet »no tests collected«. Und ohne `cd tests &&` davor — das Arbeitsverzeichnis ist bereits das Projektverzeichnis, siehe globale Regel.)

Erwartet: FAIL an allen dreien (der Code liefert noch die alten Listen mit `deleted_since` darin).

- [ ] **Schritt 3: Den Block aus `panel.js` entfernen**

In `_detailCalls`, die `missing`-Konstante und ihre Rückgabe streichen:

```js
  _detailCalls(change) {
    const explain = this._call("explain", {
      dashboard: this._selected,
      revision: change.revision,
    });
    const undo = change.previous
      ? this._call("undo_change", {
        dashboard: this._selected,
        revision: change.revision,
      })
      : Promise.resolve(null);
    return [explain, undo];
  }
```

In `_expand`, die fast-phase entsprechend kürzen:

```js
    const [explainPromise, undoPromise] = this._detailCalls(change);

    const fastPhase = explainPromise
      .then((explanation) => {
        if (!mine()) return;
        this._explanation = explanation;
        this._loadingDetail = null;
        this._render();
      })
      .catch((err) => {
        if (!mine()) return;
        this._loadingDetail = null;
        this._error = err?.message || String(err);
        this._render();
      });
```

Den Cache-Schreibpfad (`this._detailCache.set(revision, {...})`) und `_clearDetail()` von `items`/`_items` befreien; `_take`:

```js
  _take(answers) {
    const [explanation, undo] = answers || [null, null];
    this._explanation = explanation;
    this._undo = undo || null;
  }
```

Jede verbliebene Fundstelle von `this._items` (Feld-Deklaration im Konstruktor, `_clearDetail`, der Cache-Lesepfad in `_expand`) entfernen.

- [ ] **Schritt 4: Den `own`/`swallowed`/`heading`-Block aus `_renderDetail` streichen**

⚠️ **`const undo = this._undo?.available ? this._undo : null;` bleibt stehen.** Sie wird nicht nur von `swallowed()` gelesen, sondern auch vom `offer`-Block direkt darunter (`const offer = undo ? ... : ...`), der bestehen bleibt — samt dem in Aufgabe 4 ergänzten Verweigerungs-Zweig. Nur die Zeilen **danach**, bis einschließlich `const list = ...`, fallen weg — die Berechnung von `added`, `mine`, `bareLabel`, `swallowed`, `own`, `rows`, `heading`, `list`:

```js
    const undo = this._undo?.available ? this._undo : null;
    // (added/mine/bareLabel/swallowed/own/rows/heading/list: entfernt)

    // Left out where the number is not known - a row from outside the
    // loaded window has no place in it to count from, and a guessed
    // number in a sentence about what is kept would be the worst kind.
    const made = this._madeSince(change);
    const kept =
      made ? ` and keeps the ${made} change${made === 1 ? "" : "s"} made since` : "";
    const offer = undo
      ? `<div class="backto">...`
      // (unverändert, siehe aktueller Code samt Aufgabe 4)
```

`_renderDetail`s Rückgabe verliert `${list}`:

```js
    return `<div class="detail">
      ${plain}
      ${technical}
      ${offer}
      ${this._renderSetBack(change)}
      ${this._renderMakeVersion(change)}
    </div>`;
```

- [ ] **Schritt 5: `[data-restore]`-Handler entfernen**

In der Klick-Verdrahtung den in Aufgabe 3 (Schritt 1) angepassten `onClick("[data-restore]", ...)`-Handler jetzt komplett entfernen — er hatte keinen anderen Zweck als diesen Block, und der Dialog aus Aufgabe 3 deckt Put-back bereits eigenständig ab (`[data-compare-restore]`).

- [ ] **Schritt 6: Alle drei Tests grün sehen, ganze Suite grün**

```bash
python3 -m pytest test_panel_behaviour.py -v
```

Erwartet: alle Fälle bestehen, keine roten mehr.

- [ ] **Schritt 7: Commit**

```bash
git add custom_components/dashboard_history/panel.js tests/test_panel_behaviour.py
git commit -m "$(cat <<'EOF'
Remove the row-level "also missing since then" put-back list

It offered a Put-back button for anything missing since a row's
predecessor, no matter which later change actually removed it - and
on a real dashboard that piled up into a dozen buttons under one
old, unrelated row. Spec decision 19 replaces it with the compare
mode added over the previous three commits; this one only removes
the automatic display, now that the replacement already covers both
the free comparison and the undo-refusal fallback it used to give.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Aufräumen — `look_at_panel.py`, README, `status.md`

**Files:**
- Modify: `tests/integration/look_at_panel.py`
- Modify: `README.md`
- Modify: `docs/superpowers/status.md`

**Interfaces:**
- Consumes: nichts Neues.
- Produces: nichts, das andere Aufgaben lesen — letzte Aufgabe des Plans.

- [ ] **Schritt 1: `look_at_panel.py` auf den Dialog umstellen**

Der Abschnitt »Two kinds of button, told apart« (um Zeile 1095-1140) setzt synthetisch `p._items`, das nach Aufgabe 5 nicht mehr existiert, öffnet aber nie den Vergleichsdialog — er würde nach der Umstellung ein Feld setzen, das niemand liest, und anschließend einen leeren Dialog abfragen. Er wird durch einen Ablauf ersetzt, der den Vergleichsmodus tatsächlich benutzt: Umschalter klicken, zwei Checkboxen ankreuzen, den geöffneten Dialog abfragen.

```js
print("\n-- Two kinds of button, told apart --")
# Compare mode replaces the synthetic `_items` this section used to
# poke directly - `_items` is gone since the row-level list was
# removed (spec decision 19/vorhaben J). This drives the real path
# instead: turn compare mode on, tick "current state" and one row
# that has something missing before it, and read the dialog compare
# mode actually opens.
await page.js(f"{PANEL}.querySelector('[data-compare-toggle]').click()")
await page.js(
    f"(() => {{ const boxes = {PANEL}.querySelectorAll('.compare-check');"
    " boxes[0].click(); boxes[1].click(); })()"
)
opened = await page.settle(f'!!{PANEL}.querySelector("dialog.compare[open]")', 10)
told = await page.js(
    "(() => { const d = " + PANEL + ".querySelector('dialog.compare');"
    " if (!d) return null;"
    " return {"
    "   putBack: d.querySelectorAll('[data-compare-restore]').length,"
    " }; })()"
) if opened else None
for name, value in (told or {"putBack": None}).items():
    print(f"    {name}: {value!r}")
await page.shot("19-two-kinds-of-button.png")
```

Die zweite Fundstelle (um Zeile 421-436, »Two kinds of button sit on a row…«) auf denselben neuen Ort richten:

```js
putBack: d.querySelectorAll("dialog.compare [data-compare-restore]").length,
```

- [ ] **Schritt 2: README aktualisieren**

Mehr als die eine Stelle beschreibt den zeilenweisen Put-back — mindestens fünf: die Tabelle unter »Getting something back« (Zeile 174), der Abschnitt »Where the undo hides a Put back button« (Zeile 612), die Spalte »Put back« in der Grenzen-Tabelle (Zeile 702, 800), und die Sections-Passage (Zeile 277). Alle werden nachgezogen, nicht nur die letzte.

Zeile 277 (»Deleting a whole section comes back through Put back«):

```markdown
- **Deleting a whole section** comes back through *Put back*, which
  offers the section as one thing rather than as a heap of cards — as
  long as the other sections of that view are as you left them. Edit one
  of them in between and it says so; *Undo this change* declines either
  way, because a section has no path to recognise it by. When it does,
  the row offers a way into compare mode instead, prefilled with the
  state right before it and the current one — the same Put back, one
  click further in. The whole-state restore brings it back in any case.
```

Zeile 174 (Tabelle unter »Getting something back«) und Zeile 612 (»Where the undo hides a Put back button«): Beide beschreiben *Put back* als Aktion an einer Karte, unabhängig davon, ob sie über eine Zeile oder über den Vergleichsdialog erreicht wird — den Satz jeweils auf »reached through compare mode» statt »the card's own button« umstellen, ohne die übrige Aussage (additiv, ein fehlendes Element, `confirm`) zu ändern.

Zeile 702 und 800 (Grenzen-Tabellen, Spalte »Put back«): Die Spaltenüberschrift und ihre Erklärung bleiben — Put back als *Fähigkeit* existiert unverändert, nur der Weg dorthin ist jetzt der Vergleichsdialog statt die Zeile selbst. Eine Fußnote unter jeder Tabelle ergänzen: »Reached through compare mode since v0.4.0, not as a button on the row itself.«

- [ ] **Schritt 3: `status.md` nachziehen**

```markdown
| J | Der Vergleichsmodus — ersetzt das zeilenweise Put-back aus Entscheidung 15 durch den Vergleich zweier frei gewählter Stände | Erledigt | `plans/2026-09-12-vergleichsmodus.md` |
```

(Ersetzt die bisherige »Nicht begonnen«-Zeile.)

- [ ] **Schritt 4: Komplette Suite ein letztes Mal**

```bash
python3 -m pytest tests/ -v
python3 tests/integration/run_checks.py
python3 tests/integration/look_at_panel.py
```

Erwartet: `pytest` mindestens 583+ bestanden (plus die in diesem Plan hinzugekommenen), `run_checks` 188 von 188, `look_at_panel.py` zählt den Put-back-Knopf im Dialog statt in der Zeile und öffnet dafür den Vergleichsmodus wirklich.

- [ ] **Schritt 5: Commit**

```bash
git add tests/integration/look_at_panel.py README.md docs/superpowers/status.md
git commit -m "$(cat <<'EOF'
Point look_at_panel and the README at the compare dialog

The last references to the row-level put-back list: a browser check
that used to poke a synthetic _items and never opened anything,
rebuilt to drive the real compare-mode path; and every README
passage describing put-back as a row button, not only the one about
sections. Vorhaben J is done; status.md says so.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
